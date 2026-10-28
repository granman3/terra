"""Open-Meteo forecast (api.open-meteo.com/v1/forecast), keyless (free for non-commercial use, ~10k calls/day).
Default: tomorrow's hourly forecast (America/Denver day) for Salt Lake City + the Utah solar sites, written to
../tomorrow_weather.json. --model: same variables, units and timezone (GMT, km/h) as train/fetch_weather.py and
train/fetch_solar_sites.py, so the output can be fed to the trained model without conversion.
Run: python3 -I openmeteo_forecast.py [YYYY-MM-DD] [--model]
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SITES = {"salt_lake_city": (40.76, -111.89), "milford": (38.40, -113.01), "cedar_city": (37.68, -113.06),
         "delta": (39.35, -112.58)}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = "--model" in sys.argv
day = args[0] if args else str((datetime.now(ZoneInfo("America/Denver")) + timedelta(days=1)).date())
if model:  # union of fetch_weather.py and fetch_solar_sites.py VARS, GMT, default units (degC, km/h, W/m2)
    v = ("temperature_2m,relative_humidity_2m,dew_point_2m,cloud_cover,shortwave_radiation,direct_radiation,"
         "diffuse_radiation,wind_speed_100m,precipitation")
    tz, extra = "GMT", ""
else:
    v = "temperature_2m,cloud_cover,shortwave_radiation,direct_radiation,diffuse_radiation,wind_speed_10m,wind_speed_100m"
    tz, extra = "America%2FDenver", "&wind_speed_unit=ms"
lat = ",".join(str(a) for a, _ in SITES.values())
lon = ",".join(str(b) for _, b in SITES.values())
url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly={v}"
       f"&start_date={day}&end_date={day}&timezone={tz}{extra}")
with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "terra-live-check/0.1"}), timeout=60) as r:
    raw = json.load(r)
out = {"source": "Open-Meteo forecast API, best-match models", "fetched_utc": f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}",
       "date": day, "timezone": raw[0]["timezone"], "units": raw[0]["hourly_units"], "sites": {}}
for (name, (la, lo)), s in zip(SITES.items(), raw):
    h = s["hourly"]
    out["sites"][name] = {"requested_lat": la, "requested_lon": lo, "grid_lat": s["latitude"], "grid_lon": s["longitude"],
                          "elevation_m": s["elevation"], "hourly": [{k: h[k][i] for k in h} for i in range(len(h["time"]))]}
    i = max(range(len(h["time"])), key=lambda i: h["shortwave_radiation"][i] or 0)
    print(f"{name} {day}: Tmax {max(h['temperature_2m'])} C, peak sun {h['shortwave_radiation'][i]} W/m2 at {h['time'][i]}"
          f" ({raw[0]['timezone']}), mean cloud {sum(h['cloud_cover']) / len(h['cloud_cover']):.0f}%")
dest = Path(__file__).resolve().parent.parent / ("tomorrow_weather_model_units.json" if model else "tomorrow_weather.json")
dest.write_text(json.dumps(out, indent=1))
print(f"wrote {dest}")
