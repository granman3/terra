"""Azure LLM inference 2024 (1 week, range-sampled chunks) -> hourly request & token rate curve.
Each chunk: parse complete lines, rate = rows / time span inside the chunk. Hours with no chunk are
linearly interpolated (flagged). Also token stats from the 2023 full files + 2024 chunks.
Usage: python -I azure_diurnal.py RAW_DIR OUT_CSV OUT_JSON"""
import sys, os, glob, json
import pandas as pd, numpy as np
raw, out_csv, out_json = sys.argv[1:4]
def chunks(svc):
    rows = []
    toks = []
    for f in sorted(glob.glob(f"{raw}/azure-llm-2024/{svc}/chunk_*.csv.part")):
        lines = open(f, "rb").read().decode("utf-8", "replace").split("\n")[1:-1]  # drop partial first/last
        recs = [l.split(",") for l in lines if l.count(",") == 2 and l.startswith("2024-")]
        if len(recs) < 50: continue
        ts = pd.to_datetime([r[0] for r in recs], utc=True, format="ISO8601")
        span = (ts.max() - ts.min()).total_seconds()
        if span <= 0: continue
        ctx = np.array([int(r[1]) for r in recs]); gen = np.array([int(r[2]) for r in recs])
        mid = ts.min() + (ts.max() - ts.min()) / 2
        rows.append({"t": mid, "req_per_s": (len(recs) - 1) / span,
                     "tok_per_s": (ctx.sum() + gen.sum()) / span * (len(recs) - 1) / len(recs),
                     "gen_tok_per_s": gen.sum() / span * (len(recs) - 1) / len(recs)})
        toks.append(pd.DataFrame({"ctx": ctx, "gen": gen}))
    return pd.DataFrame(rows).sort_values("t"), pd.concat(toks)
out, stats = [], {}
for svc in ("code", "conv"):
    c, tk = chunks(svc)
    c["hour"] = c.t.dt.floor("h")
    h = c.groupby("hour")[["req_per_s", "tok_per_s", "gen_tok_per_s"]].mean()
    full = pd.date_range(c.hour.min(), c.hour.max(), freq="h", tz="UTC")
    h = h.reindex(full); h["interpolated"] = h.req_per_s.isna()
    h[["req_per_s", "tok_per_s", "gen_tok_per_s"]] = h[["req_per_s", "tok_per_s", "gen_tok_per_s"]].interpolate(limit_direction="both")
    h["service"] = svc
    out.append(h.rename_axis("utc_hour").reset_index())
    stats[svc] = {"chunks_used": int(len(c)), "hours": int(len(h)), "hours_interpolated": int(h.interpolated.sum()),
        "first_utc": str(full.min()), "last_utc": str(full.max()),
        "mean_req_per_s": round(float(h.req_per_s.mean()), 2),
        "peak_to_trough_req": round(float(h.req_per_s.max() / h.req_per_s.min()), 2),
        "ctx_tokens_2024_sample": {p: int(np.percentile(tk.ctx, q)) for p, q in (("p50", 50), ("p90", 90), ("p99", 99))},
        "gen_tokens_2024_sample": {p: int(np.percentile(tk.gen, q)) for p, q in (("p50", 50), ("p90", 90), ("p99", 99))},
        "sample_requests": int(len(tk))}
    f23 = pd.read_csv(f"{raw}/azure-llm-2023/AzureLLMInferenceTrace_{svc}.csv")
    t23 = pd.to_datetime(f23.TIMESTAMP)
    stats[svc]["trace_2023"] = {"requests": int(len(f23)), "span_min": round((t23.max() - t23.min()).total_seconds() / 60, 1),
        "ctx_p50": int(f23.ContextTokens.median()), "gen_p50": int(f23.GeneratedTokens.median()),
        "ctx_p90": int(f23.ContextTokens.quantile(.9)), "gen_p90": int(f23.GeneratedTokens.quantile(.9))}
d = pd.concat(out)
d["dow_utc"] = d.utc_hour.dt.day_name(); d["hour_utc"] = d.utc_hour.dt.hour
for svc in ("code", "conv"):
    m = d.service == svc
    d.loc[m, "req_norm_to_week_mean"] = d.loc[m, "req_per_s"] / d.loc[m, "req_per_s"].mean()
    d.loc[m, "tok_norm_to_week_mean"] = d.loc[m, "tok_per_s"] / d.loc[m, "tok_per_s"].mean()
# combined (both services, summed rates) by hour
# "both": only the hours where both services were recorded (code May 10-16, conv May 12-18 -> overlap May 12-16)
both_hours = d.groupby("utc_hour").service.nunique().pipe(lambda s: s[s == 2].index)
comb = d[d.utc_hour.isin(both_hours)].groupby("utc_hour")[["req_per_s", "tok_per_s"]].sum()
stats["both_overlap_hours"] = int(len(comb))
prof = []
for svc, sub in list(d.groupby("service")) + [("both", comb.reset_index().assign(hour_utc=lambda x: x.utc_hour.dt.hour))]:
    p = sub.groupby("hour_utc")[["req_per_s", "tok_per_s"]].mean()
    p = p / p.mean(); p["service"] = svc; prof.append(p.reset_index())
prof = pd.concat(prof)
dow = d.groupby(["service", "dow_utc"]).req_per_s.mean()
stats["day_of_week_req_norm"] = {sv: (g.droplevel(0) / g.mean()).round(3).to_dict() for sv, g in dow.groupby(level=0)}
stats["hour_of_day_profile_req_norm"] = {s: g.set_index("hour_utc").req_per_s.round(3).to_dict() for s, g in prof.groupby("service")}
cols = ["utc_hour", "dow_utc", "hour_utc", "service", "req_per_s", "tok_per_s", "gen_tok_per_s",
        "req_norm_to_week_mean", "tok_norm_to_week_mean", "interpolated"]
d[cols].round({c: 4 for c in cols[4:9]}).to_csv(out_csv, index=False)
prof.rename(columns={"req_per_s": "req_norm_to_day_mean", "tok_per_s": "tok_norm_to_day_mean"}).round(4).to_csv(
    out_csv.replace(".csv", "_hour_of_day.csv"), index=False)
json.dump(stats, open(out_json, "w"), indent=1)
print(json.dumps(stats, indent=1))
