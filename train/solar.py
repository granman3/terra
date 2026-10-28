"""Utah solar forecaster: tomorrow's PACE solar output (MW) from weather forecasts where the panels are.

Target   EIA-930 PACE net generation from solar (with and without integrated storage), hourly.
Inputs   archived Open-Meteo forecasts (no peeking) at Milford, Cedar City and Delta, plus Salt Lake City
         from the main dataset; sun elevation; season. Output is a share of recent capacity (the trailing
         30-day max, known a day ahead), so the model doesn't have to learn that Utah keeps adding panels.
Baseline persistence: the same hour yesterday, the standard day-ahead solar baseline.
Splits   same as the main model: train < 2025-07, test >= 2026-01.

Bands: adaptive conformal inference (train/conformal.py) on |error| / capacity, calibrated on 2025 H2 daylight
hours, then run through 2026 in time order with each hour's forecast treated as made a day ahead. 90% target.

Writes out/solar/metrics.json, data/train/solar_replay.json (the live map's replay week) and, with the
live Open-Meteo forecast, out/solar/tomorrow.json.
Run: uv run --with pandas --with numpy --with scikit-learn --with pyarrow python train/solar.py
"""
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from build_dataset import fuel_of, sun_elevation
from conformal import aci, split_q
from fetch_solar_sites import SITES, VARS

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "out" / "solar"
SLC = ["cloud_cover", "shortwave_radiation"]
TZ = "America/Denver"


def load_solar():
    frames = []
    for f in sorted((RAW / "eia930").glob("EIA930_BALANCE_*.csv")):
        df = pd.read_csv(f, low_memory=False, thousands=",")
        df = df[df["Balancing Authority"] == "PACE"]
        cols = [c for c in df.columns if fuel_of(c) == "SUN"]
        frames.append(pd.DataFrame({
            # the file stamps hour END; shift to hour beginning (same as build_dataset.py)
            "utc": pd.to_datetime(df["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p") - pd.Timedelta(hours=1),
            "mw": df[cols].apply(pd.to_numeric, errors="coerce").clip(lower=0).sum(axis=1, min_count=1),
        }))
    s = pd.concat(frames).drop_duplicates("utc", keep="last").set_index("utc")["mw"].sort_index()
    s.index = s.index.tz_localize("UTC")
    return s.asfreq("h")


def weather_frame(hourly, prefix, cols):
    w = pd.DataFrame({f"{prefix}_{v}": hourly[v] for v in cols}, dtype=float)
    # Open-Meteo radiation is the mean over the hour BEFORE its stamp; EIA hours are stamped at the start
    w.index = pd.to_datetime(hourly["time"]).tz_localize("UTC") - pd.Timedelta(hours=1)
    return w


def features(idx, weather):
    x = weather.reindex(idx)
    lat, lon = SITES["milford"]
    x["sun"] = sun_elevation(idx, lat, lon)
    local = idx.tz_convert(TZ)
    x["hour"] = local.hour
    doy = local.dayofyear.to_numpy()
    x["doy_s"], x["doy_c"] = np.sin(2 * np.pi * doy / 365), np.cos(2 * np.pi * doy / 365)
    return x


def all_weather():
    parts = [weather_frame(json.load(open(RAW / "solar_sites" / f"{s}.json"))["hourly"], s, VARS) for s in SITES]
    parts.append(weather_frame(json.load(open(RAW / "weather2" / "PACE.json"))["hourly"], "slc", SLC))
    return pd.concat(parts, axis=1)


def capacity(mw):
    """Trailing 30-day max of daily peaks, lagged one day: what an operator knew the evening before."""
    daily = mw.tz_convert(TZ).resample("D").max()
    cap = daily.rolling(30, min_periods=10).max().shift(1)
    cap.index = cap.index.tz_convert("UTC")
    return cap.reindex(mw.index, method="ffill")


def scores(pred, actual, cap, day):
    m = day & actual.notna() & pred.notna()
    err = (pred[m] - actual[m]).abs()
    return {"mae_mw": round(float(err.mean()), 1), "nmae_pct": round(float((err / cap[m]).mean() * 100), 2), "hours": int(m.sum())}


def live_forecast(cap_mw, model, cols):
    """Tomorrow from today's Open-Meteo run (api.open-meteo.com), same sites and variables."""
    parts = []
    for s, (lat, lon) in {**SITES, "slc": (40.76, -111.89)}.items():
        v = SLC if s == "slc" else VARS
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly={','.join(v)}"
               f"&forecast_days=3&timezone=GMT")
        with urllib.request.urlopen(url, timeout=60) as r:
            parts.append(weather_frame(json.load(r)["hourly"], s, v))
        time.sleep(1)
    w = pd.concat(parts, axis=1)
    tomorrow = (pd.Timestamp.now(tz=TZ).normalize() + pd.Timedelta(days=1))
    idx = pd.date_range(tomorrow, periods=24, freq="h").tz_convert("UTC")
    p = np.clip(model.predict(features(idx, w)[cols]), 0, 1.1) * cap_mw
    local = idx.tz_convert(TZ)
    k = int(np.argmax(p))
    return {"date": f"{tomorrow:%Y-%m-%d}", "peak_mw": round(float(p[k])), "peak_hour": int(local[k].hour),
            "mwh": round(float(p.sum())), "capacity_mw": round(float(cap_mw)),
            "hours": [{"hour": int(h.hour), "mw": round(float(v))} for h, v in zip(local, p)],
            "source": "Open-Meteo forecast run of " + f"{pd.Timestamp.now(tz=TZ):%Y-%m-%d %H:%M} MT"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mw = load_solar()
    cap = capacity(mw)
    weather = all_weather()
    x = features(mw.index, weather)
    cols = list(x.columns)
    y = mw / cap
    day = x["sun"] > 0.05
    ok = y.notna() & cap.gt(50) & x.notna().all(axis=1)
    train = ok & (mw.index < "2025-07-01")
    test = ok & (mw.index >= "2026-01-01")

    t0 = time.time()
    model = HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05, max_leaf_nodes=48, random_state=0)
    model.fit(x[train][cols], y[train].clip(0, 1.1))
    fit_s = time.time() - t0
    pred = pd.Series(np.clip(model.predict(x[cols].fillna(0)), 0, 1.1), index=mw.index) * cap
    pred[~x.notna().all(axis=1)] = np.nan

    persist = mw.shift(24)
    # what the forecast would be with Salt Lake City weather only (the main model's one city per grid)
    slc_cols = [c for c in cols if c.startswith("slc_") or c in ("sun", "hour", "doy_s", "doy_c")]
    slc_model = HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05, max_leaf_nodes=48, random_state=0)
    slc_model.fit(x[train][slc_cols], y[train].clip(0, 1.1))
    slc_pred = pd.Series(np.clip(slc_model.predict(x[slc_cols].fillna(0)), 0, 1.1), index=mw.index) * cap

    td = test & day
    m = {"model": scores(pred, mw, cap, td), "persistence": scores(persist, mw, cap, td),
         "slc_weather_only": scores(slc_pred, mw, cap, td)}
    m["skill_vs_persistence_pct"] = round((1 - m["model"]["mae_mw"] / m["persistence"]["mae_mw"]) * 100, 1)
    m["fit_seconds"] = round(fit_s, 1)
    m["capacity_mw_latest"] = round(float(cap.dropna().iloc[-1]))
    m["capacity_mw_2022"] = round(float(cap.dropna().iloc[0]))
    m["test"] = "daylight hours, 2026-01-01 onward"
    # cloudy days are where a forecast earns its keep: test days whose solar came in under 60% of capacity
    dmax = (mw / cap).tz_convert(TZ).resample("D").max()
    cloudy_days = set(dmax[dmax < 0.6].index.date)
    cl = td & pd.Series([d in cloudy_days for d in mw.index.tz_convert(TZ).date], index=mw.index)
    m["cloudy_days"] = {"days": len({d for d, c in zip(mw.index.tz_convert(TZ).date, cl) if c}),
                        "model": scores(pred, mw, cap, cl), "persistence": scores(persist, mw, cap, cl)}
    # 90% bands: split conformal for reference, adaptive conformal for use
    val_day = ok & day & (mw.index >= "2025-07-01") & (mw.index < "2026-01-01")
    score = ((pred - mw).abs() / cap)
    s_cal = score[val_day].to_numpy()
    tt = test & day & pred.notna()
    tgt = ((mw.index[tt] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy()  # unit-safe epoch seconds
    q_aci, _ = aci(s_cal, score[tt].to_numpy(), tgt - 86400, tgt, 0.10, gamma=0.005, window=2000)
    q_split = split_q(s_cal, 0.10)
    band = pd.Series(np.nan, index=mw.index)
    band[tt] = q_aci
    m["band_90"] = {"split": {"q_share_of_capacity": round(q_split, 4), "test_coverage": round(float((score[tt] <= q_split).mean()), 4)},
                    "adaptive": {"test_coverage": round(float((score[tt].to_numpy() <= q_aci).mean()), 4),
                                 "latest_q_share_of_capacity": round(float(q_aci[-1]), 4)}}
    (OUT / "metrics.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))

    # the live map's replay week (and a day past it, for the 24 h look-ahead)
    rp = json.load(open(ROOT / "data" / "train" / "replay_v2.json"))
    utcs = [h["utc"] for h in rp["hours"]["PACE"]]
    idx = pd.date_range(pd.Timestamp(min(utcs), unit="s", tz="UTC"), pd.Timestamp(max(utcs), unit="s", tz="UTC") + pd.Timedelta(hours=24), freq="h")
    half = (band * cap).reindex(idx)
    rows = [{"utc": int(t.timestamp()), "pred": None if np.isnan(p) else round(float(p)), "actual": None if np.isnan(a) else round(float(a)),
             "band": None if np.isnan(b) else round(float(b))}
            for t, p, a, b in zip(idx, pred.reindex(idx), mw.reindex(idx), half)]
    (ROOT / "data" / "train" / "solar_replay.json").write_text(json.dumps({"capacity_mw": round(float(cap.reindex(idx).dropna().iloc[-1])), "hours": rows}))

    try:
        tm = live_forecast(float(cap.dropna().iloc[-1]), model, cols)
        tm["band_mw"] = round(float(q_aci[-1] * cap.dropna().iloc[-1]))  # +/- per daylight hour, 90% (adaptive)
        (OUT / "tomorrow.json").write_text(json.dumps(tm, indent=1))
        print("tomorrow", tm["date"], tm["peak_mw"], "MW at", tm["peak_hour"], "h,", tm["mwh"], "MWh")
    except Exception as e:  # the replay and metrics stand on their own
        print("live forecast failed:", e)


if __name__ == "__main__":
    main()
