"""Train the Mycelium grid model on the GPU, calibrate it, score it, export ONNX.

Small on purpose: an MLP over 48 h of grid history + 24 h of forecasts, with a region
embedding (~0.5M params). Three heads per future hour: P(peak), demand share of the
day's max, gCO2/kWh. Peak probabilities get temperature scaling on the validation set.

Also logs GPU power while training, so we can say what the model cost to train.

Run on enterprise:  .venv/bin/python train/train.py data/train/dataset.npz
Writes out/model/{mycelium.onnx, metrics.json, reliability.json, decision_eval.json}
"""
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from decide import WAITS, JOB_HOURS, DEADLINE_H, cost_matrix

torch.manual_seed(0)
DEV = "cuda" if torch.cuda.is_available() else "cpu"
OUT = Path(os.environ.get("OUT", "out/model"))
N_ROUTE = 4  # jobs route between the first 4 regions (PACE, CISO, BPAT, ERCO)
# MODEL=mlp: the 0.5M-param MLP (v2). MODEL=terra: a small transformer over the hours (v3), trained longer.
MODEL = os.environ.get("MODEL", "mlp")
EPOCHS = int(os.environ.get("EPOCHS", 40))
BATCH = int(os.environ.get("BATCH", 1024 if MODEL == "mlp" else 512))
LR = float(os.environ.get("LR", 2e-3 if MODEL == "mlp" else 4e-4))
SUBSET = int(os.environ.get("SUBSET", 0))
DROPOUT = float(os.environ.get("DROPOUT", 0.1))  # terra only
WD = float(os.environ.get("WD", 1e-4 if MODEL == "mlp" else 0.05))  # quick test runs: use only this many samples per split


class GridModel(nn.Module):
    def __init__(self, n_regions=4, hidden=512, horizon=24, past_ch=4, fut_ch=4, mkt=0):
        super().__init__()
        self.emb = nn.Embedding(n_regions, 8 if n_regions <= 4 else 16)
        d = 48 * past_ch + 24 * fut_ch + 6 + mkt + self.emb.embedding_dim
        self.body = nn.Sequential(nn.Linear(d, hidden), nn.GELU(), nn.Dropout(0.1),
                                  nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(0.1))
        self.peak = nn.Linear(hidden, horizon)
        self.share = nn.Linear(hidden, horizon)
        self.gco2 = nn.Linear(hidden, horizon)
        self.register_buffer("temperature", torch.ones(1))

    def forward(self, past, fut, cal, region, mkt=None):
        x = torch.cat([past.flatten(1), fut.flatten(1), cal] + ([] if mkt is None else [mkt]) + [self.emb(region)], 1)
        h = self.body(x)
        return self.peak(h), torch.sigmoid(self.share(h)) * 1.2, torch.relu(self.gco2(h))


class Block(nn.Module):
    """Pre-norm transformer block, written out with plain matmuls so the ONNX export stays simple."""
    def __init__(self, d, heads, drop=0.1):
        super().__init__()
        self.heads = heads
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.qkv, self.o = nn.Linear(d, 3 * d), nn.Linear(d, d)
        self.ff = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))
        self.drop = nn.Dropout(drop)

    def forward(self, x):
        B, T, D = x.shape
        q, k, v = self.qkv(self.n1(x)).reshape(B, T, 3, self.heads, D // self.heads).permute(2, 0, 3, 1, 4)
        a = torch.softmax(q @ k.transpose(-1, -2) / math.sqrt(D // self.heads), -1)
        x = x + self.drop(self.o((a @ v).transpose(1, 2).reshape(B, T, D)))
        return x + self.drop(self.ff(self.n2(x)))


class TerraNet(nn.Module):
    """Small transformer: one token per past hour (48), one per forecast hour (24), and a context token
    (calendar, yesterday's prices, which grid). Each forecast-hour token predicts that hour's peak, share and gCO2."""
    def __init__(self, n_regions, past_ch, fut_ch, mkt=0, d=256, layers=6, heads=8, horizon=24):
        super().__init__()
        self.horizon = horizon
        self.past_in, self.fut_in, self.ctx_in = nn.Linear(past_ch, d), nn.Linear(fut_ch, d), nn.Linear(6 + mkt, d)
        self.emb = nn.Embedding(n_regions, d)
        self.pos = nn.Parameter(torch.randn(1, 1 + 48 + horizon, d) * 0.02)
        self.blocks = nn.ModuleList(Block(d, heads, DROPOUT) for _ in range(layers))
        self.norm, self.head = nn.LayerNorm(d), nn.Linear(d, 3)
        self.register_buffer("temperature", torch.ones(1))

    def forward(self, past, fut, cal, region, mkt=None):
        ctx = self.ctx_in(torch.cat([cal] + ([] if mkt is None else [mkt]), 1)) + self.emb(region)
        x = torch.cat([ctx[:, None], self.past_in(past), self.fut_in(fut)], 1) + self.pos
        for b in self.blocks:
            x = b(x)
        o = self.head(self.norm(x[:, -self.horizon:])).float()
        return o[..., 0], torch.sigmoid(o[..., 1]) * 1.2, torch.relu(o[..., 2])


def build(kind, n_regions, past_ch, fut_ch, mkt):
    return (TerraNet if kind == "terra" else GridModel)(n_regions=n_regions, past_ch=past_ch, fut_ch=fut_ch, mkt=mkt)


def kind_of(state_dict):
    return "terra" if any(k.startswith("blocks.") for k in state_dict) else "mlp"


class Exported(nn.Module):
    """ONNX wrapper: calibrated probabilities, gCO2 back in g/kWh."""
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, past, fut, cal, region, mkt):
        logit, share, g = self.m(past, fut, cal, region, mkt)
        return torch.sigmoid(logit / self.m.temperature), share, g * 1000


def tensors(d, mask):
    # inputs first (past, fut, cal, region, mkt), then targets (y_peak, y_share, y_gco2)
    keys = ("past", "fut", "cal", "region") + (("mkt",) if "mkt" in d else ()) + ("y_peak", "y_share", "y_gco2")
    ts = [torch.as_tensor(d[k][mask]).to(DEV) for k in keys]
    return ts if "mkt" in d else ts[:4] + [None] + ts[4:]


def predict(model, past, fut, cal, region, mkt=None, bs=8192):
    model.eval()
    outs = []
    with torch.no_grad(), torch.autocast(DEV, dtype=torch.bfloat16, enabled=MODEL == "terra" and DEV == "cuda"):
        for i in range(0, len(past), bs):
            outs.append([o.float() for o in model(past[i:i + bs], fut[i:i + bs], cal[i:i + bs], region[i:i + bs],
                                                   None if mkt is None else mkt[i:i + bs])])
    return [torch.cat([o[j] for o in outs]) for j in range(3)]


def power_logger(path):
    if not shutil.which("nvidia-smi"):  # test runs off the GPU box: an empty log
        return subprocess.Popen(["true"], stdout=open(path, "w"))
    return subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,power.draw.instant,utilization.gpu",
                             "--format=csv,noheader,nounits", "-lms", "100"], stdout=open(path, "w"))


def energy_wh(path, seconds):
    rows = [l.split(",") for l in open(path) if l.count(",") == 2]
    watts = [float(r[1]) for r in rows if r[1].strip() not in ("", "[N/A]")]
    return (sum(watts) / len(watts)) * seconds / 3600 if watts else None, (sum(watts) / len(watts) if watts else None)


def reliability(p, y, bins=10):
    p, y = p.flatten().cpu().numpy(), y.flatten().cpu().numpy()
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum():
            out.append({"bin": [round(lo, 1), round(hi, 1)], "predicted": float(p[m].mean()), "actual": float(y[m].mean()), "n": int(m.sum())})
    return out


def brier(p, y):
    return float(((p - y) ** 2).mean())


def main(path):
    OUT.mkdir(parents=True, exist_ok=True)
    d = dict(np.load(path))
    if SUBSET:  # quick test: a small random slice of each split
        keep = np.concatenate([np.random.default_rng(0).choice(np.flatnonzero(d["split"] == s), SUBSET, replace=False) for s in (0, 1, 2)])
        d = {k: (v[keep] if v.shape[:1] == d["split"].shape else v) for k, v in d.items()}
    split = d["split"]
    tr, va, te = (tensors(d, split == s) for s in (0, 1, 2))
    model = build(MODEL, len(d["regions"]), d["past"].shape[2], d["fut"].shape[2], d["mkt"].shape[1] if "mkt" in d else 0).to(DEV)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"{MODEL}: {n_params / 1e6:.2f}M params, {EPOCHS} epochs, batch {BATCH}, lr {LR}, dropout {DROPOUT}, wd {WD}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    best = (float("inf"), None, 0)  # (val brier, state, epoch): keep the best checkpoint, not just the last
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=EPOCHS * (len(tr[0]) // BATCH + 1))
    bce = nn.BCEWithLogitsLoss()

    log = OUT / "train_power.csv"
    logger = power_logger(log)
    t0 = time.time()
    for epoch in range(EPOCHS):
        model.train()
        perm = torch.randperm(len(tr[0]), device=DEV)
        total = 0.0
        for i in range(0, len(perm), BATCH):
            b = perm[i:i + BATCH]
            past, fut, cal, region, mkt, yp, ys, yg = (None if x is None else x[b] for x in tr)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=MODEL == "terra" and DEV == "cuda"):
                logit, share, g = model(past, fut, cal, region, mkt)
            loss = bce(logit, yp) + 4 * nn.functional.mse_loss(share, ys) + 4 * nn.functional.mse_loss(g, yg)
            opt.zero_grad()
            loss.backward()
            if MODEL == "terra":
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total += loss.detach() * len(b)
        every = 5 if MODEL == "mlp" else 2
        if epoch % every == every - 1 or epoch == EPOCHS - 1:
            vl, vs, vg = predict(model, *va[:5])
            vb = brier(torch.sigmoid(vl), va[5])
            if vb < best[0]:
                best = (vb, copy.deepcopy(model.state_dict()), epoch + 1)
            print(f"epoch {epoch + 1:2d}  train {float(total) / len(perm):.4f}  val brier {vb:.4f}  "
                  f"val gco2 MAE {(vg - va[7]).abs().mean().item() * 1000:.0f} g  {(time.time() - t0) / 60:.1f} min", flush=True)
    model.load_state_dict(best[1])
    print(f"keeping epoch {best[2]} (val brier {best[0]:.4f})", flush=True)
    torch.cuda.synchronize() if DEV == "cuda" else None
    train_s = time.time() - t0
    logger.terminate()
    logger.wait()
    wh, avg_w = energy_wh(log, train_s)

    # temperature scaling on validation
    vl, _, _ = predict(model, *va[:5])
    temp = torch.ones(1, device=DEV, requires_grad=True)
    lbfgs = torch.optim.LBFGS([temp], lr=0.1, max_iter=100)

    def closure():
        lbfgs.zero_grad()
        l = bce(vl / temp, va[5])
        l.backward()
        return l
    lbfgs.step(closure)
    model.temperature.copy_(temp.detach())

    # test metrics
    tl, ts, tg = predict(model, *te[:5])
    p = torch.sigmoid(tl / model.temperature)
    y = te[5]
    base = torch.as_tensor(d["base_share"][split == 2]).to(DEV)
    base_ok = torch.isfinite(base).all(1)
    # fair probabilistic EIA baseline: logistic curve on the forecast's day share, fit on validation
    vb = torch.as_tensor(d["base_share"][split == 1]).to(DEV)
    vm = torch.isfinite(vb).all(1)
    ab = torch.tensor([20.0, 0.95], device=DEV, requires_grad=True)
    fit = torch.optim.LBFGS([ab], lr=0.1, max_iter=200)

    def closure_b():
        fit.zero_grad()
        l = bce(ab[0] * (vb[vm] - ab[1]), va[5][vm])
        l.backward()
        return l
    fit.step(closure_b)
    p_eia = torch.sigmoid(ab[0].detach() * (base - ab[1].detach()))
    train_rate = tr[5].mean(0)  # climatology by horizon hour
    region_names = list(d["regions"])
    metrics = {
        "model": MODEL, "epochs": EPOCHS, "best_epoch": best[2], "params": n_params, "device": torch.cuda.get_device_name(0) if DEV == "cuda" else "cpu",
        "train_seconds": round(train_s, 1), "train_energy_wh": round(wh, 2) if wh else None, "train_avg_watts": round(avg_w, 1) if avg_w else None,
        "temperature": round(model.temperature.item(), 3),
        "samples": {"train": int(len(tr[0])), "val": int(len(va[0])), "test": int(len(te[0]))},
        "test_peak_brier": {"model": brier(p, y), "climatology": brier(train_rate.expand_as(y), y),
                            "eia_forecast_rule": brier((base[base_ok] >= 0.95).float(), y[base_ok]),
                            "eia_forecast_calibrated": brier(p_eia[base_ok], y[base_ok])},
        "test_peak_accuracy": {"model": float(((p > 0.5) == (y > 0.5)).float().mean()),
                               "eia_forecast_rule": float(((base[base_ok] >= 0.95) == (y[base_ok] > 0.5)).float().mean())},
        "test_gco2_mae_g": float((tg - te[7]).abs().mean() * 1000),
        "test_share_mae": float((ts - te[6]).abs().mean()),
        "by_region": {},
    }
    reg = te[3]
    for i, name in enumerate(region_names):
        m = reg == i
        mb = m & base_ok
        metrics["by_region"][name] = {
            "brier_model": brier(p[m], y[m]), "brier_eia_rule": brier((base[mb] >= 0.95).float(), y[mb]),
            "brier_eia_calibrated": brier(p_eia[mb], y[mb]),
            "peak_hours_caught_model": float(((p[m] > 0.5) & (y[m] > 0.5)).sum() / (y[m] > 0.5).sum()),
            "peak_hours_caught_eia_rule": float(((base[mb] >= 0.95) & (y[mb] > 0.5)).sum() / (y[mb] > 0.5).sum()),
        }
    (OUT / "reliability.json").write_text(json.dumps({"model": reliability(p, y)}, indent=1))

    # decision-level eval: the same typed questions any outside router gets (where + when)
    # issue hours (every 3rd sampled UTC hour) where all routing regions have a sample, as (T, regions) indexes
    utc, regs = d["utc"][split == 2], d["region"][split == 2]
    route = np.flatnonzero(regs < N_ROUTE)
    order = route[np.lexsort((regs[route], utc[route]))]
    times, starts, counts = np.unique(utc[order], return_index=True, return_counts=True)
    full = (counts == N_ROUTE) & ((times // 3600) % 3 == 0)
    if full.any():  # (tiny SUBSET test runs can have no hour where all routing grids line up)
        keep = np.stack([order[s:s + N_ROUTE] for s in starts[full]])
        pk, gk, yk, ygk = p.cpu().numpy(), tg.cpu().numpy() * 1000, y.cpu().numpy(), te[7].cpu().numpy() * 1000
        pred_cost = cost_matrix(pk[keep], gk[keep])  # (T, regions, waits)
        true_cost = cost_matrix(yk[keep], ygk[keep])
        pick = pred_cost.reshape(len(keep), -1).argmin(1)
        best = true_cost.reshape(len(keep), -1).argmin(1)
        tc = true_cost.reshape(len(keep), -1)
        naive = tc[:, 0]  # Utah (region 0), start now
        metrics["decisions"] = {
            "n": int(len(keep)), "job_hours": JOB_HOURS, "deadline_h": DEADLINE_H,
            "exact_match": float((pick == best).mean()),
            "cost_model": float(tc[np.arange(len(keep)), pick].mean()),
            "cost_oracle": float(tc[np.arange(len(keep)), best].mean()),
            "cost_run_now_in_utah": float(naive.mean()),
            "utah_peak_hours_hit_model": float(true_cost_peak(yk[keep], pick)), "utah_peak_hours_hit_naive": float(yk[keep][:, 0, :JOB_HOURS].sum(1).mean()),
        }
        # export ~300 decision cases for router comparisons (raw numbers; the router words them)
        rng = np.random.default_rng(0)
        sel = rng.choice(len(keep), size=min(300, len(keep)), replace=False)
        cases = []
        pa, fu = d["past"][split == 2], d["fut"][split == 2]
        for s in sel:
            row = keep[s]
            cases.append({"utc": int(utc[row[0]]), "best": int(best[s]), "model_pick": int(pick[s]),
                          "true_cost": tc[s].round(4).tolist(),
                          "regions": {region_names[r]: {
                              "demandVsTypical": float(pa[row[r]][-1, 0]),
                              "demandTrend": float((pa[row[r]][-1, 0] - pa[row[r]][-4, 0]) / max(pa[row[r]][-1, 0], 1e-6)),
                              "gco2": float(pa[row[r]][-1, 1] * 1000), "solarShare": float(pa[row[r]][-1, 2]),
                              "hoursToForecastPeak": int(np.argmax(fu[row[r]][:, 0]))} for r in range(N_ROUTE)}})
        (OUT / "decision_eval.json").write_text(json.dumps({"waits": WAITS, "regions": region_names[:N_ROUTE], "cases": cases}))
    else:
        metrics["decisions"] = None

    model.eval()
    ex = Exported(model).eval()
    dummy = [x[:1] for x in te[:5]]
    torch.onnx.export(ex, tuple(dummy), OUT / "mycelium.onnx", input_names=["past", "fut", "cal", "region", "mkt"],
                      output_names=["p_peak", "share", "gco2"], dynamic_axes={k: {0: "n"} for k in ("past", "fut", "cal", "region", "mkt", "p_peak", "share", "gco2")},
                      dynamo=False)
    torch.save(model.state_dict(), OUT / "mycelium.pt")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


def true_cost_peak(y, pick):
    """Utah-or-wherever peak hours the job actually overlapped, for the model's picks."""
    from decide import job_hours_mask
    T, R, H = y.shape
    hits = []
    for i, k in enumerate(pick):
        r, w = divmod(int(k), len(WAITS))
        hits.append(y[i, r][job_hours_mask(w)].sum())
    return np.mean(hits)


if __name__ == "__main__":
    main(sys.argv[1])
