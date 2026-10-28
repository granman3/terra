"""Export a replay week for the live demo (v2): model inputs + actuals per grid per hour.

The week is in the test period, so the model never saw it. The router feeds these
inputs to the ONNX model live, one hour per tick, for all 51 grids.
Run: uv run --with pandas --with numpy --with pyarrow --with openpyxl --with xlrd --with holidays python train/make_replay.py [start] [days]
"""
import json
import sys

import numpy as np
import pandas as pd

from build_dataset import FUT, GRIDS, OUT, PAST, REGIONS, ROUTE, channels, inputs_at, load_eia, load_markets, region_frame, us_holiday_days

START = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else "2026-10-19", tz="America/Denver")
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 7


def main():
    eia, _ = load_eia()
    markets, _ = load_markets()
    hol = us_holiday_days()
    hours = pd.date_range(START, periods=DAYS * 24, freq="h").tz_convert("UTC")
    out = {}
    for ba in REGIONS:
        r = region_frame(eia, ba, markets, hol)
        pos = r.index.get_indexer(hours)
        ok = (pos >= PAST) & (pos + FUT <= len(r))
        t = pos[ok]
        past, fut, cal, mkt = inputs_at(channels(r), r["norm"].to_numpy(np.float32), t)
        rows = []
        for k, i in enumerate(t):
            if not (np.isfinite(past[k]).all() and np.isfinite(fut[k]).all() and np.isfinite(mkt[k]).all()):
                continue  # incomplete inputs (e.g. the look-ahead runs past the end of the weather data)
            rows.append({
                "utc": int(r.index[i].timestamp()),
                "past": past[k].round(4).tolist(), "fut": fut[k].round(4).tolist(),
                "cal": cal[k].round(5).tolist(), "mkt": mkt[k].round(4).tolist(),
                "actual": {"demand": float(r["demand"].iat[i]), "forecast": float(r["forecast"].iat[i]), "gco2": float(r["gco2"].iat[i]),
                           "peak": float(r["peak"].iat[i]), "share": float(r["share"].iat[i])},
            })
        out[ba] = rows
        print(ba, len(rows), "hours", flush=True)
    meta = {ba: {"tz": GRIDS[ba][0], "city": GRIDS[ba][1], "ll": [GRIDS[ba][3], GRIDS[ba][2]]} for ba in REGIONS}
    (OUT / "replay_v2.json").write_text(json.dumps({"regions": list(REGIONS), "route": ROUTE, "meta": meta, "hours": out}))
    print("wrote", OUT / "replay_v2.json")


if __name__ == "__main__":
    main()
