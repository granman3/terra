"""How little energy Terra's small model needs per forecast, on this MacBook (chip power from macmon, no sudo).

One forecast = one power region's next 24 hours (the same unit mac_agent.py counts for the 4B model).
Measures the chip at idle for IDLE_S, then the small model forecasting the replay week nonstop on the CPU for LOAD_S,
50 regions per call, and reports joules per forecast above idle. Writes out/mac/tiny_efficiency.json.
Run with nothing else heavy open: demo/.venv/bin/python demo/measure_tiny.py   (TINY=out/v3/mycelium.pt for another model)
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "train"))
from train import build, kind_of  # noqa: E402

TINY = Path(os.environ.get("TINY", ROOT / "out" / "v2" / "mycelium.pt")).resolve()
IDLE_S, LOAD_S = 8, 15
samples = []


def sampler(stop):
    p = subprocess.Popen(["macmon", "pipe", "-i", "200"], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        if stop.is_set():
            break
        try:
            m = json.loads(line)
        except ValueError:
            continue
        samples.append((time.time(), m["cpu_power"] + m["gpu_power"] + m.get("ane_power", 0)))
    p.terminate()


def mean_w(t0, t1):
    w = [x for t, x in samples if t0 <= t <= t1]
    return sum(w) / len(w), len(w)


def main():
    torch.set_num_threads(1)
    r = json.load(open(ROOT / "data" / "train" / "replay_v2.json"))
    regions = r["regions"]
    rows = [(ba, h) for i in range(len(r["hours"]["PACE"])) for ba in regions if i < len(r["hours"][ba]) for h in [r["hours"][ba][i]]]
    sd = torch.load(TINY, map_location="cpu")
    m = build(kind_of(sd), len(regions), 5, 10, 6)
    m.load_state_dict(sd)
    m.eval()
    batches = []
    for k in range(0, len(rows) - len(regions), len(regions)):
        b = rows[k:k + len(regions)]
        batches.append([torch.tensor([h[key] for _, h in b]) for key in ("past", "fut", "cal")] +
                       [torch.tensor([regions.index(ba) for ba, _ in b]), torch.tensor([h["mkt"] for _, h in b])])
    stop = threading.Event()
    threading.Thread(target=sampler, args=(stop,), daemon=True).start()
    time.sleep(2)
    t0 = time.time()
    time.sleep(IDLE_S)
    t1 = time.time()
    n, k = 0, 0
    with torch.no_grad():
        while time.time() - t1 < LOAD_S:
            past, fut, cal, reg, mkt = batches[k % len(batches)]
            m(past, fut, cal, reg, mkt)
            n += len(reg)
            k += 1
    t2 = time.time()
    time.sleep(0.5)
    stop.set()
    idle, ni = mean_w(t0, t1)
    load, nl = mean_w(t1 + 1, t2)  # skip the first second while clocks ramp
    rate = n / (t2 - t1)
    out = {"model": str(TINY.relative_to(ROOT)), "params": sum(p.numel() for p in m.parameters()), "threads": 1,
           "idle_w": round(idle, 2), "load_w": round(load, 2), "forecasts_per_s": round(rate),
           "joules_per_forecast": float(f"{(load - idle) / rate:.3g}"), "samples": {"idle": ni, "load": nl},
           "unit": "one forecast = one power region's next 24 h", "measured": time.strftime("%Y-%m-%d %H:%M"),
           "joules_per_forecast_total_chip": float(f"{load / rate:.3g}"),
           "year_all_regions_joules": round((load - idle) / rate * 50 * 8760, 1),
           "note": "joules_per_forecast is above idle; *_total_chip counts all chip power, the convention of out/mac/downshift*.json"}
    (ROOT / "out" / "mac").mkdir(parents=True, exist_ok=True)
    (ROOT / "out" / "mac" / "tiny_efficiency.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
