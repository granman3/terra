"""CAISO Today's Outlook (www.caiso.com/outlook): 5-min demand, fuel mix and CO2 for the CAISO footprint, keyless.

The CSVs hold today in bare "HH:MM" Pacific rows, with blank future rows (the day-ahead forecast is filled for the
whole day), so take the last row with a value, not the last line. stats.txt is JSON despite the name.
NOT interchangeable with EIA-930 CISO demand: EIA's daytime CISO D runs ~5-8 GW higher than Outlook "Current demand"
(seen 10-25 and 10-27). The model was trained on EIA, so feed it EIA; use Outlook for the 5-min display only.
Run: python3 -I caiso_outlook.py
"""
import csv
import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = "https://www.caiso.com/outlook/current/"
PT = ZoneInfo("America/Los_Angeles")


def get(name):  # curl, not urllib: caiso.com's chain fails Python's bundled CA store (same as train/fetch_pace_lmp.py)
    raw = subprocess.run(["curl", "-sSf", "-m", "60", "-A", "terra-live-check/0.1", BASE + name],
                         capture_output=True, check=True).stdout
    return raw.decode("utf-8-sig")


today = datetime.now(PT).date()


def last_row(name, col):
    rows = [r for r in csv.DictReader(io.StringIO(get(name))) if r.get(col, "").strip()]
    r = rows[-1]
    hh, mm = map(int, r["Time"].split(":"))
    t = datetime(today.year, today.month, today.day, hh, mm, tzinfo=PT)
    return t.astimezone(timezone.utc), r


t, r = last_row("demand.csv", "Current demand")
print(f"CISO demand {r['Current demand']} MW at {t:%Y-%m-%d %H:%M} UTC (day-ahead fcst {r['Day ahead forecast']}, "
      f"hour-ahead {r['Hour ahead forecast']})")
t, r = last_row("fuelsource.csv", "Solar")
print(f"CISO fuel mix at {t:%H:%M} UTC: " + ", ".join(f"{k} {v}" for k, v in r.items() if k != "Time"))
t, r = last_row("co2.csv", "Natural Gas CO2")
print(f"CISO CO2 (metric tons/h) at {t:%H:%M} UTC: " + ", ".join(f"{k} {v}" for k, v in r.items() if k != "Time"))
s = json.loads(get("stats.txt"))
print(f"today's forecast peak {s.get('todayForecastPeakDemand')} MW, tomorrow's {s.get('tomorrowsForecastPeakDemand')} MW")
