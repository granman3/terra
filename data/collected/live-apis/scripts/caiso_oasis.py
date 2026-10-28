"""CAISO OASIS (oasis.caiso.com), keyless. Three queries, one zip (CSV inside) each:
  rtm   PRC_INTVL_LMP RTM: 5-min real-time LMP $/MWh, last 2 h, for PACE (ELAP_PACE-APND) + CAISO NP15/SP15 hubs
  dam   PRC_LMP DAM: tomorrow's hourly day-ahead LMP (published ~1 PM Pacific the day before)
  load  SLD_FCST DAM: tomorrow's hourly load forecast by TAC area (CA ISO-TAC, PACE, PACW, BPAT and other WEIM BAs)
OASIS throttles fast callers: keep >=5 s between requests. Times are GMT.
Run: python3 -I caiso_oasis.py [rtm|dam|load ...] [YYYY-MM-DD]  (default: all three; dam/load default to tomorrow,
     pass a date, e.g. today's, to compare the day-ahead numbers with what is happening)
"""
import csv
import io
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NODES = "ELAP_PACE-APND,TH_NP15_GEN-APND,TH_SP15_GEN-APND"
B = "https://oasis.caiso.com/oasisapi/SingleZip?resultformat=6"
F = "%Y%m%dT%H:%M-0000"


def get(q):
    # curl, not urllib: caiso.com's chain fails Python's bundled CA store (same as train/fetch_pace_lmp.py)
    raw = subprocess.run(["curl", "-sSf", "-m", "180", "-A", "terra-live-check/0.1", B + q],
                         capture_output=True, check=True).stdout
    if raw[:2] != b"PK":
        raise RuntimeError(f"OASIS returned non-zip: {raw[:200]!r}")
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = z.namelist()[0]
    if not name.endswith(".csv"):
        raise RuntimeError(f"OASIS returned {name} (error XML: throttled or bad query)")
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8")))


now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
pt = ZoneInfo("America/Los_Angeles")
dates = [a for a in sys.argv[1:] if a[:1].isdigit()]
tom = datetime.strptime(dates[0], "%Y-%m-%d").date() if dates else (datetime.now(pt) + timedelta(days=1)).date()
t0 = datetime(tom.year, tom.month, tom.day, tzinfo=pt).astimezone(timezone.utc)
t1 = t0 + timedelta(days=1)
which = [a for a in sys.argv[1:] if not a[:1].isdigit()] or ["rtm", "dam", "load"]
for i, w in enumerate(which):
    if i:
        time.sleep(6)
    if w == "rtm":
        rows = [r for r in get(f"&queryname=PRC_INTVL_LMP&version=3&market_run_id=RTM&node={NODES}"
                                f"&startdatetime={(now - timedelta(hours=2)):{F}}&enddatetime={now:{F}}")
                if r["LMP_TYPE"] == "LMP"]
        for n in NODES.split(","):
            r = max((r for r in rows if r["NODE"] == n), key=lambda r: r["INTERVALSTARTTIME_GMT"])
            print(f"RTM {n}: ${float(r['VALUE']):.2f}/MWh, 5-min interval starting {r['INTERVALSTARTTIME_GMT']}")
    elif w == "dam":
        rows = [r for r in get(f"&queryname=PRC_LMP&version=12&market_run_id=DAM&node={NODES}"
                                f"&startdatetime={t0:{F}}&enddatetime={t1:{F}}") if r["LMP_TYPE"] == "LMP"]
        for n in NODES.split(","):
            xs = sorted((r for r in rows if r["NODE"] == n), key=lambda r: r["INTERVALSTARTTIME_GMT"])
            hi = max(xs, key=lambda r: float(r["MW"]))
            print(f"DAM {tom} {n}: {len(xs)} h, peak ${float(hi['MW']):.2f}/MWh at {hi['INTERVALSTARTTIME_GMT']}")
    elif w == "load":
        rows = get(f"&queryname=SLD_FCST&version=1&market_run_id=DAM&startdatetime={t0:{F}}&enddatetime={t1:{F}}")
        for tac in ("CA ISO-TAC", "PACE", "BPAT"):
            xs = [r for r in rows if r["TAC_AREA_NAME"] == tac]
            hi = max(xs, key=lambda r: float(r["MW"]))
            print(f"DAM load fcst {tom} {tac}: {len(xs)} h, peak {float(hi['MW']):.0f} MW at {hi['INTERVALSTARTTIME_GMT']}")
