"""Export a replay week for the live demo: model inputs + actuals per region per hour.

The week is in the test period, so the model never saw it. The router feeds these
inputs to the ONNX model live, one hour per tick.
Run: uv run --with pandas --with numpy --with pyarrow python train/make_replay.py [start] [days]
"""
import json
import sys

import numpy as np
import pandas as pd

from build_dataset import FUT, OUT, PAST, REGIONS, load_eia, region_frame

START = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else "2026-10-19", tz="America/Denver")
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 7


def main():
    eia = load_eia()
    hours = pd.date_range(START, periods=DAYS * 24, freq="h").tz_convert("UTC")
    regions = {}
    for ba in REGIONS:
        r = region_frame(eia, ba)
        pos = r.index.get_indexer(hours)
        rows = []
        for t, i in zip(hours, pos):
            if i < PAST or i + FUT > len(r):
                continue
            past = r.iloc[i - PAST:i]
            fut = r.iloc[i:i + FUT]
            norm = r["norm"].iat[i]
            cols = ["demand", "gco2", "solar", "wind", "forecast", "temp", "cloud", "sun"]
            if not (np.isfinite(past[cols[:4]].to_numpy()).all() and np.isfinite(fut[cols[4:]].to_numpy()).all()):
                continue  # incomplete inputs (e.g. the look-ahead runs past the end of the weather data)
            loc = t.tz_convert(REGIONS[ba])
            rows.append({
                "utc": int(t.timestamp()),
                "past": np.stack([past["demand"] / norm, past["gco2"] / 1000, past["solar"], past["wind"]], -1).round(4).tolist(),
                "fut": np.stack([fut["forecast"] / norm, fut["temp"] / 30, fut["cloud"] / 100, fut["sun"] / 1000], -1).round(4).tolist(),
                "cal": [np.sin(2 * np.pi * loc.hour / 24), np.cos(2 * np.pi * loc.hour / 24), np.sin(2 * np.pi * loc.dayofweek / 7),
                        np.cos(2 * np.pi * loc.dayofweek / 7), np.sin(2 * np.pi * loc.dayofyear / 365.25), np.cos(2 * np.pi * loc.dayofyear / 365.25)],
                "actual": {"demand": float(r["demand"].iat[i]), "forecast": float(r["forecast"].iat[i]), "gco2": float(r["gco2"].iat[i]),
                           "peak": float(r["peak"].iat[i]), "share": float(r["share"].iat[i])},
            })
        regions[ba] = rows
        print(ba, len(rows), "hours")
    (OUT / "replay.json").write_text(json.dumps({"regions": list(REGIONS), "tz": REGIONS, "hours": regions}))
    print("wrote", OUT / "replay.json")


if __name__ == "__main__":
    main()
