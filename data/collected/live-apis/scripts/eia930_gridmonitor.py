"""EIA-930 hourly demand (D) and day-ahead demand forecast (DF) for any balancing authorities, keyless.

Uses the JSON endpoint behind EIA's Hourly Electric Grid Monitor (www.eia.gov/electricity/gridmonitor). It is
undocumented (the official route is API v2 with a free key), so treat it as best effort. Times are UTC, hour ENDING,
the same convention as the bulk 6-month CSVs ("UTC Time at End of Hour"); verified on PACE 2026-10-25.
D lags ~1 h; NG (net generation) and TI (interchange) lag ~17 h on this endpoint, so only D/DF are live.
Run: python3 -I eia930_gridmonitor.py [PACE CISO BPAT ERCO ...]
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BAS = sys.argv[1:] or ["PACE", "CISO", "BPAT", "ERCO"]
now = datetime.now(timezone.utc)
a, b = (now - timedelta(hours=30)).strftime("%m%d%Y %H:00:00"), (now + timedelta(hours=30)).strftime("%m%d%Y %H:00:00")
q = "&".join(f"type[{i}]={t}" for i, t in enumerate(["D", "DF"])) + "&" + \
    "&".join(f"respondent[{i}]={r}" for i, r in enumerate(BAS))
url = (f"https://www.eia.gov/electricity/930-api/region_data/series_data?{q}&start={a}&end={b}"
       "&frequency=hourly&timezone=Eastern&limit=10000&offset=0").replace(" ", "%20")
req = urllib.request.Request(url, headers={"User-Agent": "terra-live-check/0.1"})
with urllib.request.urlopen(req, timeout=60) as r:
    j = json.load(r)
out = {}
for blk in j:
    for s in blk["data"]:
        pts = [(d, v) for d, v in zip(s["VALUES"]["DATES"], s["VALUES"]["DATA"]) if v is not None]
        if pts:
            out.setdefault(s["RESPONDENT_ID"], {})[s["TYPE_ID"]] = pts
for ba in BAS:
    d = out.get(ba, {})
    if "D" in d:
        t, v = d["D"][-1]
        fc = dict(d.get("DF", [])).get(t)
        print(f"{ba}: demand {v} MW, hour ending {datetime.strptime(t, '%m/%d/%Y %H:%M:%S'):%Y-%m-%d %H:00} UTC"
              f" (EIA day-ahead forecast for that hour {fc} MW; forecast runs to {d['DF'][-1][0]} UTC)")
    else:
        print(f"{ba}: no demand returned")
