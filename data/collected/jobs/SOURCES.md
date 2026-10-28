# Jobs: real AI/GPU workload traces (retrieved 2026-10-27)

Replaces the illustrative `JOBS` list in `router/src/server.ts` (nightly-evals 160 GPU-h / 12 h, etc.).
Everything here is either **reported** (copied from a source) or **derived** (computed by a script in
`scripts/` from files in `raw/`). Nothing is invented.

## What this replaces (the line a judge can hear)

> "Our job mix comes from Alibaba's 2026 trace of 155,410 production GPUs: 42% of GPU-hours were
> training or offline batch inference, work that can wait, and 22% already ran as low-priority
> flexible capacity. The other 53% was online inference, which Terra never moves. The demand
> curve is Microsoft Azure's real week of LLM requests: peak hours run 1.5x the daily mean."

Honest caveat to say if asked: work being *batch* doesn't mean the operator lets it move. In that
same trace 90% of training GPU-hours run at guaranteed priority, and a Sept 2026 paper on it
(arXiv 2609.05406) finds the scheduler gets almost no extra capacity from deferring new arrivals.
Terra's argument is that this share *could* move with a carbon/peak signal, not that it already does.

## Files

| File | What | Reported / derived |
|---|---|---|
| `job_mix.csv` | Job types with GPU-hours, interactive flag, `deadline_h_derived`, share of GPU-hours, source | derived |
| `diurnal.csv` | 168 hourly rows per Azure service (code, conv): req/s, tokens/s, normalized to week mean, day of week | derived (range-sampled) |
| `diurnal_hour_of_day.csv` | 24-hour profile per service and both combined, normalized to the daily mean | derived |
| `summary.json` | Headline percentages, per-source stats, caveats | derived |
| `scripts/*.py` | All parsing; run as `uv run --with pandas --with pyarrow python -I scripts/<x>.py ...` | |
| `raw/` | Downloaded files, untrusted, never executed | raw |

**Deadline rule (derived, Terra's own, not in any trace):** `deadline_h = 0` for online inference,
dev notebooks and HP services (a user or SLO is waiting); `deadline_h = 16` for training, offline/batch
inference and LP/spot work = Terra's longest wait option (12 h) + `JOB_HOURS` (4 h) from
`router/src/decide.ts`.

## Sources

### 1. Alibaba cluster-trace-gpu-v2026 (ASI), headline source
- Repo: https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2026
- Data: https://tre-clusterdata.oss-cn-hangzhou.aliyuncs.com/cluster-trace-gpu-v2026/data/asi_opensource_pod_hourly.zip (351.8 GB)
- Paper: Li et al., "Heterogeneity at Hyperscale", OSDI '26, https://www.usenix.org/conference/osdi26/presentation/li-suyi
- License: no license file in the v2026 folder or repo root (404); the repo's v2020 folder is CC-BY 4.0. Treat as "public research release, cite the paper".
- What we pulled: 58 hourly partitions (all 24 h of day 100; hours 02 and 14 on 15 other days; hour 14 only on days 20, 60, 140, 180; days 0 to 184), **only 7 columns**, read with HTTP Range from inside the zip (`scripts/remote_parquet.py`), ~70 MB. Saved as `raw/alibaba-asi-2026/pod_hourly_cols/*.parquet`.
- Derived (GPU-requesting pods, `used_gpu_hours`): online inference **53.0%**, training **22.1%**, offline inference **20.2%**, dev **3.6%**, other/unknown 1.2%. Priority: HP **77.1%**, LP **22.1%**. Online share across snapshots: 46% to 70%. `state_public`: Standby pods are 1.1% of used GPU-hours (kept). GPUs per pod (hourly snapshot): training p50 1, p90 16; online inference p50 1, p90 1. Per-job GPU-hours for ASI were not fetched, so ASI rows in `job_mix.csv` give shares only; PAI and spot rows carry real per-job GPU-hours.
- Reported (README): "covers 155,410 GPUs across 37,707 GPU servers" at hourly peak, ~six months.

### 2. Alibaba cluster-trace-v2026-maas (xMaaS LLM inference)
- Repo: https://github.com/alibaba/clusterdata/tree/master/cluster-trace-v2026-maas
- Data: https://tre-clusterdata.oss-cn-hangzhou.aliyuncs.com/cluster-trace-v2026-maas/data/instance_daily.zip (10.5 GB), plus `app_metrics.csv.zip` (100 KB, downloaded whole, not yet analyzed)
- Paper: Zheng et al., "Model-as-a-Service in the Wild", ATC '26
- License: none stated in folder; cite the paper.
- What we pulled: 12 of 61 parquet shards (0, 5, ..., 55), columns `day, workload, gpu_hours, gpu_count, pd_role, params_b`, range-read (~55 MB), days 0 to 181.
- How it squares with ASI: ASI is the whole GPU fleet (recommendation, vision, LLM; training and inference), where offline inference is 20% of all GPU-hours (about 27% of inference). xMaaS is an LLM-only serving platform. Different platforms, different scope; treat this as a second, narrower view, not the same measurement. The judge line uses ASI.
- Derived: of LLM-inference GPU-hours, **offline 60.1%**, online 39.9% (range across shards 57% to 61% offline).

### 3. Alibaba cluster-trace-v2026-spot-gpu
- File: https://raw.githubusercontent.com/alibaba/clusterdata/master/cluster-trace-v2026-spot-gpu/job_info_df.csv (23 MB, whole)
- Paper: Duan et al., "GFS: A Preemptive Scheduling Framework for GPU Clusters with Predictive Spot Management", ASPLOS '26
- Derived: 466,867 jobs; Spot jobs are 11.0% of jobs but **2.4%** of GPU-hours (HP includes months-long services). Spot job median 1.6 GPU-h (p90 28.5); HP median 0.4 GPU-h (p90 54, p99 2,027).

### 4. Alibaba cluster-trace-gpu-v2020 (PAI)
- Repo: https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2020
- Data: https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2020GPUTraces/{pai_job_table,pai_task_table,pai_group_tag_table}.tar.gz (147 MB, sha256 verified against README)
- Paper: Weng et al., "MLaaS in the Wild", NSDI '22
- License: CC-BY 4.0 (https://github.com/alibaba/clusterdata/blob/master/cluster-trace-gpu-v2020/LICENSE)
- Derived (GPU-hours = plan_gpu/100 x inst_num x task runtime): 719,560 GPU jobs, 4.97 M GPU-hours. Per job: median **0.12** GPU-h, p90 **6.1**, p99 **115**, mean 6.9. 7% of jobs (>= 10 GPU-h) hold **89%** of GPU-hours; the top 1% of jobs hold 63%. Jobs running >= 4 h hold 78% of GPU-hours. No training/inference label (README: "a hybrid of training and inference jobs"), so `interactive=False` for PAI rows is an **assumption**.

### 5. Azure LLM Inference traces 2024 (diurnal)
- Docs: https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2024.md
- Data: https://github.com/Azure/AzurePublicDataset/releases/download/dataset-llm-2024/AzureLLMInferenceTrace_code_1week.csv (692 MB) and `..._conv_1week.csv` (1,135 MB)
- Paper: Stojkovic et al., "DynamoLLM", HPCA '25
- License: CC-BY 4.0 (`raw/azure-LICENSE.txt`)
- What we pulled: **range-sampled**, 672 evenly spaced 128 KB chunks per file (88 MB each), saved in `raw/azure-llm-2024/{code,conv}/`. Rate per chunk = rows / time span inside the chunk; averaged per UTC hour; 5 code-hours with no chunk were linearly interpolated (flagged `interpolated=True`). Sanity check: code mean 28.0 req/s x 1 week = 17.0 M rows, matching 692 MB / ~40 B per row.
- Derived: both services, overlap May 12 to 16 2024: busiest hour (18 UTC) **1.52x** the daily mean, quietest (05 UTC) **0.63x**. Coding requests swing 0.25x to 2.15x over a day; weekends run 0.40x (code) and 0.65x (conversation) of the week mean. Token sizes (2024 sample, 2.1 M requests each): code context p50 1,923 / output p50 8; conversation context p50 930 / output p50 41.

### 6. Azure LLM Inference traces 2023 (token sizes only)
- Data: https://github.com/Azure/AzurePublicDataset/tree/master/data (AzureLLMInferenceTrace_code.csv, _conv.csv; 0.3 and 0.7 MB, whole)
- Paper: Patel et al., "Splitwise", ISCA '24. License CC-BY 4.0.
- Each file covers ~1 hour (2023-11-16 18:17 to 19:14 UTC): 8,819 code and 19,366 conversation requests. Too short for a daily curve.

### Skipped
- GitHub Copilot coding-agent traces 2026 (Azure release `ghcp-coding-agent-2026`): 124 to 621 MB per day, over budget.
- Alibaba ASI `job_execution_summary` (1.19 GB single parquet): a column-projected range read was started but not finished in the time box; per-span GPU-hours by job type are therefore not in `job_mix.csv`.
- Microsoft Philly, Google cluster-data 2019: not needed once the labeled 2026 traces were available.

## Published statements (exact quotes, ≤15 words)

| Source | Quote | URL |
|---|---|---|
| Radovanovic et al. (Google), "Carbon-Aware Computing for Datacenters", 2021 | "delay the execution of temporally flexible workloads to "greener" times" | https://arxiv.org/abs/2106.11750 |
| same | goal of "enabling all such workloads to complete within a day" (no flexible share is given) | https://arxiv.org/abs/2106.11750 |
| Stojkovic et al. (Microsoft), DynamoLLM, HPCA '25 | DynamoLLM "conserves 53% energy and 38% operational carbon emissions" | https://arxiv.org/abs/2408.00741 |
| Patel et al. (Microsoft), Splitwise, ISCA '24 | token generation "can be run with lower power and cost" | https://arxiv.org/abs/2311.18677 |
| Li, "Beyond Scalar Flexibility", arXiv Sept 2026 (uses the ASI trace) | "newly deferrable arrivals average 0.008 MW and have zero 95%-available capacity" | https://arxiv.org/abs/2609.05406 |
| same | immediate eligible curtailment averages "3.55 MW after retaining allocated-GPU idle power" (about 6.35% of median facility power) | https://arxiv.org/abs/2609.05406 |

The Google "temporally flexible" / "within a day" and the 2609.05406 "newly deferrable arrivals" wording was checked against the arXiv abstract HTML. The other quotes came from a fetch tool's summary of the abstract pages.
No paper we found reports a single "% of AI compute that is deferrable"; the ASI and MaaS shares above are our derived answers from labeled traces.
