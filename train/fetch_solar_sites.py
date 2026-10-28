"""Pull archived weather FORECASTS for Utah's solar country, for the solar forecaster (train/solar.py).

The main model reads one city per grid (Salt Lake City for PACE), but Utah's utility-scale solar sits in
the south and west deserts, so this adds three sites there. Same API and window as fetch_weather.py,
plus the direct/diffuse split. One file per site in data/raw/solar_sites/, skipped if already there.
Run: uv run python train/fetch_solar_sites.py
"""
import json
import time
import urllib.request
from pathlib import Path

from fetch_weather import END, START

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "solar_sites"
VARS = ["shortwave_radiation", "direct_radiation", "diffuse_radiation", "cloud_cover", "temperature_2m"]
# site -> (lat, lon); towns next to Utah's big solar clusters
SITES = {
    "milford": (38.40, -113.01),  # Beaver County
    "cedar_city": (37.68, -113.06),  # Iron County
    "delta": (39.35, -112.58),  # Millard County
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for site, (lat, lon) in SITES.items():
        f = OUT / f"{site}.json"
        if f.exists():
            continue
        url = (f"https://historical-forecast-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&start_date={START}&end_date={END}&hourly={','.join(VARS)}&timezone=GMT")
        with urllib.request.urlopen(url, timeout=180) as r:
            j = json.load(r)
        f.write_text(json.dumps(j))
        print(f"{site}: {len(j['hourly']['time'])} h", flush=True)
        time.sleep(8)


if __name__ == "__main__":
    main()
