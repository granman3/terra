"""Current-hour demand for Terra's four routing regions in one keyless call: EIA-930 grid-monitor JSON
(hour-ending UTC, same convention and source as the training data). No fallback built in: for 5-min values run
the ISO-native scripts (caiso_outlook.py, ercot_dashboard.py, bpa_baltwg.py). PACE has no ISO-native
5-min public demand feed; EIA-930 is its only keyless live demand.
Run: python3 -I live_now.py   -> prints JSON {ba: {"utc_hour_ending":..., "demand_mw":..., "eia_forecast_mw":...}}
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

BAS = ["PACE", "CISO", "BPAT", "ERCO"]
now = datetime.now(timezone.utc)
q = "type[0]=D&type[1]=DF&" + "&".join(f"respondent[{i}]={r}" for i, r in enumerate(BAS))
url = (f"https://www.eia.gov/electricity/930-api/region_data/series_data?{q}"
       f"&start={(now - timedelta(hours=12)):%m%d%Y %H:00:00}&end={(now + timedelta(hours=2)):%m%d%Y %H:00:00}"
       "&frequency=hourly&timezone=Eastern&limit=10000&offset=0").replace(" ", "%20")
with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "terra-live-check/0.1"}), timeout=60) as r:
    j = json.load(r)
ser = {}
for blk in j:
    for s in blk["data"]:
        ser[(s["RESPONDENT_ID"], s["TYPE_ID"])] = dict(zip(s["VALUES"]["DATES"], s["VALUES"]["DATA"]))
out = {}
for ba in BAS:
    d = {k: v for k, v in ser.get((ba, "D"), {}).items() if v is not None}
    if d:
        t = max(d, key=lambda k: datetime.strptime(k, "%m/%d/%Y %H:%M:%S"))
        out[ba] = {"utc_hour_ending": datetime.strptime(t, "%m/%d/%Y %H:%M:%S").strftime("%Y-%m-%dT%H:00Z"),
                   "demand_mw": d[t], "eia_forecast_mw": ser.get((ba, "DF"), {}).get(t)}
print(json.dumps(out, indent=1))
