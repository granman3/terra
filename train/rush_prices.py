"""What a kWh not used during Utah's rush hour is really worth, from public prices (replaces the old $0.50 guess).

Three sources, each a different view of the same kWh:
1. Wholesale: PACE real-time price (CAISO OASIS, train/fetch_pace_lmp.py), averaged over the 2026 hours that really
   were rush hour (demand within 5% of that day's high, the model's label). What the grid pays for that energy.
2. Rocky Mountain Power Schedule 9 (high voltage, effective 2026-08-10): on-peak energy charge. What a data center
   saves on its bill per kWh it doesn't draw on-peak (the on-peak demand charge is per kW-month and isn't counted).
3. Rocky Mountain Power Wattsmart Business demand response (Schedule 114): $100 per kW a year for up to 65 hours of
   cuts, so at least $100 / 65 h per kWh cut during an event. What the utility pays to have load cut at the peak.
Writes out/math/prices.json.
Run: uv run --with pandas --with pyarrow python train/rush_prices.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "math" / "prices.json"
SCHED9 = {"on_peak_cents_kwh": {"jun_sep": 5.5841, "oct_may": 4.9417}, "off_peak_cents_kwh": {"jun_sep": 2.8383, "oct_may": 2.5118},
          "on_peak_usd_kw_month": {"jun_sep": 15.54, "oct_may": 13.75}, "effective": "2026-08-10", "docket": "26-035-T08"}
DR = {"usd_per_kw_year": 100.0, "max_hours_year": 65}


def main():
    lmp = pd.read_csv(ROOT / "data" / "raw" / "caiso" / "pace_lmp_hourly_2026.csv", parse_dates=["utc"])
    h = pd.read_parquet(ROOT / "data" / "train" / "hourly_v2.parquet", columns=["utc", "ba", "peak"])
    h = h[(h.ba == "PACE") & (h.utc >= "2026-01-01")].merge(lmp, on="utc")
    usd = h.lmp_usd_mwh / 1000
    rush, other = usd[h.peak == 1], usd[h.peak == 0]
    week = h[(h.utc >= "2026-10-19T06:00Z") & (h.utc < "2026-10-26T06:00Z")]  # the dashboard's replay week, Mountain time
    out = {
        "source": "CAISO OASIS PRC_INTVL_LMP, RTM, ELAP_PACE-APND (5-minute, averaged per hour)",
        "hours": int(len(h)), "first": str(h.utc.min()), "last": str(h.utc.max()),
        "wholesale": {"rush_mean_usd_kwh": round(float(rush.mean()), 4), "other_mean_usd_kwh": round(float(other.mean()), 4),
                      "rush_median_usd_kwh": round(float(rush.median()), 4), "rush_p95_usd_kwh": round(float(rush.quantile(0.95)), 4),
                      "rush_hours": int(len(rush)), "rush_max5_usd_kwh": round(float(h.max5_usd_mwh[h.peak == 1].max() / 1000), 3),
                      "week_rush_mean_usd_kwh": round(float(week.lmp_usd_mwh[week.peak == 1].mean() / 1000), 4)},
        "schedule_9": SCHED9,
        "demand_response": {**DR, "usd_per_kwh_cut_at_max_hours": round(DR["usd_per_kw_year"] / DR["max_hours_year"], 3)},
        "week_hourly_usd_kwh": {str(int(t.timestamp())): round(v / 1000, 4) for t, v in zip(week.utc, week.lmp_usd_mwh)},
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "week_hourly_usd_kwh"}, indent=1))


if __name__ == "__main__":
    main()
