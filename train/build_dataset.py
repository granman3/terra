"""Build the router's training set (v2): 51 US grids, six kinds of public data.

  1 grid operations   EIA-930: hourly demand, EIA's day-ahead demand forecast, net interchange
  2 generation mix    EIA-930: hourly generation by fuel -> carbon intensity, solar and wind share
  3 weather forecasts Open-Meteo historical-forecast API (what was forecast at the time, no peeking):
                      temperature, humidity, dew point, cloud, sunlight, wind at 100 m, precipitation
  4 sun position      computed solar elevation for each grid's city, every hour
  5 calendar          local hour, weekday, season, US federal holidays
  6 energy markets    EIA daily wholesale power prices at 5 trading hubs + Henry Hub natural gas,
                      lagged one day (only what had already traded)

One sample = (grid, issue hour t), every 2nd UTC hour. The model sees only what was knowable at t:
  past 48 h   demand / 30-day mean, gCO2/kWh / 1000, solar share, wind share, net interchange / 30-day mean
  next 24 h   EIA forecast / 30-day mean, 7 weather forecasts, sun elevation, holiday flag
  cal, mkt    calendar sin/cos; yesterday's market prices
It predicts, for each of the next 24 h: share of that local day's max demand, peak (share >= 0.95),
and average gCO2/kWh (IPCC lifecycle medians; not marginal).

Splits by time: train < 2025-07, val 2025-07..2025-12, test >= 2026-01.
Writes data/train/dataset_v2.npz, hourly_v2.parquet, checks_v2.json.
Run: uv run --with pandas --with numpy --with pyarrow --with openpyxl --with xlrd --with holidays python train/build_dataset.py
"""
import json
import os
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

from fetch_weather import GRIDS, VARS as WEATHER_VARS

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "train"
ROUTE = ["PACE", "CISO", "BPAT", "ERCO"]  # jobs route between these; they come first so their indexes stay 0..3
REGIONS = {ba: GRIDS[ba][0] for ba in ROUTE + [b for b in GRIDS if b not in ROUTE]}
if os.environ.get("ONLY_AVAILABLE") == "1":  # test runs while the weather pull is still going
    REGIONS = {ba: tz for ba, tz in REGIONS.items() if (RAW / "weather2" / f"{ba}.json").exists()}
    print(f"ONLY_AVAILABLE: {len(REGIONS)} grids", flush=True)
PAST, FUT, STRIDE = 48, 24, 2
PEAK_SHARE = 0.95
EF = {"COL": 820, "NG": 490, "NUC": 12, "OIL": 650, "WAT": 24, "SUN": 48, "WND": 11, "GEO": 38, "OTH": 500}
FUEL_KEYS = [("Coal", "COL"), ("Natural Gas", "NG"), ("Nuclear", "NUC"), ("Petroleum", "OIL"), ("Hydropower", "WAT"),
             ("Solar", "SUN"), ("Wind", "WND"), ("Geothermal", "GEO"), ("Other Fuel", "OTH"), ("Unknown Fuel", "OTH")]
HUBS = {"Mid C Peak": "midc", "Palo Verde Peak": "pv", "SP15 EZ Gen DA LMP Peak": "sp15",
        "PJM WH Real Time Peak": "pjmw", "Nepool MH DA LMP Peak": "nepool"}
MKT = list(HUBS.values()) + ["henry_hub"]
PAST_CH = ["demand", "gco2", "solar", "wind", "interchange"]
FUT_CH = ["forecast"] + WEATHER_VARS + ["sun_elev", "holiday"]


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


def num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)


def load_eia():
    frames, raw_values = [], 0
    for f in sorted((RAW / "eia930").glob("EIA930_BALANCE_*.csv")):
        df = pd.read_csv(f, low_memory=False, thousands=",")
        df = df[df["Balancing Authority"].isin(REGIONS)]
        out = pd.DataFrame({
            "ba": df["Balancing Authority"],
            # the file stamps hour END; shift to hour beginning
            "utc": pd.to_datetime(df["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p") - pd.Timedelta(hours=1),
            "demand": num(df, "Demand (MW) (Adjusted)").fillna(num(df, "Demand (MW)")),
            "forecast": num(df, "Demand Forecast (MW)"),
            "interchange": num(df, "Total Interchange (MW) (Adjusted)").fillna(num(df, "Total Interchange (MW)")),
        })
        fuel_values = 0
        for code in set(EF):
            cols = [c for c in df.columns if fuel_of(c) == code]
            vals = df[cols].apply(pd.to_numeric, errors="coerce")
            fuel_values += int(vals.notna().sum().sum())  # reported values only, not blank cells
            out[code] = vals.clip(lower=0).sum(axis=1, min_count=1) if cols else np.nan
        raw_values += int(out[["demand", "forecast", "interchange"]].notna().sum().sum()) + fuel_values
        frames.append(out)
    eia = pd.concat(frames).drop_duplicates(["ba", "utc"], keep="last")
    eia["utc"] = eia["utc"].dt.tz_localize("UTC")
    gen = eia[list(EF)].sum(axis=1, min_count=1)
    eia["gco2"] = sum(eia[c].fillna(0) * ef for c, ef in EF.items()) / gen
    eia["solar"] = eia["SUN"].fillna(0) / gen
    eia["wind"] = eia["WND"].fillna(0) / gen
    return eia[["ba", "utc", "demand", "forecast", "interchange", "gco2", "solar", "wind"]], raw_values


def load_weather(ba):
    h = json.load(open(RAW / "weather2" / f"{ba}.json"))["hourly"]
    w = pd.DataFrame({v: h[v] for v in WEATHER_VARS}, dtype=float)
    w.index = pd.to_datetime(h["time"]).tz_localize("UTC")
    return w


def load_markets():
    """Daily prices by delivery day, shifted so day D only sees what was known by D-1."""
    e = pd.concat(pd.read_excel(f) for f in sorted((RAW / "prices").glob("ice_electric-*.xlsx")))
    e["day"] = pd.to_datetime(e["Delivery start date"], errors="coerce").dt.normalize()
    e = e[e["Price hub"].isin(HUBS)].pivot_table(index="day", columns="Price hub", values="Wtd avg price $/MWh", aggfunc="mean").rename(columns=HUBS)
    hh = pd.read_excel(RAW / "prices" / "RNGWHHDd.xls", sheet_name="Data 1", skiprows=2)
    hh = hh.set_axis(["day", "henry_hub"], axis=1).set_index("day")
    days = pd.date_range("2021-12-01", "2026-12-31", freq="D")
    m = e.join(hh, how="outer").reindex(days).ffill()[MKT]
    raw_values = int(e.notna().sum().sum() + hh.notna().sum().sum())
    return m.shift(1), raw_values


def sun_elevation(index, lat, lon):
    """sin(solar elevation), clipped at 0, from the NOAA approximation (good to ~0.5 degrees)."""
    t = index
    doy = t.dayofyear.to_numpy()
    hour = t.hour.to_numpy() + 0.5
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g) - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    ha = np.radians((hour * 60 + eqt + 4 * lon) / 4 - 180)
    la = np.radians(lat)
    return np.clip(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha), 0, None)


def region_frame(eia, ba, markets, us_holidays):
    tz, _, lat, lon = GRIDS[ba]
    r = eia[eia["ba"] == ba].set_index("utc").sort_index()
    idx = pd.date_range(r.index.min(), r.index.max(), freq="h")
    r = r.reindex(idx)
    # short gaps only; long outages stay NaN and their samples get dropped
    for c in ("demand", "forecast", "interchange", "gco2", "solar", "wind"):
        r[c] = r[c].interpolate(limit=3)
    r = r.join(load_weather(ba), how="left")
    r[WEATHER_VARS] = r[WEATHER_VARS].interpolate(limit=3)
    r["sun_elev"] = sun_elevation(r.index, lat, lon)
    local = r.index.tz_convert(tz)
    r["local_day"] = local.normalize().tz_localize(None)
    r["holiday"] = np.isin(r["local_day"].dt.date, list(us_holidays)).astype(float)
    r["hour"] = local.hour
    r["dow"] = local.dayofweek
    r["doy"] = local.dayofyear
    r = r.join(markets, on="local_day")
    r["norm"] = r["demand"].rolling(24 * 30, min_periods=24 * 7).mean().shift(1)  # past-only scale
    r["day_max"] = r.groupby("local_day")["demand"].transform("max")
    r["share"] = r["demand"] / r["day_max"]
    r["peak"] = (r["share"] >= PEAK_SHARE).astype(float)
    # the EIA baseline uses the same rule on the day-ahead forecast: share of its own local-day max
    r["fc_share"] = r["forecast"] / r.groupby("local_day")["forecast"].transform("max")
    r.loc[r["demand"].isna(), ["share", "peak"]] = np.nan
    r["ba"] = ba
    return r


def channels(r):
    """Per-hour model channels, scaled to roughly unit range (norm applied per sample)."""
    past = np.stack([r["demand"], r["gco2"] / 1000, r["solar"], r["wind"], r["interchange"]], -1).astype(np.float32)
    fut = np.stack([r["forecast"], r["temperature_2m"] / 30, r["relative_humidity_2m"] / 100, r["dew_point_2m"] / 30,
                    r["cloud_cover"] / 100, r["shortwave_radiation"] / 1000, r["wind_speed_100m"] / 50,
                    np.clip(r["precipitation"], 0, 10) / 5, r["sun_elev"], r["holiday"]], -1).astype(np.float32)
    mkt = np.stack([r[m] / (5 if m == "henry_hub" else 100) for m in MKT], -1).astype(np.float32)
    hr, dw, dy = r["hour"].to_numpy(), r["dow"].to_numpy(), r["doy"].to_numpy()
    cal = np.stack([np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24), np.sin(2 * np.pi * dw / 7), np.cos(2 * np.pi * dw / 7),
                    np.sin(2 * np.pi * dy / 365.25), np.cos(2 * np.pi * dy / 365.25)], -1).astype(np.float32)
    return past, fut, cal, mkt


def inputs_at(ch, norm, t):
    """Model inputs for issue hours t (array): past (n,48,5), fut (n,24,10), cal (n,6), mkt (n,6)."""
    past_c, fut_c, cal_c, mkt_c = ch
    past = past_c[t[:, None] + np.arange(-PAST, 0)[None]].copy()
    fut = fut_c[t[:, None] + np.arange(0, FUT)[None]].copy()
    n = norm[t][:, None]
    past[..., 0] /= n
    past[..., 4] /= n
    fut[..., 0] /= n
    return past, fut, cal_c[t], mkt_c[t]


def forecast_lag_check(r):
    """Is EIA's day-ahead forecast shifted against actual demand? (pitch claim check)"""
    prof = r.groupby("hour")[["demand", "forecast"]].mean()
    lags = {lag: float((r["demand"] - r["forecast"].shift(lag)).abs().mean()) for lag in range(-4, 5)}
    best = min(lags, key=lags.get)
    return {"peak_hour_actual": int(prof["demand"].idxmax()), "peak_hour_forecast": int(prof["forecast"].idxmax()),
            "best_lag_h": best, "mape_pct": round(float(((r["demand"] - r["forecast"]).abs() / r["demand"]).mean() * 100), 1)}


def samples(r, region_id):
    n = len(r)
    t = np.arange(PAST, n - FUT)
    t = t[(r.index[t].hour % STRIDE) == 0]
    norm = r["norm"].to_numpy(np.float32)
    past, fut, cal, mkt = inputs_at(channels(r), norm, t)
    a = {k: r[k].to_numpy(np.float32) for k in ("share", "peak", "gco2", "fc_share")}
    fut_idx = t[:, None] + np.arange(0, FUT)[None]
    y_share, y_peak, y_gco2 = a["share"][fut_idx], a["peak"][fut_idx], a["gco2"][fut_idx] / 1000
    ok = (np.isfinite(past).all((1, 2)) & np.isfinite(fut).all((1, 2)) & np.isfinite(mkt).all(1)
          & np.isfinite(y_share).all(1) & np.isfinite(y_gco2).all(1) & np.isfinite(norm[t]) & (norm[t] > 0))
    utc = r.index[t].to_numpy(dtype="datetime64[s]").astype(np.int64)
    return dict(past=past[ok], fut=fut[ok], cal=cal[ok], mkt=mkt[ok], region=np.full(ok.sum(), region_id, np.int64),
                y_share=y_share[ok], y_peak=y_peak[ok], y_gco2=y_gco2[ok], utc=utc[ok],
                # day-ahead forecast as a share of its own local-day max: the EIA baseline for "peak"
                base_share=a["fc_share"][fut_idx][ok])


def us_holiday_days():
    return holidays.US(years=range(2021, 2028))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    eia, eia_values = load_eia()
    markets, market_values = load_markets()
    us_holidays = us_holiday_days()
    parts, hourly, checks = [], [], {}
    weather_values = 0
    for i, ba in enumerate(REGIONS):
        r = region_frame(eia, ba, markets, us_holidays)
        weather_values += int(r[WEATHER_VARS].notna().sum().sum())
        checks[ba] = forecast_lag_check(r)
        hourly.append(r.drop(columns=["local_day"]).reset_index(names="utc"))
        s = samples(r, i)
        parts.append(s)
        print(f"{ba}: {len(r)} h ({r.index.min():%Y-%m-%d}..{r.index.max():%Y-%m-%d}), {len(s['utc'])} samples, "
              f"peak rate {np.nanmean(r['peak']):.2f}, gCO2 mean {r['gco2'].mean():.0f}", flush=True)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    t = pd.to_datetime(data["utc"], unit="s")
    data["split"] = np.where(t < "2025-07-01", 0, np.where(t < "2026-01-01", 1, 2)).astype(np.int8)
    np.savez(OUT / "dataset_v2.npz", **data, regions=np.array(list(REGIONS)), past_ch=np.array(PAST_CH), fut_ch=np.array(FUT_CH), mkt_ch=np.array(MKT))
    pd.concat(hourly).to_parquet(OUT / "hourly_v2.parquet")
    holiday_days = sum(1 for d in us_holidays if pd.Timestamp("2022-01-01").date() <= d <= pd.Timestamp("2026-10-26").date())
    counts = {
        "grids": sum(1 for p in parts if len(p["utc"])), "data_types": 6,  # grids that produced training samples
        "raw_values": {"eia930": eia_values, "weather_forecasts": weather_values, "markets": market_values,
                       "sun_position": int(sum(len(h) for h in hourly)), "holidays": holiday_days},
        "features_per_sample": int(PAST * len(PAST_CH) + FUT * len(FUT_CH) + 6 + len(MKT)),
        "samples": np.bincount(data["split"]).tolist(), "hours_of_grid_history": int(sum(len(h) for h in hourly)),
    }
    # headline count: downloaded public values only (sun position is computed, so it is listed but not counted)
    counts["raw_values"]["total"] = sum(v for k, v in counts["raw_values"].items() if k != "sun_position")
    (OUT / "checks_v2.json").write_text(json.dumps({"counts": counts, "eia_forecast": checks}, indent=2))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
