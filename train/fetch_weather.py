"""Pull archived weather FORECASTS (Open-Meteo historical-forecast API) for one city per grid.

Past forecasts, not observed weather, so the model never sees what it couldn't have known.
One file per grid in data/raw/weather2/, skipped if already there, so a partial pull isn't lost.
Run: uv run python train/fetch_weather.py [BA ...]
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "weather2"
VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "cloud_cover", "shortwave_radiation",
        "wind_speed_100m", "precipitation"]
START, END = "2022-01-01", "2026-10-26"

# balancing authority -> (time zone, representative city, lat, lon); the city sits in the grid's main load
GRIDS = {
    "PJM": ("America/New_York", "Baltimore", 39.29, -76.61), "MISO": ("America/Chicago", "Indianapolis", 39.77, -86.16),
    "ERCO": ("America/Chicago", "Dallas", 32.78, -96.80), "SWPP": ("America/Chicago", "Oklahoma City", 35.47, -97.52),
    "SOCO": ("America/New_York", "Atlanta", 33.75, -84.39), "CISO": ("America/Los_Angeles", "Fresno", 36.75, -119.77),
    "TVA": ("America/Chicago", "Nashville", 36.16, -86.78), "NYIS": ("America/New_York", "New York", 40.71, -74.01),
    "FPL": ("America/New_York", "Miami", 25.76, -80.19), "ISNE": ("America/New_York", "Boston", 42.36, -71.06),
    "DUK": ("America/New_York", "Charlotte", 35.23, -80.84), "BPAT": ("America/Los_Angeles", "Portland", 45.52, -122.68),
    "CPLE": ("America/New_York", "Raleigh", 35.78, -78.64), "FPC": ("America/New_York", "St. Petersburg", 27.77, -82.64),
    "PACE": ("America/Denver", "Salt Lake City", 40.76, -111.89), "WACM": ("America/Denver", "Cheyenne", 41.14, -104.82),
    "PSCO": ("America/Denver", "Denver", 39.74, -104.99), "NEVP": ("America/Los_Angeles", "Las Vegas", 36.17, -115.14),
    "LGEE": ("America/New_York", "Louisville", 38.25, -85.76), "AZPS": ("America/Phoenix", "Phoenix", 33.45, -112.07),
    "SRP": ("America/Phoenix", "Mesa", 33.42, -111.83), "SC": ("America/New_York", "Moncks Corner", 33.20, -80.01),
    "PSEI": ("America/Los_Angeles", "Bellevue", 47.61, -122.20), "SCEG": ("America/New_York", "Columbia SC", 34.00, -81.03),
    "PGE": ("America/Los_Angeles", "Salem", 44.94, -123.04), "LDWP": ("America/Los_Angeles", "Los Angeles", 34.05, -118.24),
    "TEC": ("America/New_York", "Tampa", 27.95, -82.46), "AECI": ("America/Chicago", "Springfield MO", 37.21, -93.29),
    "PACW": ("America/Los_Angeles", "Medford", 42.33, -122.87), "FMPP": ("America/New_York", "Orlando", 28.54, -81.38),
    "IPCO": ("America/Boise", "Boise", 43.62, -116.20), "BANC": ("America/Los_Angeles", "Sacramento", 38.58, -121.49),
    "PNM": ("America/Denver", "Albuquerque", 35.08, -106.65), "TEPC": ("America/Phoenix", "Tucson", 32.22, -110.97),
    "JEA": ("America/New_York", "Jacksonville", 30.33, -81.66), "AVA": ("America/Los_Angeles", "Spokane", 47.66, -117.43),
    "NWMT": ("America/Denver", "Billings", 45.78, -108.50), "SCL": ("America/Los_Angeles", "Seattle", 47.61, -122.33),
    "EPE": ("America/Denver", "El Paso", 31.76, -106.49), "WALC": ("America/Phoenix", "Kingman", 35.19, -114.05),
    "GCPD": ("America/Los_Angeles", "Moses Lake", 47.13, -119.28), "CPLW": ("America/New_York", "Asheville", 35.60, -82.55),
    "TPWR": ("America/Los_Angeles", "Tacoma", 47.25, -122.44), "IID": ("America/Los_Angeles", "El Centro", 32.79, -115.56),
    "TAL": ("America/New_York", "Tallahassee", 30.44, -84.28), "TIDC": ("America/Los_Angeles", "Turlock", 37.49, -120.85),
    "DOPD": ("America/Los_Angeles", "East Wenatchee", 47.42, -120.29), "GVL": ("America/New_York", "Gainesville", 29.65, -82.32),
    "CHPD": ("America/Los_Angeles", "Wenatchee", 47.42, -120.31), "HST": ("America/New_York", "Homestead", 25.47, -80.48),
    "WAUW": ("America/Denver", "Miles City", 46.41, -105.84),
}


def fetch(ba):
    _, _, lat, lon = GRIDS[ba]
    url = (f"https://historical-forecast-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&start_date={START}&end_date={END}&hourly={','.join(VARS)}&timezone=GMT")
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code not in (429, 500, 502, 503, 504):
                raise
            wait = 60 * (attempt + 1)
            print(f"  {ba}: {type(e).__name__} {getattr(e, 'code', '')}, waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{ba}: gave up after retries")


def main(bas):
    OUT.mkdir(parents=True, exist_ok=True)
    for ba in bas:
        f = OUT / f"{ba}.json"
        if f.exists():
            continue
        j = fetch(ba)
        h = j["hourly"]
        missing = {v: sum(x is None for x in h[v]) for v in VARS}
        f.write_text(json.dumps(j))
        print(f"{ba} ({GRIDS[ba][1]}): {len(h['time'])} h, nulls {missing}", flush=True)
        time.sleep(8)


if __name__ == "__main__":
    main(sys.argv[1:] or list(GRIDS))
