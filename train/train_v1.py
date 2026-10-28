"""Train the Mycelium grid model on the GPU, calibrate it, score it, export ONNX.

Small on purpose: an MLP over 48 h of grid history + 24 h of forecasts, with a region
embedding (~0.5M params). Three heads per future hour: P(peak), demand share of the
day's max, gCO2/kWh. Peak probabilities get temperature scaling on the validation set.

Also logs GPU power while training, so we can say what the model cost to train.

Run on enterprise:  .venv/bin/python train/train.py data/train/dataset.npz
Writes out/model/{mycelium.onnx, metrics.json, reliability.json, decision_eval.json}
"""
import json
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
OUT = Path("out/model")
EPOCHS, BATCH, LR = 40, 1024, 2e-3


class GridModel(nn.Module):
    def __init__(self, n_regions=4, hidden=512, horizon=24):
        super().__init__()
        self.emb = nn.Embedding(n_regions, 8)
        d = 48 * 4 + 24 * 4 + 6 + 8
        self.body = nn.Sequential(nn.Linear(d, hidden), nn.GELU(), nn.Dropout(0.1),
                                  nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(0.1))
        self.peak = nn.Linear(hidden, horizon)
        self.share = nn.Linear(hidden, horizon)
        self.gco2 = nn.Linear(hidden, horizon)
        self.register_buffer("temperature", torch.ones(1))

    def forward(self, past, fut, cal, region):
        x = torch.cat([past.flatten(1), fut.flatten(1), cal, self.emb(region)], 1)
        h = self.body(x)
        return self.peak(h), torch.sigmoid(self.share(h)) * 1.2, torch.relu(self.gco2(h))


class Exported(nn.Module):
    """ONNX wrapper: calibrated probabilities, gCO2 back in g/kWh."""
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, past, fut, cal, region):
        logit, share, g = self.m(past, fut, cal, region)
        return torch.sigmoid(logit / self.m.temperature), share, g * 1000


def tensors(d, mask):
    return [torch.as_tensor(d[k][mask]).to(DEV) for k in ("past", "fut", "cal", "region", "y_peak", "y_share", "y_gco2")]


def predict(model, past, fut, cal, region, bs=8192):
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(past), bs):
            outs.append([o.float() for o in model(past[i:i + bs], fut[i:i + bs], cal[i:i + bs], region[i:i + bs])])
    return [torch.cat([o[j] for o in outs]) for j in range(3)]


def power_logger(path):
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
    split = d["split"]
    tr, va, te = (tensors(d, split == s) for s in (0, 1, 2))
    model = GridModel(n_regions=len(d["regions"])).to(DEV)
    n_params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
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
            past, fut, cal, region, yp, ys, yg = (x[b] for x in tr)
            logit, share, g = model(past, fut, cal, region)
            loss = bce(logit, yp) + 4 * nn.functional.mse_loss(share, ys) + 4 * nn.functional.mse_loss(g, yg)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(b)
        if epoch % 5 == 4 or epoch == EPOCHS - 1:
            vl, vs, vg = predict(model, *va[:4])
            print(f"epoch {epoch + 1:2d}  train {total / len(perm):.4f}  val brier {brier(torch.sigmoid(vl), va[4]):.4f}  "
                  f"val gco2 MAE {(vg - va[6]).abs().mean().item() * 1000:.0f} g", flush=True)
    torch.cuda.synchronize() if DEV == "cuda" else None
    train_s = time.time() - t0
    logger.terminate()
    logger.wait()
    wh, avg_w = energy_wh(log, train_s)

    # temperature scaling on validation
    vl, _, _ = predict(model, *va[:4])
    temp = torch.ones(1, device=DEV, requires_grad=True)
    lbfgs = torch.optim.LBFGS([temp], lr=0.1, max_iter=100)

    def closure():
        lbfgs.zero_grad()
        l = bce(vl / temp, va[4])
        l.backward()
        return l
    lbfgs.step(closure)
    model.temperature.copy_(temp.detach())

    # test metrics
    tl, ts, tg = predict(model, *te[:4])
    p = torch.sigmoid(tl / model.temperature)
    y = te[4]
    base = torch.as_tensor(d["base_share"][split == 2]).to(DEV)
    base_ok = torch.isfinite(base).all(1)
    # fair probabilistic EIA baseline: logistic curve on the forecast's day share, fit on validation
    vb = torch.as_tensor(d["base_share"][split == 1]).to(DEV)
    vm = torch.isfinite(vb).all(1)
    ab = torch.tensor([20.0, 0.95], device=DEV, requires_grad=True)
    fit = torch.optim.LBFGS([ab], lr=0.1, max_iter=200)

    def closure_b():
        fit.zero_grad()
        l = bce(ab[0] * (vb[vm] - ab[1]), va[4][vm])
        l.backward()
        return l
    fit.step(closure_b)
    p_eia = torch.sigmoid(ab[0].detach() * (base - ab[1].detach()))
    train_rate = tr[4].mean(0)  # climatology by horizon hour
    region_names = list(d["regions"])
    metrics = {
        "params": n_params, "device": torch.cuda.get_device_name(0) if DEV == "cuda" else "cpu",
        "train_seconds": round(train_s, 1), "train_energy_wh": round(wh, 2) if wh else None, "train_avg_watts": round(avg_w, 1) if avg_w else None,
        "temperature": round(model.temperature.item(), 3),
        "samples": {"train": int(len(tr[0])), "val": int(len(va[0])), "test": int(len(te[0]))},
        "test_peak_brier": {"model": brier(p, y), "climatology": brier(train_rate.expand_as(y), y),
                            "eia_forecast_rule": brier((base[base_ok] >= 0.95).float(), y[base_ok]),
                            "eia_forecast_calibrated": brier(p_eia[base_ok], y[base_ok])},
        "test_peak_accuracy": {"model": float(((p > 0.5) == (y > 0.5)).float().mean()),
                               "eia_forecast_rule": float(((base[base_ok] >= 0.95) == (y[base_ok] > 0.5)).float().mean())},
        "test_gco2_mae_g": float((tg - te[6]).abs().mean() * 1000),
        "test_share_mae": float((ts - te[5]).abs().mean()),
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
    # issue hours (every 3rd UTC hour) where all regions have a sample, as (T, regions) indexes
    utc, regs = d["utc"][split == 2], d["region"][split == 2]
    order = np.lexsort((regs, utc))
    times, starts, counts = np.unique(utc[order], return_index=True, return_counts=True)
    full = (counts == len(region_names)) & ((times // 3600) % 3 == 0)
    keep = np.stack([order[s:s + len(region_names)] for s in starts[full]])
    pk, gk, yk, ygk = p.cpu().numpy(), tg.cpu().numpy() * 1000, y.cpu().numpy(), te[6].cpu().numpy() * 1000
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
                          "hoursToForecastPeak": int(np.argmax(fu[row[r]][:, 0]))} for r in range(len(region_names))}})
    (OUT / "decision_eval.json").write_text(json.dumps({"waits": WAITS, "regions": region_names, "cases": cases}))

    model.eval()
    ex = Exported(model).eval()
    dummy = [x[:1] for x in te[:4]]
    torch.onnx.export(ex, tuple(dummy), OUT / "mycelium.onnx", input_names=["past", "fut", "cal", "region"],
                      output_names=["p_peak", "share", "gco2"], dynamic_axes={k: {0: "n"} for k in ("past", "fut", "cal", "region", "p_peak", "share", "gco2")},
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
