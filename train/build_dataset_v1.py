"""Build the router's training set from EIA-930 six-month files + Open-Meteo past forecasts.

One sample = (region, issue hour t). The model sees only what was knowable at t:
  past   48 h  demand / 30-day mean, gCO2/kWh / 1000, solar share, wind share
  future 24 h  EIA day-ahead demand forecast / 30-day mean, and weather FORECASTS
               (Open-Meteo historical-forecast API: temperature, cloud cover, sun)
  calendar     local hour, weekday, day of year (sin/cos)
It predicts, for each of the next 24 h:
  share   demand as a share of that local day's max demand
  peak    1 if share >= PEAK_SHARE (a tolerant "in the peak" label; the daily
          peak is a flat plateau, so exact top-2 hours are a coin flip)
  gco2    average gCO2/kWh of the in-region mix (IPCC lifecycle medians; not marginal)

Splits by time: train < 2025-07, val 2025-07..2025-12, test >= 2026-01.
Writes data/train/dataset.npz, data/train/hourly.parquet and prints data checks.
Run: uv run --with pandas --with numpy --with pyarrow python train/build_dataset.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "train"
REGIONS = {"PACE": "America/Denver", "CISO": "America/Los_Angeles", "BPAT": "America/Los_Angeles", "ERCO": "America/Chicago"}
PAST, FUT = 48, 24
PEAK_SHARE = 0.95
EF = {"COL": 820, "NG": 490, "NUC": 12, "OIL": 650, "WAT": 24, "SUN": 48, "WND": 11, "GEO": 38, "OTH": 500}
FUEL_KEYS = [("Coal", "COL"), ("Natural Gas", "NG"), ("Nuclear", "NUC"), ("Petroleum", "OIL"), ("Hydropower", "WAT"),
             ("Solar", "SUN"), ("Wind", "WND"), ("Geothermal", "GEO"), ("Other Fuel", "OTH"), ("Unknown Fuel", "OTH")]


def fuel_of(col):
    if "(Adjusted)" not in col or " from " not in col:
        return None
    # battery, pumped and other storage aren't generation; "Hydropower Excluding Pumped Storage" and
    # "Solar/Wind with Integrated Battery Storage" are
    if "Storage" in col and not any(k in col for k in ("Hydropower", "Solar", "Wind")):
        return None
    for key, code in FUEL_KEYS:
        if key in col:
            return code
    return None


def load_eia():
    frames = []
    for f in sorted((RAW / "eia930").glob("EIA930_BALANCE_*.csv")):
        df = pd.read_csv(f, low_memory=False, thousands=",")
        df = df[df["Balancing Authority"].isin(REGIONS)]
        out = pd.DataFrame({
            "ba": df["Balancing Authority"],
            # the file stamps hour END; shift to hour beginning
            "utc": pd.to_datetime(df["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p") - pd.Timedelta(hours=1),
            "demand": pd.to_numeric(df["Demand (MW) (Adjusted)"], errors="coerce").fillna(pd.to_numeric(df["Demand (MW)"], errors="coerce")),
            "forecast": pd.to_numeric(df["Demand Forecast (MW)"], errors="coerce"),
        })
        for code in set(EF):
            cols = [c for c in df.columns if fuel_of(c) == code]
            out[code] = df[cols].apply(pd.to_numeric, errors="coerce").clip(lower=0).sum(axis=1, min_count=1) if cols else np.nan
        frames.append(out)
    eia = pd.concat(frames).drop_duplicates(["ba", "utc"], keep="last")
    eia["utc"] = eia["utc"].dt.tz_localize("UTC")
    gen = eia[list(EF)].sum(axis=1, min_count=1)
    eia["gco2"] = sum(eia[c].fillna(0) * ef for c, ef in EF.items()) / gen
    eia["solar"] = eia["SUN"].fillna(0) / gen
    eia["wind"] = eia["WND"].fillna(0) / gen
    return eia[["ba", "utc", "demand", "forecast", "gco2", "solar", "wind"]]


def load_weather(ba):
    h = json.load(open(RAW / "weather" / f"{ba}.json"))["hourly"]
    w = pd.DataFrame({"utc": pd.to_datetime(h["time"]).tz_localize("UTC"), "temp": h["temperature_2m"],
                      "cloud": h["cloud_cover"], "sun": h["shortwave_radiation"]})
    return w.set_index("utc")


def region_frame(eia, ba):
    r = eia[eia["ba"] == ba].set_index("utc").sort_index()
    idx = pd.date_range(r.index.min(), r.index.max(), freq="h")
    r = r.reindex(idx)
    # short gaps only; long outages stay NaN and their samples get dropped
    for c in ("demand", "forecast", "gco2", "solar", "wind"):
        r[c] = r[c].interpolate(limit=3)
    r = r.join(load_weather(ba), how="left")
    r[["temp", "cloud", "sun"]] = r[["temp", "cloud", "sun"]].interpolate(limit=3)
    local = r.index.tz_convert(REGIONS[ba])
    r["local_day"] = local.normalize().tz_localize(None)
    r["hour"] = local.hour
    r["dow"] = local.dayofweek
    r["doy"] = local.dayofyear
    r["norm"] = r["demand"].rolling(24 * 30, min_periods=24 * 7).mean().shift(1)  # past-only scale
    r["day_max"] = r.groupby("local_day")["demand"].transform("max")
    r["share"] = r["demand"] / r["day_max"]
    r["peak"] = (r["share"] >= PEAK_SHARE).astype(float)
    # the EIA baseline uses the same rule on the day-ahead forecast: share of its own local-day max
    r["fc_share"] = r["forecast"] / r.groupby("local_day")["forecast"].transform("max")
    r.loc[r["demand"].isna(), ["share", "peak"]] = np.nan
    r["ba"] = ba
    return r


def forecast_lag_check(r, ba):
    """Is EIA's day-ahead forecast shifted against actual demand? (pitch claim check)"""
    prof = r.groupby("hour")[["demand", "forecast"]].mean()
    lags = {lag: float((r["demand"] - r["forecast"].shift(lag)).abs().mean()) for lag in range(-4, 5)}
    best = min(lags, key=lags.get)
    return {"peak_hour_actual": int(prof["demand"].idxmax()), "peak_hour_forecast": int(prof["forecast"].idxmax()),
            "best_lag_h": best, "mae_at_0": round(lags[0]), "mae_best": round(lags[best]),
            "mape_pct": round(float(((r["demand"] - r["forecast"]).abs() / r["demand"]).mean() * 100), 1)}


def samples(r, region_id):
    a = {k: r[k].to_numpy(dtype=np.float32) for k in ("demand", "forecast", "gco2", "solar", "wind", "temp", "cloud", "sun", "norm", "share", "peak", "fc_share")}
    n = len(r)
    t = np.arange(PAST, n - FUT)
    past_idx = t[:, None] + np.arange(-PAST, 0)[None]
    fut_idx = t[:, None] + np.arange(0, FUT)[None]
    norm = a["norm"][t][:, None]
    past = np.stack([a["demand"][past_idx] / norm, a["gco2"][past_idx] / 1000, a["solar"][past_idx], a["wind"][past_idx]], -1)
    fut = np.stack([a["forecast"][fut_idx] / norm, a["temp"][fut_idx] / 30, a["cloud"][fut_idx] / 100, a["sun"][fut_idx] / 1000], -1)
    hr, dw, dy = r["hour"].to_numpy()[t], r["dow"].to_numpy()[t], r["doy"].to_numpy()[t]
    cal = np.stack([np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24), np.sin(2 * np.pi * dw / 7), np.cos(2 * np.pi * dw / 7),
                    np.sin(2 * np.pi * dy / 365.25), np.cos(2 * np.pi * dy / 365.25)], -1).astype(np.float32)
    y_share, y_peak, y_gco2 = a["share"][fut_idx], a["peak"][fut_idx], a["gco2"][fut_idx] / 1000
    ok = (np.isfinite(past).all((1, 2)) & np.isfinite(fut).all((1, 2)) & np.isfinite(y_share).all(1)
          & np.isfinite(y_gco2).all(1) & np.isfinite(norm[:, 0]))
    utc = r.index[t].to_numpy(dtype="datetime64[s]").astype(np.int64)
    return dict(past=past[ok], fut=fut[ok], cal=cal[ok], region=np.full(ok.sum(), region_id, np.int64),
                y_share=y_share[ok], y_peak=y_peak[ok], y_gco2=y_gco2[ok], utc=utc[ok],
                # day-ahead forecast as a share of its own local-day max: the EIA baseline for "peak"
                base_share=a["fc_share"][fut_idx][ok])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    eia = load_eia()
    parts, hourly, checks = [], [], {}
    for i, ba in enumerate(REGIONS):
        r = region_frame(eia, ba)
        checks[ba] = forecast_lag_check(r, ba)
        hourly.append(r.drop(columns=["local_day"]).reset_index(names="utc"))
        s = samples(r, i)
        parts.append(s)
        print(f"{ba}: {len(r)} h ({r.index.min():%Y-%m-%d}..{r.index.max():%Y-%m-%d}), {len(s['utc'])} samples, "
              f"peak rate {np.nanmean(r['peak']):.2f}, gCO2 mean {r['gco2'].mean():.0f}")
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    t = pd.to_datetime(data["utc"], unit="s")
    data["split"] = np.where(t < "2025-07-01", 0, np.where(t < "2026-01-01", 1, 2)).astype(np.int8)
    np.savez_compressed(OUT / "dataset.npz", **data, regions=np.array(list(REGIONS)))
    pd.concat(hourly).to_parquet(OUT / "hourly.parquet")
    (OUT / "checks.json").write_text(json.dumps(checks, indent=2))
    print("split sizes (train/val/test):", np.bincount(data["split"]).tolist())
    print("EIA day-ahead forecast check:", json.dumps(checks, indent=1))


if __name__ == "__main__":
    main()
