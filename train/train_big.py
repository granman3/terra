"""Fine-tune a ~4B LLM (Qwen3-4B, LoRA) on the same peak question the tiny model answers.

Same samples, same splits as train.py, but the inputs are written out as text and a
24-output head on top of the LLM gives P(peak) for each of the next 24 hours. Scored
against the 455K-param model and the EIA baseline on one fixed test subset, with GPU
power logged so both models get a joules-per-decision number.

Run on enterprise:
  PYTHONPATH=train .venv/bin/python train/train_big.py data/train/dataset.npz [dry]
Writes out/big/{adapter/, merged/, metrics_big.json, test_idx.npy, p_big.npy, train_power.csv}
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from peft import LoraConfig, get_peft_model

from train import GridModel, power_logger, energy_wh, brier, reliability
from fetch_weather import GRIDS

torch.manual_seed(0)
BASE = os.environ.get("BASE", "/fast/hf/Qwen3-4B-Instruct-2507")
OUT = Path(os.environ.get("OUT", "out/big"))
TINY = os.environ.get("TINY", "out/model/mycelium.pt")
N_TRAIN = int(os.environ.get("N_TRAIN", 12000))
N_VAL, N_TEST = 1000, 3000
BATCH, ACCUM, LR = int(os.environ.get("BATCH", 4)), int(os.environ.get("ACCUM", 4)), 2e-4
NAMES = {"PACE": "Utah (PACE)", "CISO": "California (CISO)", "BPAT": "Pacific Northwest (BPAT)", "ERCO": "Texas (ERCOT)"}
NAMES.update({b: f"{b} ({g[1]} area)" for b, g in GRIDS.items() if b not in NAMES})
HUB_NAMES = ["Mid-C", "Palo Verde", "SP15", "PJM West", "New England"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ints(xs, scale=1.0):
    return " ".join(str(int(round(float(x) * scale))) for x in xs)


def to_text(past, fut, cal, region, regions, mkt=None):
    """The model's whole view of one grid at one hour, as text. Same inputs as the tiny model,
    except carbon, solar, wind and interchange history are the last 24 h instead of 48 h (shorter prompts).
    v1 inputs: past 4 channels, fut 4. v2 adds interchange, humidity, dew point, wind, rain, sun, holiday, prices."""
    hour = round(math.atan2(cal[0], cal[1]) / (2 * math.pi) * 24) % 24
    dow = round(math.atan2(cal[2], cal[3]) / (2 * math.pi) * 7) % 7
    doy = (math.atan2(cal[4], cal[5]) / (2 * math.pi) * 365.25) % 365.25
    month = MONTHS[min(11, int(doy / 30.44))]
    return (f"Grid: {NAMES[regions[region]]}. Now: {DAYS[dow]} {hour:02d}:00 local, {month}.\n"
            f"Demand vs 30-day mean, last 48 h (%): {ints(past[:, 0], 100)}\n"
            f"Carbon gCO2/kWh, last 24 h: {ints(past[-24:, 1], 1000)}\n"
            f"Solar share, last 24 h (%): {ints(past[-24:, 2], 100)}\n"
            f"Wind share, last 24 h (%): {ints(past[-24:, 3], 100)}\n"
            f"EIA demand forecast vs mean, next 24 h (%): {ints(fut[:, 0], 100)}\n"
            f"Temperature forecast, next 24 h (C): {ints(fut[:, 1], 30)}\n"
            f"Cloud forecast, next 24 h (%): {ints(fut[:, 2], 100)}\n"
            f"Sunlight forecast, next 24 h (W/m2): {ints(fut[:, 3], 1000)}\n"
            f"Which of the next 24 hours are in this grid's daily peak?") if past.shape[1] == 4 else (
            f"Grid: {NAMES[regions[region]]}. Now: {DAYS[dow]} {hour:02d}:00 local, {month}"
            f"{', a US holiday' if fut[0, 9] > 0.5 else ''}.\n"
            f"Demand vs 30-day mean, last 48 h (%): {ints(past[:, 0], 100)}\n"
            f"Carbon gCO2/kWh, last 24 h: {ints(past[-24:, 1], 1000)}\n"
            f"Solar share, last 24 h (%): {ints(past[-24:, 2], 100)}\n"
            f"Wind share, last 24 h (%): {ints(past[-24:, 3], 100)}\n"
            f"Net exports vs mean demand, last 24 h (%): {ints(past[-24:, 4], 100)}\n"
            f"EIA demand forecast vs mean, next 24 h (%): {ints(fut[:, 0], 100)}\n"
            f"Temperature forecast, next 24 h (C): {ints(fut[:, 1], 30)}\n"
            f"Humidity forecast, next 24 h (%): {ints(fut[:, 2], 100)}\n"
            f"Dew point forecast, next 24 h (C): {ints(fut[:, 3], 30)}\n"
            f"Cloud forecast, next 24 h (%): {ints(fut[:, 4], 100)}\n"
            f"Sunlight forecast, next 24 h (W/m2): {ints(fut[:, 5], 1000)}\n"
            f"Wind at 100 m forecast, next 24 h (km/h): {ints(fut[:, 6], 50)}\n"
            f"Rain forecast, next 24 h (0.1 mm): {ints(fut[:, 7], 50)}\n"
            f"Sun height, next 24 h (% of overhead): {ints(fut[:, 8], 100)}\n"
            f"Yesterday's prices: " + ", ".join(f"{h} ${v * 100:.0f}/MWh" for h, v in zip(HUB_NAMES, mkt[:5]))
            + f", Henry Hub gas ${mkt[5] * 5:.2f}/MMBtu\n"
            f"Which of the next 24 hours are in this grid's daily peak?")


def pick(split, n, seed):
    idx = np.flatnonzero(split)
    return np.sort(np.random.default_rng(seed).choice(idx, size=min(n, len(idx)), replace=False))


def predict_big(model, tok, texts, bs=16):
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            enc = tok(texts[i:i + bs], return_tensors="pt", padding=True).to("cuda")
            out.append(model(**enc).logits.float().cpu())
    return torch.cat(out)


def scores(p, y, reg, regions):
    out = {"brier": brier(p, y), "accuracy": float(((p > 0.5) == (y > 0.5)).float().mean()), "by_region": {}}
    for i, name in enumerate(regions):
        m = reg == i
        out["by_region"][name] = {"brier": brier(p[m], y[m]),
                                  "peak_hours_caught": float(((p[m] > 0.5) & (y[m] > 0.5)).sum() / (y[m] > 0.5).sum())}
    return out


def joules_per_decision(fn, n_decisions, path, min_s=10.0):
    """Run fn() repeatedly for at least min_s seconds with the power logger on; J per decision."""
    logger = power_logger(path)
    time.sleep(0.5)
    t0, reps = time.time(), 0
    while time.time() - t0 < min_s or reps == 0:
        fn()
        reps += 1
    torch.cuda.synchronize()
    secs = time.time() - t0
    logger.terminate()
    logger.wait()
    wh, watts = energy_wh(path, secs)
    return {"joules": wh * 3600 / (reps * n_decisions), "avg_watts": watts, "seconds_per_decision": secs / (reps * n_decisions)}


def main(path, dry=False):
    OUT.mkdir(parents=True, exist_ok=True)
    d = dict(np.load(path))
    regions = list(d["regions"])
    split = d["split"]
    tr, va, te = pick(split == 0, N_TRAIN, 0), pick(split == 1, N_VAL, 1), pick(split == 2, N_TEST, 2)
    np.save(OUT / "test_idx.npy", te)
    mk = d.get("mkt")
    text = lambda ix: [to_text(d["past"][i], d["fut"][i], d["cal"][i], int(d["region"][i]), regions, None if mk is None else mk[i]) for i in ix]

    tok = AutoTokenizer.from_pretrained(BASE)
    tok.padding_side = "left"
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=24, dtype=torch.bfloat16).to("cuda")
    model.config.pad_token_id = tok.pad_token_id
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="SEQ_CLS",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    n_params = sum(p.numel() for p in model.parameters())
    n_train_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    lens = [len(tok(t).input_ids) for t in text(tr[:200])]
    print(f"params {n_params / 1e9:.2f}B, trainable {n_train_params / 1e6:.1f}M, prompt tokens ~{np.mean(lens):.0f} (max {max(lens)})", flush=True)

    steps = (20 if dry else len(tr) // (BATCH * ACCUM))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=steps, pct_start=max(0.05, 3 / steps))
    bce = nn.BCEWithLogitsLoss()
    order = np.random.default_rng(3).permutation(tr)
    y_all = d["y_peak"]

    log = OUT / "train_power.csv"
    logger = power_logger(log)
    t0 = time.time()
    model.train()
    for step in range(steps):
        total = 0.0
        for a in range(ACCUM):
            b = order[(step * ACCUM + a) * BATCH:(step * ACCUM + a + 1) * BATCH]
            enc = tok(text(b), return_tensors="pt", padding=True).to("cuda")
            logits = model(**enc).logits.float()
            loss = bce(logits, torch.as_tensor(y_all[b]).cuda()) / ACCUM
            loss.backward()
            total += loss.item()
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        sched.step()
        opt.zero_grad()
        if step % 10 == 0 or step == steps - 1:
            el = time.time() - t0
            print(f"step {step + 1}/{steps}  loss {total:.4f}  {el / (step + 1):.2f} s/step  eta {el / (step + 1) * (steps - step - 1) / 60:.0f} min  "
                  f"mem {torch.cuda.max_memory_allocated() / 2**30:.1f} GB", flush=True)
    torch.cuda.synchronize()
    train_s = time.time() - t0
    logger.terminate()
    logger.wait()
    wh, avg_w = energy_wh(log, train_s)
    if dry:
        print(f"dry run ok: {train_s / steps:.2f} s/step -> full run ~{train_s / steps * (N_TRAIN // (BATCH * ACCUM)) / 3600:.1f} h, {avg_w:.0f} W")
        return

    model.save_pretrained(OUT / "adapter")

    # temperature scaling on validation, like the tiny model
    vl = predict_big(model, tok, text(va))
    vy = torch.as_tensor(y_all[va])
    temp = torch.ones(1, requires_grad=True)
    lbfgs = torch.optim.LBFGS([temp], lr=0.1, max_iter=100)

    def closure():
        lbfgs.zero_grad()
        l = bce(vl / temp, vy)
        l.backward()
        return l
    lbfgs.step(closure)
    T = float(temp.detach())

    # test: big model, tiny model and EIA on the same 3000 rows
    t1 = time.time()
    tl = predict_big(model, tok, text(te))
    eval_s = time.time() - t1
    p_big = torch.sigmoid(tl / T)
    np.save(OUT / "p_big.npy", p_big.numpy())
    y, reg = torch.as_tensor(y_all[te]), torch.as_tensor(d["region"][te])

    tiny = GridModel(n_regions=len(regions), past_ch=d["past"].shape[2], fut_ch=d["fut"].shape[2], mkt=0 if mk is None else mk.shape[1]).cuda()
    tiny.load_state_dict(torch.load(TINY))
    tiny.eval()
    tin = [torch.as_tensor(d[k][te]).cuda() for k in ("past", "fut", "cal", "region") + (() if mk is None else ("mkt",))]
    with torch.no_grad():
        p_tiny = torch.sigmoid(tiny(*tin)[0] / tiny.temperature).float().cpu()

    # EIA baseline: logistic on the forecast's day share, fit on the full validation split
    vb, vyb = torch.as_tensor(d["base_share"][split == 1]), torch.as_tensor(y_all[split == 1])
    vm = torch.isfinite(vb).all(1)
    ab = torch.tensor([20.0, 0.95], requires_grad=True)
    fit = torch.optim.LBFGS([ab], lr=0.1, max_iter=200)

    def closure_b():
        fit.zero_grad()
        l = bce(ab[0] * (vb[vm] - ab[1]), vyb[vm])
        l.backward()
        return l
    fit.step(closure_b)
    base = torch.as_tensor(d["base_share"][te])
    ok = torch.isfinite(base).all(1)
    p_eia = torch.sigmoid(ab[0].detach() * (base - ab[1].detach()))

    # energy per decision (one decision = one grid, next 24 h), same GPU, same way
    sub = text(te[:64])
    j_big = joules_per_decision(lambda: predict_big(model, tok, sub), len(sub), OUT / "eval_power_big.csv", 20)

    def run_tiny():
        with torch.no_grad():
            tiny(*tin)
    j_tiny = joules_per_decision(run_tiny, len(te), OUT / "eval_power_tiny.csv", 10)

    metrics = {
        "base": BASE.split("/")[-1], "params": n_params, "trainable_params": n_train_params,
        "tiny_params": sum(p.numel() for p in tiny.parameters()),
        "train_samples": int(len(tr)), "train_seconds": round(train_s), "train_energy_wh": round(wh, 1), "train_avg_watts": round(avg_w),
        "temperature": round(T, 3), "test_rows": int(len(te)), "eval_seconds": round(eval_s, 1),
        "big": scores(p_big, y, reg, regions), "tiny": scores(p_tiny, y, reg, regions),
        "eia_calibrated": scores(p_eia[ok], y[ok], reg[ok], regions),
        "joules_per_decision": {"big": j_big, "tiny": j_tiny, "ratio": j_big["joules"] / j_tiny["joules"]},
        "agree_big_tiny": float(((p_big > 0.5) == (p_tiny > 0.5)).float().mean()),
    }
    (OUT / "reliability_big.json").write_text(json.dumps({"big": reliability(p_big, y), "tiny": reliability(p_tiny, y)}, indent=1))
    (OUT / "metrics_big.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)

    # merged weights for the Mac demo (Qwen3 + LoRA folded in + the 24-hour head)
    merged = model.merge_and_unload()
    merged.config.peak_temperature = T  # not "temperature": newer transformers treat that as a generation setting and refuse to save
    merged.save_pretrained(OUT / "merged", safe_serialization=True)
    tok.save_pretrained(OUT / "merged")
    print("saved", OUT / "merged")


if __name__ == "__main__":
    main(sys.argv[1], dry=len(sys.argv) > 2 and sys.argv[2] == "dry")
