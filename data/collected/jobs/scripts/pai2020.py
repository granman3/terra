"""Alibaba PAI GPU trace 2020: GPU-hours per job, task roles, queueing, submit hour-of-day (UTC+8).
Reads the verified tar.gz files directly. Usage: python -I pai2020.py RAW_DIR OUT_JSON"""
import sys, json
import pandas as pd, numpy as np
raw, out = sys.argv[1], sys.argv[2]
task = pd.read_csv(f"{raw}/pai_task_table.tar.gz", header=None, names=[
    "job_name","task_name","inst_num","status","start_time","end_time","plan_cpu","plan_mem","plan_gpu","gpu_type"])
job = pd.read_csv(f"{raw}/pai_job_table.tar.gz", header=None, names=["job_name","inst_id","user","status","start_time","end_time"])
tag = pd.read_csv(f"{raw}/pai_group_tag_table.tar.gz", header=None, names=["inst_id","user","gpu_type_spec","group","workload"])
t = task.dropna(subset=["start_time","end_time"]).copy()
t = t[(t.plan_gpu > 0) & (t.end_time >= t.start_time)]
t["gpu_hours"] = t.plan_gpu / 100 * t.inst_num * (t.end_time - t.start_time) / 3600
t["gpus"] = t.plan_gpu / 100 * t.inst_num
g = t.groupby("job_name").agg(gpu_hours=("gpu_hours","sum"), gpus=("gpus","sum"),
    t0=("start_time","min"), t1=("end_time","max"), roles=("task_name", lambda s: "+".join(sorted(set(s)))))
g["runtime_h"] = (g.t1 - g.t0) / 3600
g = g.join(job.set_index("job_name")[["inst_id","status","start_time"]])
g["queue_min"] = (g.t0 - g.start_time) / 60
g = g.join(tag.drop_duplicates("inst_id").set_index("inst_id")[["workload"]], on="inst_id")
g = g[g.gpu_hours > 0]
def pct(s, ps=(50, 90, 99)): return {f"p{p}": round(float(np.percentile(s, p)), 3) for p in ps}
tot = g.gpu_hours.sum()
# percentile buckets of GPU-hours per job
edges = [0, 0.1, 1, 10, 100, 1000, np.inf]
labels = ["<0.1", "0.1-1", "1-10", "10-100", "100-1000", ">=1000"]
g["bucket"] = pd.cut(g.gpu_hours, edges, labels=labels, right=False)
b = g.groupby("bucket", observed=False).agg(jobs=("gpu_hours","size"), gpu_hours=("gpu_hours","sum"),
    median_gpu_hours=("gpu_hours","median"), median_runtime_h=("runtime_h","median"), median_gpus=("gpus","median"))
b["share_jobs"] = b.jobs / len(g); b["share_gpu_hours"] = b.gpu_hours / tot
role = g.groupby("roles").gpu_hours.sum().sort_values(ascending=False) / tot
wl = g.dropna(subset=["workload"]).groupby("workload").gpu_hours.sum().sort_values(ascending=False)
hour8 = ((g.start_time.dropna() + 8 * 3600) % 86400 // 3600).astype(int)  # README: time-of-day matches UTC+8
# README says Unix-time-in-UTC+8 matches original, i.e. interpret raw seconds as UTC epoch then shift +8
res = {
  "jobs_with_gpu": int(len(g)), "total_gpu_hours": round(float(tot), 1),
  "gpu_hours_per_job": pct(g.gpu_hours), "mean_gpu_hours_per_job": round(float(g.gpu_hours.mean()), 3),
  "gpus_per_job": pct(g.gpus), "runtime_h": pct(g.runtime_h),
  "queue_min": pct(g.queue_min.dropna().clip(lower=0)),
  "share_gpu_hours_top1pct_jobs": round(float(g.gpu_hours.nlargest(max(1, len(g)//100)).sum() / tot), 4),
  "share_gpu_hours_jobs_ge_10gpuh": round(float(g.gpu_hours[g.gpu_hours >= 10].sum() / tot), 4),
  "share_jobs_ge_10gpuh": round(float((g.gpu_hours >= 10).mean()), 4),
  "share_gpu_hours_jobs_runtime_ge_4h": round(float(g.gpu_hours[g.runtime_h >= 4].sum() / tot), 4),
  "status_share_gpu_hours": (g.groupby("status").gpu_hours.sum() / tot).round(4).to_dict(),
  "buckets": b.reset_index().round(4).to_dict(orient="records"),
  "role_share_gpu_hours_top10": role.head(10).round(4).to_dict(),
  "tagged_workload_gpu_hours_top10": wl.head(10).round(1).to_dict(),
  "tagged_share_of_gpu_hours": round(float(wl.sum() / tot), 4),
  "submits_by_hour_utc8": hour8.value_counts().sort_index().to_dict(),
}
json.dump(res, open(out, "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k not in ("buckets","submits_by_hour_utc8")}, indent=1, default=str))
print(b.round(3).to_string())
