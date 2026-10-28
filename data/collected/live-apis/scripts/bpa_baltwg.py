"""BPA balancing authority (BPAT) 5-min load, wind+solar (VER), hydro, fossil/biomass, nuclear; last 7 days, keyless.
Tab-separated text with an 11-line preamble; times are Pacific (local, DST-aware); future rows are blank.
Run: python3 -I bpa_baltwg.py
"""
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://transmission.bpa.gov/business/operations/wind/baltwg.txt"
req = urllib.request.Request(URL, headers={"User-Agent": "terra-live-check/0.1"})
with urllib.request.urlopen(req, timeout=60) as r:
    lines = r.read().decode("latin-1").splitlines()
hdr_i = next(i for i, l in enumerate(lines) if l.startswith("Date/Time"))
cols = [c.strip() for c in lines[hdr_i].split("\t")]
rows = [l.split("\t") for l in lines[hdr_i + 1:]]
rows = [r for r in rows if len(r) >= 2 and r[1].strip()]
last = dict(zip(cols, [c.strip() for c in rows[-1]]))
t = datetime.strptime(last["Date/Time"], "%m/%d/%Y %H:%M").replace(tzinfo=ZoneInfo("America/Los_Angeles"))
print(f"BPAT at {t.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC: " + ", ".join(f"{k} {v} MW" for k, v in last.items()
                                                                               if k != "Date/Time"))
