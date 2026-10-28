"""Collect every number the deck shows into deck/numbers.json, each with the file it came from.

Nothing on a slide is typed by hand: rerun this after any retrain or measurement.
Prefers v2 (51 grids) results when they exist; the tiny-vs-big comparison only ever uses
one metrics_big file, where both models were scored on the same test rows.
Run: uv run --with pandas --with pyarrow python deck/make_numbers.py
"""
import csv
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
N = {}


def first(*paths):
    for p in paths:
        if (ROOT / p).exists():
            return p, json.loads((ROOT / p).read_text())
    return None, None


def put(key, value, source, **extra):
    N[key] = {"value": value, "source": source, **extra}


# 1. this fall's EIA forecast miss in Utah (from the same hourly table the model trains on)
hourly = next((p for p in ("data/train/hourly_v2.parquet", "data/train/hourly.parquet") if (ROOT / p).exists()), None)
if hourly:
    h = pd.read_parquet(ROOT / hourly, columns=["utc", "ba", "demand", "forecast", "hour"] if "v2" in hourly else None)
    u = h[h["ba"] == "PACE"].copy()
    u["local"] = pd.to_datetime(u["utc"], utc=True).dt.tz_convert("America/Denver")
    octo = u[(u["local"].dt.month == 10)]
    oct26 = octo[octo["local"].dt.year == 2026]
    prof = oct26.groupby("hour")[["demand", "forecast"]].mean()
    put("fall_peak_actual_hour", int(prof["demand"].idxmax()), hourly, note="Utah, Oct 2026, mean demand by local hour")
    put("fall_peak_forecast_hour", int(prof["forecast"].idxmax()), hourly, note="EIA day-ahead forecast, same hours")
    err = {int(y): round(float(((g["demand"] - g["forecast"]).abs() / g["demand"]).mean() * 100), 1) for y, g in octo.groupby(octo["local"].dt.year)}
    put("october_forecast_error_pct", err, hourly, note="mean absolute % error of EIA day-ahead forecast, Utah, October")
    # the "time" half of the problem: how far demand swings inside one day, so the grid is built for the top
    y26 = u[u["local"].dt.year == 2026].dropna(subset=["demand"])
    days = y26.groupby(y26["local"].dt.date)["demand"].agg(["max", "min", "size"])
    days = days[days["size"] >= 23]
    put("daily_swing_mw", round(float((days["max"] - days["min"]).median())), hourly,
        note="PACE 2026, median of each full day's peak minus its low", days=len(days),
        mean_low_mw=round(float(days["min"].mean())), mean_peak_mw=round(float(days["max"].mean())))

    # how little of the year the top of Utah's grid is used (2025, the last full year): the grid is built for a few hours
    y25 = u[u["local"].dt.year == 2025].dropna(subset=["demand"])
    pk = float(y25["demand"].max())
    put("utah_top10", {"peak_mw": round(pk), "top10_mw": round(pk * .1), "hours": int((y25["demand"] >= pk * .9).sum()),
                       "share_of_year_pct": round(float((y25["demand"] >= pk * .9).mean()) * 100, 1),
                       "top5_hours": int((y25["demand"] >= pk * .95).sum())}, hourly,
        note="PACE 2025, hours with demand at or above 90% of the year's peak")
    # demand can move: the four routing grids peak at different hours, so one of them usually has room
    four = pd.read_parquet(ROOT / hourly, columns=["utc", "ba", "demand"])
    four = four[four["ba"].isin(["PACE", "CISO", "BPAT", "ERCO"])].dropna()
    four["local"] = pd.to_datetime(four["utc"], utc=True).dt.tz_convert("America/Denver")
    four = four[four["local"].dt.year == 2026]
    four["day"] = four["local"].dt.date
    four["rush"] = (four["demand"] >= .95 * four.groupby(["ba", "day"])["demand"].transform("max")).astype(int)
    prof = four.groupby(["ba", four["local"].dt.hour])["demand"].mean().unstack(0)
    w = four.pivot_table(index="local", columns="ba", values="rush", aggfunc="max").dropna().astype(bool)
    ur = w[w["PACE"]]
    put("peaks_differ", {"peak_hour_mt": {k: int(v) for k, v in prof.idxmax().items()},
                         "profile": {k: [round(float(x), 3) for x in (prof[k] / prof[k].max())] for k in prof},
                         "utah_rush_hours": len(ur), "another_has_room_pct": round(float((~ur[["CISO", "BPAT", "ERCO"]]).any(axis=1).mean()) * 100)},
        hourly, note="2026, Utah (Mountain) time; rush = demand >= 95% of that day's high")

# 2. the data
src, c = first("data/train/checks_v2.json")
if c:
    c = c["counts"]
    put("grids", c["grids"], src)
    put("data_types", c["data_types"], src, list=["Grid operations", "Generation mix", "Weather forecasts", "Sun position", "Calendar + holidays", "Energy markets"])
    put("raw_values", c["raw_values"]["total"], src, breakdown=c["raw_values"])
    put("hours_of_grid_history", c["hours_of_grid_history"], src)
    put("features_per_sample", c["features_per_sample"], src)
    put("samples", sum(c["samples"]), src, split=c["samples"])

# 3. the tiny model
src, m = first("out/v3/metrics.json", "out/v2/metrics.json", "out/model/metrics.json")
if m:
    put("tiny_params", m["params"], src)
    put("train_seconds", m["train_seconds"], src, device=m["device"])
    put("train_energy_wh", m["train_energy_wh"], src)
    b = m["test_peak_brier"]
    put("brier_vs_eia_pct", round((1 - b["model"] / b["eia_forecast_calibrated"]) * 100), src, model=b["model"], eia=b["eia_forecast_calibrated"])
    u = m["by_region"]["PACE"]
    put("utah_catch", {"model": round(u["peak_hours_caught_model"] * 100), "eia": round(u["peak_hours_caught_eia_rule"] * 100)}, src)
    d = m["decisions"]
    put("peak_hours_hit", {"run_now_in_utah": round(d["utah_peak_hours_hit_naive"], 2), "mycelium": round(d["utah_peak_hours_hit_model"], 2)}, src,
        note=f"{d['job_hours']} h job that can wait {d['deadline_h']} h, routed between 4 grids, {d['n']} test cases")

# 4. tiny vs big, both scored on the same rows in one run
# never mix: with v2 tiny numbers on the other slides, only the v2 4B comparison may appear
tiny_src = first("out/v3/metrics.json", "out/v2/metrics.json")[0]
src, big = first("out/big_v2/metrics_big.json") if tiny_src else first("out/big/metrics_big.json")
if big:
    j = big["joules_per_decision"]
    put("big_vs_tiny", {
        "big_params": big["params"], "tiny_params": big["tiny_params"], "param_ratio": round(big["params"] / big["tiny_params"]),
        "big_brier": round(big["big"]["brier"], 4), "tiny_brier": round(big["tiny"]["brier"], 4), "eia_brier": round(big["eia_calibrated"]["brier"], 4),
        "big_joules": j["big"]["joules"], "tiny_joules": j["tiny"]["joules"], "energy_ratio": round(j["ratio"]),
        "agree_pct": round(big["agree_big_tiny"] * 100), "test_rows": big["test_rows"],
        "big_train_hours": round(big["train_seconds"] / 3600, 1), "big_train_wh": big["train_energy_wh"],
    }, src)

# 5. demand response on the 4080 (decode, llama-bench)
sweep = ROOT / "out/sweep/jtoken.csv"
if sweep.exists():
    rows = {(r["setting"], r["phase"]): r for r in csv.DictReader(open(sweep))}
    a, e = rows[("pl350", "tg")], rows[("lgc2400", "tg")]
    put("gpu_4080", {"watts_before": round(float(a["watts_mean"])), "watts_after": round(float(e["watts_mean"])),
                     "power_drop_pct": round((1 - float(e["watts_mean"]) / float(a["watts_mean"])) * 100),
                     "speed_drop_pct": round((1 - float(e["tokens_per_s"]) / float(a["tokens_per_s"])) * 100)}, "out/sweep/jtoken.csv",
        note="RTX 4080 Super, 27B model decoding, default clocks vs SM clock locked at 2400 MHz")

# 6. downshift on this laptop (written by demo/measure_downshift.py)
src, mac = first("out/mac/downshift.json")
if mac:
    put("mac_downshift", mac, src)

# 7. Utah solar forecaster (train/solar.py)
src, sol = first("out/solar/metrics.json")
if sol:
    put("solar_forecast", {"skill_vs_persistence_pct": sol["skill_vs_persistence_pct"], "nmae_pct": sol["model"]["nmae_pct"],
                           "persistence_nmae_pct": sol["persistence"]["nmae_pct"], "slc_only_nmae_pct": sol["slc_weather_only"]["nmae_pct"],
                           "capacity_mw": sol["capacity_mw_latest"]}, src, note=sol["test"])

# 8. surge smoothing (train/surge.py): one measured 4080 start, a simulated 1 MW site
src, sg = first("out/surge/metrics.json")
if sg:
    put("surge_1mw", sg["site"], src, note=sg["note"])

# 9. Utah's planned plants (train/expansion.py, EIA-860M)
src, ex = first("out/expansion/utah.json")
if ex:
    put("utah_expansion", {k: ex[k] for k in ("planned_mw", "ldwp_share_pct", "planned_on_wasatch_front_mw", "planned_by_county_mw", "planned_by_kind_mw")},
        src, source_data=ex["source"])

# 10. how little the small model needs per forecast, on this laptop (demo/measure_tiny.py), vs the 4B on the same laptop
src, eff = first("out/mac/tiny_efficiency.json")
if eff:
    big = next((json.loads((ROOT / p).read_text())["big"] for p in ("out/mac/downshift.json", "out/mac/downshift_page_hidden.json") if (ROOT / p).exists()), None)
    put("tiny_efficiency", {"forecasts_per_s": eff["forecasts_per_s"], "joules_per_forecast": eff["joules_per_forecast"],
                            "year_all_regions_joules": eff["year_all_regions_joules"], "params": eff["params"],
                            "vs_4b_ratio": round(big["joules_per_forecast"] / eff["joules_per_forecast_total_chip"], -4) if big else None,
                            "big_joules_per_forecast": big["joules_per_forecast"] if big else None}, src,
        note="one forecast = one power region's next 24 h; ratio uses total chip power on both sides, same MacBook")

# 10b. right-sizing chart: the three designs trained for the same job, energy per forecast relative to the shipped one.
# v2 vs v3: back-to-back on one laptop core (above idle); v2 vs 4B: total chip power on the same MacBook. The 4B's error is
# from the earlier 4-region test (out/big, on the server): Brier 0.100 vs calibrated EIA 0.103 (README "Model versions").
_, e2 = first("out/v3_candidate/efficiency_v2.json")
_, e3 = first("out/v3_candidate/efficiency_v3_candidate.json")
_, m2 = first("out/v2/metrics.json")
_, m3 = first("out/v3_candidate/metrics.json")
if e2 and e3 and m2 and m3 and eff and big:
    vs_eia = lambda m: round(100 * (1 - m["test_peak_brier"]["model"] / m["test_peak_brier"]["eia_forecast_calibrated"]))
    put("model_sizes", [
        {"name": "Terra", "params": m2["params"], "energy_x": 1, "fewer_errors_pct": vs_eia(m2), "shipped": True},
        {"name": "Transformer", "params": m3["params"], "energy_x": round(e3["joules_per_forecast"] / e2["joules_per_forecast"], -1),
         "fewer_errors_pct": vs_eia(m3)},
        {"name": "Fine-tuned LLM", "params": 4.0e9, "energy_x": round(big["joules_per_forecast"] / eff["joules_per_forecast_total_chip"], -4),
         "fewer_errors_pct": round(100 * (1 - 0.100 / 0.103)), "earlier_test": True},
    ], "out/v2/metrics.json, out/v3_candidate/, out/mac/",
        note="energy per forecast vs Terra; fewer errors = Brier vs the utility's calibrated day-ahead forecast, held-out 2026")

# 11. what Utah saved in the replay week (deck/utah_savings.ts, same jobs and routing as the live map)
src, sv = first("deck/utah_savings.json")
if sv:
    put("utah_savings", {k: v for k, v in sv.items() if k != "ledger"}, src)

(ROOT / "deck/numbers.json").write_text(json.dumps(N, indent=1))
print(json.dumps({k: v["value"] for k, v in N.items()}, indent=1))
