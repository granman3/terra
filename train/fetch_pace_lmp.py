"""Real-time wholesale price for Utah's grid (PacifiCorp East) from CAISO OASIS, hourly, 2026 to date.

PACE prices in the Western Energy Imbalance Market at node ELAP_PACE-APND. OASIS is free and needs no key; it serves
5-minute real-time LMPs ($/MWh) in up to ~10-day requests and throttles fast callers, so requests are 6 s apart.
Writes data/raw/caiso/pace_lmp_hourly_2026.csv: utc hour start, mean LMP $/MWh, max 5-min LMP $/MWh.
Run: uv run --with pandas python train/fetch_pace_lmp.py
"""
import io
import subprocess
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "caiso" / "pace_lmp_hourly_2026.csv"
NODE, STEP = "ELAP_PACE-APND", timedelta(days=10)
URL = ("https://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_INTVL_LMP&version=3&market_run_id=RTM"
       f"&node={NODE}&resultformat=6&startdatetime={{a}}&enddatetime={{b}}")


def get(a, b, tries=4):
    url = URL.format(a=a.strftime("%Y%m%dT%H:%M-0000"), b=b.strftime("%Y%m%dT%H:%M-0000"))
    for k in range(tries):
        raw = subprocess.run(["curl", "-sS", "-m", "180", url], capture_output=True).stdout  # curl: system trust store
        if raw[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(raw))
            name = z.namelist()[0]
            if name.endswith(".csv"):
                return pd.read_csv(z.open(name))
        time.sleep(15 * (k + 1))  # throttled or an error XML: back off and retry
    raise RuntimeError(f"OASIS gave no data for {a:%Y-%m-%d}..{b:%Y-%m-%d}")


def main():
    start = datetime(2026, 1, 1, 7, tzinfo=timezone.utc)  # midnight Mountain Standard Time
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    parts, a = [], start
    while a < end:
        b = min(a + STEP, end)
        df = get(a, b)
        df = df[df["LMP_TYPE"] == "LMP"]
        parts.append(df[["INTERVALSTARTTIME_GMT", "VALUE"]])
        print(f"{a:%Y-%m-%d} .. {b:%Y-%m-%d}: {len(df)} five-minute prices", flush=True)
        a = b
        time.sleep(6)
    df = pd.concat(parts)
    df["utc"] = pd.to_datetime(df["INTERVALSTARTTIME_GMT"], utc=True).dt.floor("h")
    h = df.groupby("utc")["VALUE"].agg(lmp_usd_mwh="mean", max5_usd_mwh="max", n="size").reset_index()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    h.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(h)} hours, mean ${h.lmp_usd_mwh.mean():.2f}/MWh)")


if __name__ == "__main__":
    main()
