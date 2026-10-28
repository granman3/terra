"""Combine per-source results into job_mix.csv and summary.json.
DERIVED RULE (Terra's, not in any trace): deadline_h = 0 for online inference / dev notebooks / HP services
(a person or SLO is waiting); deadline_h = 16 for training, offline/batch inference, LP/spot work
(= Terra's longest wait option 12 h + JOB_HOURS 4 h, router/src/decide.ts).
Usage: python -I build_outputs.py SCRIPTS_DIR OUT_DIR"""
import sys, json, csv
sd, od = sys.argv[1:3]
pai = json.load(open(f"{sd}/_pai2020.json")); az = json.load(open(f"{sd}/_azure.json"))
ali = json.load(open(f"{sd}/_alibaba2026.json"))
RULE = "derived: 0 if online/dev/HP-service; 16 = Terra max wait 12h + JOB_HOURS 4h if training/offline/LP/spot"
rows = []
asi = ali["asi_gpu_cluster"]; jt = asi["share_gpu_hours_by_job_type"]
spans = ali.get("asi_execution_spans", {}).get("by_job_type", {})
st = json.load(open(f"{sd}/_asi_state.json")); gpp = st["gpus_per_pod_hour_by_job_type"]
src_asi = "Alibaba cluster-trace-gpu-v2026 (ASI, OSDI'26), 58 hourly snapshots over 185 days, used_gpu_hours"
for k, inter in [("online_inference", True), ("training", False), ("offline_inference", False), ("dev", True), ("other", None), ("unknown", None)]:
    sp = spans.get(k, {})
    rows.append({"source_trace": "alibaba-asi-2026", "name": f"asi-{k}", "type": k,
        "gpu_hours": sp.get("gpu_hours_per_span", {}).get("p50", ""),
        "gpu_hours_stat": "median per execution span" if sp else f"n/a: per-job GPU-hours not fetched; GPUs per pod (hourly snapshot, NOT GPU-hours) p50 {gpp[k]['p50']} p90 {gpp[k]['p90']}",
        "gpu_hours_p90": sp.get("gpu_hours_per_span", {}).get("p90", ""),
        "interactive": "" if inter is None else inter, "deadline_h_derived": "" if inter is None else (0 if inter else 16),
        "share_of_gpu_hours": jt.get(k, 0), "share_basis": "share of all GPU-hours in ASI cluster (labeled job_type_public)", "source": src_asi})
pr = asi["share_gpu_hours_by_priority"]
for k, inter in [("HP", None), ("LP", False)]:
    rows.append({"source_trace": "alibaba-asi-2026", "name": f"asi-priority-{k}", "type": f"priority {k}" + (" (low-priority/spot, runs on flexible capacity)" if k == "LP" else " (guaranteed)"),
        "gpu_hours": "", "gpu_hours_stat": "", "gpu_hours_p90": "", "interactive": "" if inter is None else inter,
        "deadline_h_derived": "" if inter is None else 16, "share_of_gpu_hours": pr[k],
        "share_basis": "share of all GPU-hours in ASI cluster (labeled priority_class); overlaps the job-type rows", "source": src_asi})
mq = ali["maas_llm_inference"]
for k, inter in [("online", True), ("offline", False)]:
    rows.append({"source_trace": "alibaba-maas-2026", "name": f"llm-inference-{k}", "type": f"LLM inference, {k}",
        "gpu_hours": "", "gpu_hours_stat": "", "gpu_hours_p90": "", "interactive": inter, "deadline_h_derived": 0 if inter else 16,
        "share_of_gpu_hours": mq["share_gpu_hours"][k], "share_basis": "share of LLM-inference GPU-hours only (xMaaS platform, 12 of 61 shards, 6 months)",
        "source": "Alibaba cluster-trace-v2026-maas (ATC'26), instance_daily gpu_hours"})
for k, g in ali["spot_gpu_jobs"]["by_type"].items():
    rows.append({"source_trace": "alibaba-spot-gpu-2026", "name": f"gpu-job-{k.lower()}", "type": "high-priority job (strict SLO)" if k == "HP" else "spot job (opportunistic, preemptible)",
        "gpu_hours": g["gpu_hours_per_job"]["p50"], "gpu_hours_stat": "median per job", "gpu_hours_p90": g["gpu_hours_per_job"]["p90"],
        "interactive": "" if k == "HP" else False, "deadline_h_derived": "" if k == "HP" else 16,
        "share_of_gpu_hours": g["share_gpu_hours"], "share_basis": f"share of GPU-hours in spot-GPU trace ({g['jobs']} jobs); HP includes months-long services",
        "source": "Alibaba cluster-trace-v2026-spot-gpu (ASPLOS'26), job_info_df.csv"})
for b in pai["buckets"]:
    rows.append({"source_trace": "alibaba-pai-2020", "name": f"pai-job-{b['bucket']}-gpuh", "type": f"PAI ML job, {b['bucket']} GPU-h (unlabeled training/inference mix; roles mostly worker/PyTorchWorker)",
        "gpu_hours": b["median_gpu_hours"], "gpu_hours_stat": f"median in bucket; median runtime {b['median_runtime_h']} h on {b['median_gpus']} GPUs; {b['jobs']} jobs",
        "gpu_hours_p90": "", "interactive": False, "deadline_h_derived": 16,
        "share_of_gpu_hours": b["share_gpu_hours"], "share_basis": "share of PAI 2020 GPU-hours (719,560 GPU jobs, Jul-Aug 2020); interactive=False is an ASSUMPTION (no label in trace)",
        "source": "Alibaba cluster-trace-gpu-v2020 (PAI, NSDI'22), pai_task_table plan_gpu x inst_num x runtime"})
for r in rows: r["deadline_rule"] = RULE
with open(f"{od}/job_mix.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
ex = ali.get("asi_execution_spans")
movable_type = jt["training"] + jt["offline_inference"]
summary = {
  "retrieved": "2026-10-27",
  "headline": {
    "asi_2026_share_gpu_hours_training_plus_offline_inference": round(movable_type, 4),
    "asi_2026_share_gpu_hours_online_inference": jt["online_inference"],
    "asi_2026_share_gpu_hours_dev": jt["dev"],
    "asi_2026_share_gpu_hours_low_priority_LP": pr["LP"],
    "maas_2026_llm_inference_offline_share_gpu_hours": mq["share_gpu_hours"]["offline"],
    "pai_2020_share_gpu_hours_jobs_ge_10_gpu_hours": pai["share_gpu_hours_jobs_ge_10gpuh"],
    "pai_2020_share_gpu_hours_jobs_running_ge_4h": pai["share_gpu_hours_jobs_runtime_ge_4h"],
    "spot_2026_share_gpu_hours_spot": ali["spot_gpu_jobs"]["by_type"]["Spot"]["share_gpu_hours"],
    "azure_llm_2024_peak_hour_vs_mean_both_services": max(az["hour_of_day_profile_req_norm"]["both"].values()),
    "azure_llm_2024_trough_hour_vs_mean_both_services": min(az["hour_of_day_profile_req_norm"]["both"].values()),
    "azure_llm_2024_weekend_vs_mean_code": round((az["day_of_week_req_norm"]["code"]["Saturday"] + az["day_of_week_req_norm"]["code"]["Sunday"]) / 2, 3),
    "azure_llm_2024_weekend_vs_mean_conv": round((az["day_of_week_req_norm"]["conv"]["Saturday"] + az["day_of_week_req_norm"]["conv"]["Sunday"]) / 2, 3),
  },
  "deadline_rule": RULE,
  "alibaba_pai_2020": {k: v for k, v in pai.items() if k != "submits_by_hour_utc8"},
  "alibaba_pai_2020_submits_by_hour_utc8": pai["submits_by_hour_utc8"],
  "alibaba_asi_2026": asi, "alibaba_asi_2026_execution_spans": ex,
  "alibaba_asi_2026_state_and_pod_size": st,
  "alibaba_maas_2026": mq, "alibaba_spot_gpu_2026": ali["spot_gpu_jobs"],
  "azure_llm": az,
  "caveats": [
    "ASI shares are GPU-hours from 58 sampled hour snapshots (all 24 h of day 100; hours 02+14 on 15 other days; hour 14 on days 20/60/140/180), not all 4,440 hours.",
    "Type labels say what work is, not that the operator would let it move: in ASI, training is 90% HP (guaranteed) GPU-hours; only LP (22%) is explicitly flexible.",
    "arXiv 2609.05406 (same ASI trace) finds newly deferrable arrivals add almost no delay-based capacity at the scheduler: most GPU-hours are long-running pods already placed.",
    "PAI 2020 has no training/inference label; interactive=False there is an assumption. Its time-of-day is valid in UTC+8 only (dates are fake).",
    "Azure diurnal is range-sampled: 672 x 128 KB chunks per 1-week file; per-chunk rate = rows / time span; 5 code-hours interpolated. Hours are UTC; Azure region not disclosed.",
    "ASI state filter: Standby pods are 1.1% of used GPU-hours (rest 'Unknown'), left in; immaterial to the shares.",
    "ASI (whole fleet: rec/cv/LLM, training+inference) offline inference = 20% of all GPU-hours (~27% of inference); MaaS (LLM-only serving platform) offline = 60% of LLM-inference GPU-hours. Different platforms and scopes; not the same measurement.",
    "Azure 2023 files each cover ~1 hour (Nov 16 2023), so they give token sizes only, no diurnal shape.",
  ],
}
json.dump(summary, open(f"{od}/summary.json", "w"), indent=1, default=str)
print(json.dumps(summary["headline"], indent=1))
