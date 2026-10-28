"""Alibaba 2026 traces: labeled online vs offline / training / LP share of GPU-hours, plus spot-GPU job sizes.
Usage: python -I alibaba_2026.py RAW_DIR OUT_JSON"""
import sys, glob, json, os
import pandas as pd, numpy as np
raw, out = sys.argv[1:3]
res = {}
def pct(s, ps=(50, 90, 99)): return {f"p{p}": round(float(np.percentile(s, p)), 3) for p in ps}
# 1) MaaS (xMaaS LLM inference, 6 months): online vs offline GPU-hours, sampled shards
fs = sorted(glob.glob(f"{raw}/alibaba-maas-2026/instance_daily_cols/*.parquet"))
m = pd.concat([pd.read_parquet(f) for f in fs])
w = m.groupby("workload").gpu_hours.sum()
per_shard = [ (lambda x: float(x.get("offline", 0) / x.sum()))(pd.read_parquet(f).groupby("workload").gpu_hours.sum()) for f in fs]
res["maas_llm_inference"] = {"shards_sampled": len(fs), "of_shards": 61, "rows": int(len(m)),
    "days": [int(m.day.min()), int(m.day.max())], "gpu_hours": round(float(w.sum()), 0),
    "share_gpu_hours": (w / w.sum()).round(4).to_dict(),
    "offline_share_range_across_shards": [round(min(per_shard), 4), round(max(per_shard), 4)]}
# 2) ASI hyperscale GPU cluster: hourly pod facts, GPU-requesting pods
fs = sorted(glob.glob(f"{raw}/alibaba-asi-2026/pod_hourly_cols/*.parquet"))
parts = []
for f in fs:
    d = pd.read_parquet(f); d = d[d.gpu_request > 0]
    tag = os.path.basename(f).split("__")[1:3]
    d = d.assign(day=int(tag[0].split("-")[1]), hour=int(tag[1].split("-")[1]))
    parts.append(d.groupby(["day", "hour", "job_type_public", "priority_class"], dropna=False).used_gpu_hours.sum().reset_index())
a = pd.concat(parts)
tot = a.used_gpu_hours.sum()
jt = a.groupby("job_type_public").used_gpu_hours.sum() / tot
pr = a.groupby("priority_class").used_gpu_hours.sum() / tot
cross = (a.groupby(["job_type_public", "priority_class"]).used_gpu_hours.sum() / tot).round(4)
by_snap = a.groupby(["day", "hour"]).apply(lambda g: pd.Series({
    "online": g[g.job_type_public == "online_inference"].used_gpu_hours.sum() / g.used_gpu_hours.sum(),
    "training_or_offline": g[g.job_type_public.isin(["training", "offline_inference"])].used_gpu_hours.sum() / g.used_gpu_hours.sum()}), include_groups=False)
known = a[~a.job_type_public.isin(["unknown"])]
jt_known = known.groupby("job_type_public").used_gpu_hours.sum() / known.used_gpu_hours.sum()
d100 = a[a.day == 100].groupby(["hour", "job_type_public"]).used_gpu_hours.sum().unstack().fillna(0)
res["asi_gpu_cluster"] = {"hour_snapshots": len(fs), "days_sampled": sorted(a.day.unique().tolist()),
    "used_gpu_hours_sampled": round(float(tot), 0),
    "share_gpu_hours_by_job_type": jt.round(4).to_dict(),
    "share_gpu_hours_by_job_type_excl_unknown": jt_known.round(4).to_dict(),
    "share_gpu_hours_by_priority": pr.round(4).to_dict(),
    "share_by_job_type_x_priority": {f"{k[0]}|{k[1]}": v for k, v in cross.to_dict().items()},
    "online_share_range_across_snapshots": [round(float(by_snap.online.min()), 4), round(float(by_snap.online.max()), 4)],
    "training_or_offline_share_range": [round(float(by_snap.training_or_offline.min()), 4), round(float(by_snap.training_or_offline.max()), 4)],
    "day100_hourly_gpu_hours_by_type_peak_to_trough": {c: round(float(d100[c].max() / max(d100[c].min(), 1e-9)), 3) for c in d100.columns}}
# 2b) ASI execution spans (if fetched): per-span GPU-hours = gpu_request * duration_hours by job type
fs = glob.glob(f"{raw}/alibaba-asi-2026/job_exec_cols/*.parquet")
if fs:
    e = pd.read_parquet(fs[0]); e = e[(e.gpu_request > 0) & (e.duration_hours > 0)]
    e["gpu_hours"] = e.gpu_request * e.duration_hours
    t = e.gpu_hours.sum()
    res["asi_execution_spans"] = {"spans": int(len(e)), "gpu_hours": round(float(t), 0),
        "by_job_type": {k: {"spans": int(len(g)), "share_spans": round(len(g) / len(e), 4),
                            "share_gpu_hours": round(float(g.gpu_hours.sum() / t), 4),
                            "gpu_hours_per_span": pct(g.gpu_hours), "duration_h": pct(g.duration_hours),
                            "gpus": pct(g.gpu_request), "median_schedule_delay_s": float(g.schedule_delay_sec.median()) if g.schedule_delay_sec.notna().any() else None}
                        for k, g in e.groupby("job_type_public")},
        "by_priority_share_gpu_hours": (e.groupby("priority_class").gpu_hours.sum() / t).round(4).to_dict()}
    e[["job_type_public", "priority_class", "gpu_hours", "duration_hours", "gpu_request"]].to_parquet(f"{raw}/../scripts/_asi_spans.parquet")
# 3) Spot GPU trace (ASPLOS'26): HP vs Spot jobs
s = pd.read_csv(f"{raw}/alibaba-spot-gpu-2026/job_info_df.csv")
s["gpu_hours"] = s.gpu_request * s.worker_num * s.duration / 3600
t = s.gpu_hours.sum()
res["spot_gpu_jobs"] = {"jobs": int(len(s)), "by_type": {k: {"jobs": int(len(g)), "share_jobs": round(len(g) / len(s), 4),
    "share_gpu_hours": round(float(g.gpu_hours.sum() / t), 4), "gpu_hours_per_job": pct(g.gpu_hours),
    "duration_h": pct(g.duration / 3600), "gpus_per_job": pct(g.gpu_request * g.worker_num)} for k, g in s.groupby("job_type")},
    "note": "HP jobs include long-lived services (duration up to months); share of GPU-hours over the trace window is dominated by them"}
json.dump(res, open(out, "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
