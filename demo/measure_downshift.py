"""Measure the on-stage downshift on this Mac and save it for the deck (out/mac/downshift.json).

Needs demo/mac_agent.py running. Starts the 4B load, waits for it to settle, samples 20 s,
fires the peak event (downshift to the 455K model), samples 20 s, then restores and stops.
Run: python3 demo/measure_downshift.py
"""
import json
import statistics
import time
import urllib.request
from pathlib import Path

AGENT = "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parent.parent / "out" / "mac" / "downshift.json"


def post(action):
    return json.load(urllib.request.urlopen(urllib.request.Request(f"{AGENT}/{action}", method="POST"), timeout=10))


def state():
    return json.load(urllib.request.urlopen(f"{AGENT}/state", timeout=10))


def sample(seconds):
    rows, t0 = [], time.time()
    while time.time() - t0 < seconds:
        rows.append(state())
        time.sleep(0.25)
    return rows


def summary(rows):
    w = [r["watts"] for r in rows]
    rate = [r["forecasts_per_s"] for r in rows if r.get("forecasts_per_s")]
    j = [r["joules_per_forecast"] for r in rows if r.get("joules_per_forecast")]
    return {"watts": round(statistics.median(w), 1), "forecasts_per_s": round(statistics.median(rate), 2) if rate else None,
            "joules_per_forecast": round(statistics.median(j), 4) if j else None, "model": rows[-1]["model"]}


def main():
    post("restore")
    idle = summary(sample(5))
    post("load")
    while state().get("forecasts_per_s", 0) == 0:
        time.sleep(1)
    time.sleep(10)  # let the GPU clocks settle
    big = summary(sample(20))
    post("event")
    time.sleep(3)
    tiny = summary(sample(20))
    post("restore")
    post("unload")
    out = {"idle_watts": idle["watts"], "big": big, "tiny": tiny,
           "power_drop_pct": round((1 - tiny["watts"] / big["watts"]) * 100),
           "measured": time.strftime("%Y-%m-%d %H:%M"), "machine": "MacBook Pro M4 Pro", "power": "CPU+GPU+ANE via macmon"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
