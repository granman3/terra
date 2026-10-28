"""ASI hourly snapshots: GPU-hour share by state_public, and GPUs per pod by job type.
Usage: python -I asi_state_gpus.py RAW_DIR OUT_JSON"""
import sys, glob, json
import pandas as pd
raw, out = sys.argv[1:3]
d = pd.concat([pd.read_parquet(f, columns=["job_type_public", "state_public", "gpu_request", "used_gpu_hours"])
               for f in glob.glob(f"{raw}/alibaba-asi-2026/pod_hourly_cols/*.parquet")])
d = d[d.gpu_request > 0]
st = (d.groupby("state_public").used_gpu_hours.sum() / d.used_gpu_hours.sum()).round(4).to_dict()
run = d[d.state_public == "Running"]
jt_run = (run.groupby("job_type_public").used_gpu_hours.sum() / run.used_gpu_hours.sum()).round(4).to_dict()
g = d.groupby("job_type_public").gpu_request.describe(percentiles=[.5, .9])[["50%", "90%"]].round(2)
res = {"share_used_gpu_hours_by_state": st, "share_by_job_type_running_only": jt_run,
       "gpus_per_pod_hour_by_job_type": g.rename(columns={"50%": "p50", "90%": "p90"}).to_dict(orient="index")}
json.dump(res, open(out, "w"), indent=1); print(json.dumps(res, indent=1))
