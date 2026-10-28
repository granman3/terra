"""Surge smoothing: how big a power jump an AI site puts on the grid when jobs start, at once vs staggered.

Measured: one RTX 4080 Super starting a llama.cpp prefill run at the 350 W cap (data/sweep/power/
power_pl350_pp.csv, nvidia-smi power.draw.instant every 100 ms; the driver refreshes it every 0.5 s).
Simulated, labeled: N identical GPUs. "At once" starts them all together; "staggered" spreads the starts
evenly over STAGGER_S seconds, which a job that can wait hours never notices.

The number that matters to Torus is the biggest rise in site power over any 1 s window: that's the
fast swing a flywheel (Torus Spin) has to catch.
Writes out/surge/gpu_start.json (the trace the router uses) and out/surge/metrics.json.
Run: python3 train/surge.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "data" / "sweep" / "power" / "power_pl350_pp.csv"
OUT = ROOT / "out" / "surge"
DT = 0.1
STAGGER_S = 60
SITE_W = 1_000_000  # a labeled 1 MW site of GPUs at the cap


def start_trace():
    """Watts from the last idle sample through 3 s of steady load, 100 ms apart."""
    w = [float(r[" power.draw.instant [W]"]) for r in csv.DictReader(open(TRACE))]
    idle = w[0]
    k = next(i for i, x in enumerate(w) if x > idle + 5) - 1
    steady = sum(w[-50:]) / 50
    end = next(i for i in range(k, len(w)) if w[i] >= 0.97 * steady) + 30
    return idle, steady, w[k:end]


def site_jump(trace, idle, n, stagger_s):
    """Biggest 1 s rise in total power when n GPUs start, offsets spread evenly over stagger_s."""
    offs = [round(i * stagger_s / n / DT) for i in range(n)] if stagger_s else [0] * n
    steps = max(offs) + len(trace) + 10
    total = [0.0] * steps
    for o in offs:
        for t in range(steps):
            i = t - o
            total[t] += idle if i < 0 else trace[min(i, len(trace) - 1)]
    win = round(1 / DT)
    return max(total[t + win] - total[t] for t in range(steps - win))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idle, steady, tr = start_trace()
    one = site_jump(tr, idle, 1, 0)
    n = round(SITE_W / steady)
    # n GPUs at once is exactly n x one GPU's jump; the staggered case needs the full sum
    at_once, staggered = n * one, site_jump(tr, idle, n, STAGGER_S)
    (OUT / "gpu_start.json").write_text(json.dumps({"dt_s": DT, "idle_w": idle, "steady_w": round(steady, 1), "watts": tr,
                                                    "source": str(TRACE.relative_to(ROOT))}))
    m = {"one_gpu": {"idle_w": idle, "steady_w": round(steady, 1), "jump_1s_w": round(one), "seconds_to_full": round(len(tr) * DT - 3, 1)},
         "site": {"gpus": n, "mw": SITE_W / 1e6, "stagger_s": STAGGER_S,
                  "jump_1s_at_once_kw": round(at_once / 1e3), "jump_1s_staggered_kw": round(staggered / 1e3, 1),
                  "smaller_x": round(at_once / staggered)},
         "source": str(TRACE.relative_to(ROOT)), "note": "one GPU measured, the site is N identical GPUs (simulated)"}
    (OUT / "metrics.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
