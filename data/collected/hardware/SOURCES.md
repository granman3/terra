# Hardware and surge reference data (collected 2026-10-27)

Free, public sources only. Every number in `facts.csv`, `gpu_specs.csv` and `torus_specs.csv` was read from a
file saved in `raw/` (PDF or HTML snapshot plus a `.txt` extraction), except rows marked `derived` (arithmetic on
cited numbers, or on the project's own EIA-930 files) and rows marked `measured (project)` / `simulated (project)`
(from `out/surge/metrics.json` and README). Quotes in `facts.csv` are 15 words or fewer and were checked
string-for-string against the `.txt` extraction by `build_csvs.py`.

Rebuild: `python3 -I build_csvs.py .` (CSV files), `python3 -I pace_peak.py ../../raw/eia930` (PACE peaks),
`python3 -I h2t.py raw/*.html` (HTML to text). Scripts live here, never in `raw/`.

## What this backs

**"Is the surge number measured?"**
Half of it. One RTX 4080 Super starting a job was measured (27 W to 349 W in about 1.6 s, at a 350 W power
limit, which is above the card's 320 W reference TGP). The 1 MW site is 2,862 copies of that trace: simulated
and labeled. Real clusters do this at much larger scale. Meta (Llama 3, 16K H100s) and Google both report swings
of "tens of megawatts". Google says they can repeat every few seconds. NERC recorded a 50 MW block of a 200 MW training
site ramping at 1.9 p.u./s for about 250 ms (NERC does not state the per-unit base, so don't convert it to MW/s), and a data center dropping 450 MW to 40 MW in 36 s. Our simulated all-at-once step
is 0.81 p.u./s (813 kW on 1 MW in 1 s), so it understates rather than exaggerates. Spreading starts over 60 s
brings it to 0.016 p.u./s (15.6 kW), 52 times smaller.

**"How does Terra fit with Spin and Pulse?"**
Terra is the software layer that the Microsoft/OpenAI/NVIDIA power-stabilization paper already describes. It
says ramp limits are easy to meet by "staggering the load ramp-up across all the participating GPUs". Terra
staggers starts and slows work on the utility's call, so less is left for storage to catch. The remaining fast
swings go to hardware. NVIDIA's GB300 rack stores 65 J per GPU. Holding one 4080 Super start flat through its
worst second takes about 136 J (the area under the measured trace, 71 W to 355 W), so 65 J covers about half.
That comparison is rough: GB300 is a different GPU and also caps its own ramp-up. Torus Spin (millisecond response, 10C, full discharge in 6 minutes,
25,000 cycles) catches the second-scale residual. Torus Pulse (LFP, 0.5C, 7,500 cycles; 270 kWh to 2.2 MWh
per the older Station spec page) covers the hours-long event that Rocky Mountain Power dispatches. Lasso
dispatches in under 250 ms. Spin's per-unit kW and kWh are not published, so don't size Spin in kW on stage.

**Corrections to carry into the deck or web pages:**
- The Rocky Mountain Power program is 500 MW "being deployed" across **Utah, Wyoming, and Idaho**, three states
  per Torus's own case study, not six. It grew from a 70 MW MOU (2025-01-27). It is MOU or program scale, not
  operating MW.
- The case study gives two dispatch counts: 520 unscheduled dispatches in 18 months (RMP quote) and a "359
  unplanned events" headline. If you use one, say which.
- Spin cycle life: current pages say 25,000. The older Station spec table says "25 years, 50,000+ power cycles".
  Lead with 25,000.
- The RTX 4080 Super's reference TGP is 320 W. The measured 349 W steady draw came from a 350 W power limit.
- Torus's factory is listed as 582,000, 545,000 and 540,000 sq ft on different pages.
- Scaling: an H100 SXM is 700 W TDP, about 2.2 times a 4080 Super's 320 W. A 1 MW GPU-only site is about
  1,429 H100s, which is about 2.0 times the steady draw of the 349 W card we measured. That counts GPUs only. In a
  GB200 server, GPUs are just over 50% of provisioned power. The surge scales with total GPU watts, not GPU count.
- In decode, real inference GPUs sit far below TDP: an H200 draws 137 to 300 W of its 700 W (arXiv 2605.11999).
  Clock locking saves up to 32% of decode energy there, which matches our measured 29% for 6% slower decode.

## Not found or not verified (do not cite)
- B200 per-GPU TDP: only the DGX B200 system maximum (about 14.3 kW for 8 GPUs) was captured. H100 PCIe: NVIDIA's
  page now lists the H100 NVL (350 to 400 W) instead.
- Single-GPU steady watts: the README and brief say 344 W, but `out/surge/metrics.json` says 349.4 W. These CSVs use 349.
- Torus Spin per-unit kW and kWh ratings (not on torus.co); a "32 kWh" figure appeared only in a search summary.
- A Utah-only all-time RMP peak record. Used instead: PACE balancing-area peaks derived from EIA-930 adjusted
  demand (2026: 10,173 MW, hour ending 2026-07-20 23:00 UTC). PACE covers parts of Utah, Wyoming and Idaho.
- TOT2, TOT3 and Path 19 ratings. Only Gateway South's route and length, plus a 2022 capacity-need figure, are
  captured.
- ERCOT NOGRR 282 (ride-through for large electronic loads of 75 MW and up, filed 2025-11-14): adoption status
  and curves not captured, so it is not in the CSVs.
- The Torus $200M / 500 MW PacifiCorp MOU release on Business Wire (2025-09-09) returned 403 and was not saved.

## Files in raw/

| File | Source URL | Published |
|---|---|---|
| arxiv_2508.14318_power_stabilization.pdf/.txt | https://arxiv.org/abs/2508.14318 | 2025-08-21 (v2) |
| arxiv_2605.11999.pdf/.txt | https://arxiv.org/abs/2605.11999 | 2026-05-12 |
| arxiv_2407.21783_llama3.pdf/.txt | https://arxiv.org/abs/2407.21783 | 2024 (v3) |
| nvidia_gb300_power_smoothing_blog.html/.txt | https://developer.nvidia.com/blog/how-new-gb300-nvl72-features-provide-steady-power-for-ai/ | 2025-07-28 |
| google_cloud_balance_of_power_2025-02.html/.txt | https://cloud.google.com/blog/topics/systems/mitigating-power-and-thermal-fluctuations-in-ml-infrastructure | 2025-02-11 |
| nerc_whitepaper_characteristics_risks_large_loads_2025-07.pdf/.txt | https://www.nerc.com/globalassets/who-we-are/standing-committees/rstc/3_doc_white-paper-characteristics-and-risks-of-emerging-large-loads.pdf | 2025-07 |
| nerc_incident_review_large_load_loss_2025-01.pdf/.txt | https://nerc.com/pa/rrm/ea/Documents/Incident_Review_Large_Load_Loss.pdf | 2025-01-08 |
| nerc_level2_alert_large_loads_2025-09.pdf/.txt | https://www.nerc.com/pa/rrm/bpsa/Alerts%20DL/NERC%20Alert%20Level%202%20%20Large%20Loads.pdf | 2025 |
| nerc_reliability_insights_lcl_voltage_2026-09.pdf/.txt | https://www.nerc.com/globalassets/who-we-are/news/2026/09/reliability-insights_large-computational-load-risks-due-to-voltage-sensitivity.pdf | 2026-09 |
| nerc_timeline_large_loads.pdf/.txt | https://www.nerc.com/globalassets/initiatives/large-loads-action-plan/timeline-of-actions-completed.pdf | 2026 |
| pjm_dominion_july2026_loss_of_load.pdf/.txt | https://www.pjm.com/-/media/DotCom/committees-groups/committees/oc/2026/20260806/20260806-item-05---dominion-july-loss-of-load-event---presentation.pdf | 2026-08-06 |
| nvidia_h100 / nvidia_h200 / nvidia_dgx_b200 / nvidia_gb200_nvl72 .html/.txt | https://www.nvidia.com/en-us/data-center/{h100,h200,dgx-b200,gb200-nvl72}/ | snapshot 2026-10-27 |
| nvidia_rtx4080_family.html/.txt | https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4080-family/ | snapshot 2026-10-27 |
| amd_mi300x.html/.txt | https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html | snapshot 2026-10-27 |
| torus_*.html/.txt | https://www.torus.co/ (home, torus-flywheel, torus-nova, torus-nova-pulse, torus-lasso, torus-overwatch, utilities-electrical-utilities, industrial-landing-page, our-mission, news, customer-stories), https://torus.co/t-torus-station-overview | snapshot 2026-10-27 |
| torus_cs_*.html/.txt | https://www.torus.co/case-studies/<name> (rocky-mountain-power, jd-machine, waterford, silencerco, national-vision, american-packaging) | snapshot 2026-10-27 |
| torus_news_rmp_partnership_2025-01-27, torus_news_rmp_70mw_brief_2025-02-07, torus_spin_r-d-100 | torus.co/news/... (URLs in torus_specs.csv) | as named |

Not saved locally (read with WebFetch, cited by URL): The Register 2024-03-21, GB200 NVL72 "120kW" rack and
"1,200W GPUs" (https://www.theregister.com/2024/03/21/nvidia_dgx_gb200_nvk72); T&D World 2022-06-08, Gateway
South (https://www.tdworld.com/overhead-transmission/article/21243816/...). EIA-930 PACE peaks come from the
project's existing `data/raw/eia930/` files.
