import csv, re, sys
from pathlib import Path
OUT = Path(sys.argv[1]); RAW = OUT / "raw"
R = "2026-10-27"
U = dict(
 ps="https://arxiv.org/abs/2508.14318", pc="https://arxiv.org/abs/2605.11999", ll="https://arxiv.org/abs/2407.21783",
 nv="https://developer.nvidia.com/blog/how-new-gb300-nvl72-features-provide-steady-power-for-ai/",
 gc="https://cloud.google.com/blog/topics/systems/mitigating-power-and-thermal-fluctuations-in-ml-infrastructure",
 wp="https://www.nerc.com/globalassets/who-we-are/standing-committees/rstc/3_doc_white-paper-characteristics-and-risks-of-emerging-large-loads.pdf",
 ir="https://nerc.com/pa/rrm/ea/Documents/Incident_Review_Large_Load_Loss.pdf",
 l2="https://www.nerc.com/pa/rrm/bpsa/Alerts%20DL/NERC%20Alert%20Level%202%20%20Large%20Loads.pdf",
 ri="https://www.nerc.com/globalassets/who-we-are/news/2026/09/reliability-insights_large-computational-load-risks-due-to-voltage-sensitivity.pdf",
 pjm="https://www.pjm.com/-/media/DotCom/committees-groups/committees/oc/2026/20260806/20260806-item-05---dominion-july-loss-of-load-event---presentation.pdf",
 h100="https://www.nvidia.com/en-us/data-center/h100/", h200="https://www.nvidia.com/en-us/data-center/h200/",
 b200="https://www.nvidia.com/en-us/data-center/dgx-b200/", gb200="https://www.nvidia.com/en-us/data-center/gb200-nvl72/",
 reg="https://www.theregister.com/2024/03/21/nvidia_dgx_gb200_nvk72", r4080="https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4080-family/",
 mi="https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html",
 spin="https://www.torus.co/torus-flywheel", nova="https://www.torus.co/torus-nova", pulse="https://www.torus.co/torus-nova-pulse",
 lasso="https://www.torus.co/torus-lasso", util="https://www.torus.co/utilities-electrical-utilities", home="https://www.torus.co/",
 st="https://torus.co/t-torus-station-overview", cs="https://www.torus.co/case-studies/case-studies-rocky-mountain-power",
 jan="https://torus.co/news/rocky-mountain-power-and-torus-announce-strategic-partnership",
 feb="https://torus.co/news/technical-brief-rocky-mountain-power-and-torus-sign-mou-to-deploy-70-megawatts",
 rd="https://www.torus.co/news/torus-spin-named-winner-of-2025-r-d-100-award-for-energy-innovation",
 mis="https://www.torus.co/our-mission", ind="https://www.torus.co/industrial-landing-page",
 eia="https://www.eia.gov/electricity/gridmonitor/ (EIA-930 BALANCE files; project copy data/raw/eia930/)",
 tdw="https://www.tdworld.com/overhead-transmission/article/21243816/pacificorp-gateway-south-transmission-line-to-proceed-with-construction",
 proj="local: out/surge/metrics.json (train/surge.py); README.md")
# raw text file per source key, for quote verification
TXT = dict(ps="arxiv_2508.14318_power_stabilization.txt", pc="arxiv_2605.11999.txt", ll="arxiv_2407.21783_llama3.txt",
 nv="nvidia_gb300_power_smoothing_blog.txt", gc="google_cloud_balance_of_power_2025-02.txt",
 wp="nerc_whitepaper_characteristics_risks_large_loads_2025-07.txt", ir="nerc_incident_review_large_load_loss_2025-01.txt",
 l2="nerc_level2_alert_large_loads_2025-09.txt", ri="nerc_reliability_insights_lcl_voltage_2026-09.txt",
 pjm="pjm_dominion_july2026_loss_of_load.txt", spin="torus_spin.txt", nova="torus_torus-nova.txt", pulse="torus_torus-nova-pulse.txt",
 lasso="torus_torus-lasso.txt", util="torus_utilities-electrical-utilities.txt", home="torus_home.txt", st="torus_station_overview.txt",
 cs="torus_cs_case-studies-rocky-mountain-power.txt", jan="torus_news_rmp_partnership_2025-01-27.txt",
 feb="torus_news_rmp_70mw_brief_2025-02-07.txt", rd="torus_spin_r-d-100.txt", mis="torus_our-mission.txt", ind="torus_industrial-landing-page.txt",
 h100="nvidia_h100.txt", h200="nvidia_h200.txt", b200="nvidia_dgx_b200.txt", gb200="nvidia_gb200_nvl72.txt", r4080="nvidia_rtx4080_family.txt", mi="amd_mi300x.txt")
TITLE = dict(ps="Power Stabilization for AI Training Datacenters (Microsoft/OpenAI/NVIDIA, arXiv 2508.14318v2, Aug 2025)",
 pc="The Illusion of Power Capping in LLM Decode (Ma et al., arXiv 2605.11999, May 2026)",
 ll="The Llama 3 Herd of Models (Meta, arXiv 2407.21783)", nv="How New GB300 NVL72 Features Provide Steady Power for AI (NVIDIA blog, 2025-07-28)",
 gc="Balance of power: power and thermal fluctuations in ML infrastructure (Google Cloud blog, 2025-02-11)",
 wp="NERC white paper: Characteristics and Risks of Emerging Large Loads (July 2025)",
 ir="NERC Incident Review: Considering Simultaneous Voltage-Sensitive Load Reductions (posted 2025-01-08)",
 l2="NERC Level 2 Alert: Large Loads (2025)", ri="NERC Reliability Insights: Large Computational Load Risks Due to Voltage Sensitivity (Sept 2026)",
 pjm="PJM Operating Committee: July 22, 2026 Dominion Load Transfer Event (2026-08-06)",
 spin="Torus Spin product page", nova="Torus Station product page", pulse="Torus Pulse product page", lasso="Torus Lasso product page",
 util="Torus Electric Utilities page", home="Torus home page", st="Torus Station overview (older spec page)",
 cs="Torus case study: Rocky Mountain Power", jan="Torus/RMP press release 2025-01-27", feb="Torus/RMP technical brief 2025-02-07",
 rd="Torus Spin R&D 100 award post (2025-10-03)", mis="Torus Our Mission page", ind="Torus Industrial page",
 h100="NVIDIA H100 product page", h200="NVIDIA H200 product page", b200="NVIDIA DGX B200 product page", gb200="NVIDIA GB200 NVL72 product page",
 reg="The Register, 2024-03-21 (GTC 2024 GB200 NVL72 coverage)", r4080="NVIDIA GeForce RTX 4080 family page", mi="AMD Instinct MI300X product page",
 eia="EIA-930 Hourly Electric Grid Monitor, PACE balancing authority", tdw="T&D World, 2022-06-08, Gateway South",
 proj="Terra project measurement/simulation (train/surge.py)")
def norm(s): return re.sub(r"[^a-z0-9.%]+", " ", s.lower()).strip()
facts = []
def F(topic, fact, number, unit, k, quote, kind="reported"):
    facts.append(dict(topic=topic, fact=fact, number=number, unit=unit, source_title=TITLE[k], source_url=U[k],
                      **{"quote_≤15_words": quote}, retrieved=R, reported_or_derived=kind, _k=k))
# 1. Measured cluster swings
F("cluster_swing","Meta: Llama 3 405B trained on up to 16K H100 GPUs at 700 W TDP","16K","GPUs","ll","trained on up to 16K H100 GPUs, each running at 700W TDP")
F("cluster_swing","Meta: training-job pauses/start/stop swing data-center power by tens of MW, instantly","10s","MW","ll","fluctuations of power consumption across the data center on the order of tens of megawatts")
F("cluster_swing","Google: power fluctuations of tens of MW observed on dedicated ML clusters","10s","MW","gc","we observed power fluctuations in the tens of megawatts (MW)")
F("cluster_swing","Google: ramps nearly instantaneous and repeat every few seconds","few","s","gc","the ramp speed could be almost instantaneous, repeat as frequently as every few seconds")
F("cluster_swing","Google: compiler-based smoothing cut fluctuation magnitude ~50% with <1% performance impact","50","%","gc","the magnitude of power fluctuations dropped by nearly 50%")
F("cluster_swing","Microsoft/OpenAI/NVIDIA: swings can reach tens or hundreds of MW","10s-100s","MW","ps","these swings can amount to tens or hundreds of megawatts")
F("cluster_swing","Microsoft/OpenAI/NVIDIA: swing amplitude scales with GPU count and per-GPU peak power","","","ps","grows proportionally with the number of GPUs participating in the job")
F("oscillation","AI training power FFT energy concentrated at 0.2-3 Hz, near turbine/line resonances","0.2-3","Hz","ps","FFT energy concentrated between 0.2–3 Hz")
F("oscillation","Example utility frequency spec: critical range 0.1-20 Hz","0.1-20","Hz","ps","A critical frequency range, e.g., 0.1 − 20 Hz.")
F("ramp_spec","Utility time-domain specs are expressed as ramp rate in MW/s","","MW/s","ps","typically expressed in megawatts per second (MW/s)")
F("ramp_spec","Microsoft/OpenAI/NVIDIA: ramp specs are easy to meet by staggering GPU ramp-up (Terra's mechanism)","","","ps","staggering the load ramp-up across all the participating GPUs")
F("ramp_spec","Example: a 10 MW dynamic range on a 100 MW job (10%) cannot be met by GPU smoothing alone today","10","MW","ps","the utility company requires us to meet a 10MW dynamic range")
F("mitigation_cost","GB200 power floor at 90% of TDP costs 10.5% extra energy on a real training waveform","10.5","%","ps","we note a total energy overhead of 10.5% due to the power smoothing feature")
F("mitigation","GB200 power-floor demo set at 65% of TDP","65","% of TDP","ps","The power floor was set to 65% of the TDP of the GPU.")
F("mitigation","GPUs are more than 50% of server provisioned power (GB200 server)","50","%","ps","GPUs contribute more than 50%")
F("mitigation","Paper names rack-level energy storage as the best place for storage","","","ps","a rack-level energy storage emerges as the best option.")
F("cluster_swing","NERC: 50 MW block of a 200 MW AI training data center starting a run","50 of 200","MW","wp","a 50 MW block of a larger 200 MW AI training data center")
F("ramp_rate","NERC: fastest ramp 1.9 p.u./s for ~250 ms at that training site (p.u. base not stated)","1.9","p.u./s","wp","the demand changes at a rate of 1.9 p.u. per second for about 250 milliseconds")
F("ramp_rate","NERC: training/checkpoint transitions can happen in under one second","<1","s","wp","the transition from training to saving checkpoint progress")
F("ramp_rate","NERC: a North American data center ramped ~450 MW to ~40 MW within 36 s","410 in 36","MW in s","wp","ramping down from about 450 MW to about 40 MW within 36 seconds")
F("ramp_rate","Derived: 450->40 MW in 36 s is ~11.4 MW/s average","11.4","MW/s","wp","ramping down from about 450 MW to about 40 MW within 36 seconds","derived")
F("ramp_rate","NERC: xAI Colossus (Memphis) training changes load 35-70 MW within a minute","35-70","MW/min","wp","can change the loading 35–70 MW or more within a minute")
F("ramp_rate","NERC: crypto mine ramped down 298 MW within 25 s","298 in 25","MW in s","wp","a load ramp down 298 MW within 25 seconds")
F("oscillation","NERC: 2023 Midwest data center produced a 1 Hz forced oscillation","1","Hz","wp","A 1 Hz forced oscillation occurred")
F("oscillation","NERC: AI inference does not show the training/checkpoint ramps","","","wp","not observed in current AI inference")
F("load_loss","NERC: 230 kV fault -> ~1,500 MW of data-center load dropped at once (Virginia, 2024-07-10)","1500","MW","ir","simultaneous loss of approximately 1,500 MW of")
F("load_loss","NERC: ~1,260 MW dropped at the third reclose and stayed off for hours","1260","MW","ir","approximately 1,260 MW of load dropped off the electric grid")
F("load_loss","Frequency rose to 60.047 Hz, back to 60.0 Hz in ~4 min","60.047","Hz","ir","Frequency rose to a high of 60.047 Hz")
F("load_loss","Data center UPS blocks typically 2-5 MW","2-5","MW","ir","typically in the range of 2–5 MWs")
F("load_loss","NERC Level 2 alert: multiple events with 1,000+ MW unexpected large-load reduction, mostly 2024-2025","1000+","MW","l2","1,000+ MW of unexpected Large Loads output")
F("load_loss","PJM: 2026-07-22 Dominion event, ~3,800 MW transferred to backup (largest PJM has seen)","3800","MW","pjm","approximately 3,800 MW of load transferred to back-up generation")
F("load_loss","PJM 2026-07-22: frequency reached 60.092 Hz","60.092","Hz","pjm","Frequency reached 60.092 Hz")
F("load_loss","PJM 2026-07-22: reporting ACE reached +3,928 MW","3928","MW","pjm","Reporting ACE reached +3,928 MWs")
F("load_loss","NERC 2026: April 18, 2026 repeat fault lost only 500 MW after ride-through fixes","500","MW","ri","this April 2026 event saw only 500 MW")
F("rack_storage","NVIDIA GB300 PSU stores 65 J per GPU in capacitors","65","J/GPU","nv","65 joules per GPU of energy storage")
F("rack_storage","NVIDIA: GB300 shelves cut peak grid demand 30% training Megatron (vendor test vs GB200 PSU)","30","%","nv","reduce peak grid demand by 30% when training the Megatron LLM")
F("rack_storage","NVIDIA: generation can take 1 to 90 minutes to respond to a sudden ramp-up","1-90","min","nv","it can take one minute to 90 minutes for generation resources to respond")
F("rack_storage","NVIDIA: GB300 ramps start with a power cap raised gradually at grid-tolerable ramp rates","","","nv","aligning with the ramp rates the grid can tolerate")
F("rack_storage","NVIDIA: the feature is also coming to GB200 NVL72","","","nv","And it’s also coming to GB200 NVL72 systems.")
# 2. GPU efficiency
F("clock_lock","H200 LLM decode draws only 137-300 W on a 700 W GPU; power caps never trigger","137-300","W","pc","decode draws only 137–300 W on a 700 W GPU; no cap ever triggers")
F("clock_lock","SM clock locking recovers up to 32% of decode energy at <1% throughput loss (H200)","32","%","pc","recovering up to 32% of decode energy at minimal throughput loss")
F("terra_measured","Terra: RTX 4080 Super clock lock cut 276 W -> 196 W (-29%) for 6% less decode speed","29","%","proj","","measured (project)")
F("terra_measured","Terra: one RTX 4080 Super starting prefill goes 27 W idle -> 349 W steady in ~1.6 s at a 350 W power limit","27->349","W","proj","","measured (project)")
F("terra_measured","Terra: measured steady 349 W exceeds the 4080 Super reference TGP of 320 W because the run used a 350 W limit","349 vs 320","W","r4080","Total Graphics Power (W)","derived")
F("terra_simulated","Terra: 1 MW site = 2,862 such GPUs; all-at-once start = 813 kW rise in 1 s","813","kW in 1 s","proj","","simulated (project)")
F("terra_simulated","Terra: same site with starts spread over 60 s = 15.6 kW rise in 1 s (52x smaller)","15.6","kW in 1 s","proj","","simulated (project)")
F("comparison","Derived: Terra's simulated at-once step is 0.81 p.u./s (813 kW/1 MW/1 s) vs NERC's measured 1.9 p.u./s - the simulation is not exaggerated","0.81 vs 1.9","p.u./s","wp","the demand changes at a rate of 1.9 p.u. per second","derived")
F("comparison","Derived: staggered starts give 0.016 p.u./s (15.6 kW/1 MW/1 s), ~120x below NERC's measured training ramp","0.016","p.u./s","proj","","derived")
F("comparison","Derived: holding one 4080 Super start flat through its worst 1 s (71->355 W) takes ~136 J (integral of the trace); GB300 caps store 65 J/GPU, about half (GB300 also caps ramp-up, different GPU)","136 vs 65","J","nv","65 joules per GPU of energy storage","derived")
F("scaling","Derived: H100 SXM TDP 700 W vs RTX 4080 Super TGP 320 W = 2.19x; a 1 MW GPU-only site = ~1,429 H100s at TDP","1429","GPUs/MW","h100","Up to 700W (configurable)","derived")
# 3. Utah grid
F("utah_grid","Derived: PACE (PacifiCorp East BA, incl. Utah) 2026 peak hourly demand 10,173 MW, hour ending 2026-07-20 23:00 UTC (17:00 MDT)","10173","MW","eia","","derived")
F("utah_grid","Derived: PACE annual peak (EIA adjusted demand) 2022 9,494 / 2023 8,941 / 2024 9,562 / 2025 9,717 / 2026 10,173 MW","9494;8941;9562;9717;10173","MW","eia","","derived")
F("utah_grid","Gateway South: ~400 miles, Aeolus (WY) to Clover substation near Mona, Utah; planned late 2024","400","miles","tdw","extend approximately 400 miles from the Aeolus Substation near Medicine Bow, Wyoming")
F("utah_grid","T&D World 2022: PacifiCorp capacity need expected 1,627 MW (context for Gateway)","1627","MW","tdw","the capacity need is expected to be 1,627 megawatts.")
# Torus context in facts
F("torus","RMP+Torus: 500 MW DR capacity being deployed behind the meter in Utah, Wyoming, Idaho","500","MW","cs","across Utah, Wyoming, and Idaho")
F("torus","RMP case study: Torus sites ramp in under 20 s","<20","s","cs","Distributed assets that ramp in <20 seconds with a target power of ~100%.")
F("torus","RMP quote: Torus sites dispatched 520 times over 18 months, unscheduled","520","dispatches","cs","We've dispatched commercial Torus sites 520 times over the past 18-months")
F("torus","RMP dispatches stored energy in less than 1% of hours per year","<1","% of hours","cs","less than 1% of hours per year")
F("torus","Torus Lasso dispatch latency","<250","ms","lasso","Sub-250ms dispatch")
# validate quotes
bad = 0
for f in facts:
    q = f["quote_≤15_words"]; k = f.pop("_k")
    n = len(q.split())
    if n > 15: print("TOO LONG", n, q); bad += 1
    if q and k in TXT:
        t = norm((RAW / TXT[k]).read_text(errors="replace"))
        if norm(q) not in t: print("NOT FOUND", k, q); bad += 1
cols = ["topic","fact","number","unit","source_title","source_url","quote_≤15_words","retrieved","reported_or_derived"]
with open(OUT/"facts.csv","w",newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(facts)
gpus = [
 ["RTX 4080 SUPER","320","246 (NVIDIA avg gaming); 349 measured steady prefill at 350 W limit; 276 decode -> 196 with clock lock (Terra)","16 GB GDDR6X",U["r4080"]],
 ["RTX 4080","320","251 (NVIDIA avg gaming)","16 GB GDDR6X",U["r4080"]],
 ["H100 SXM","700","","80 GB HBM3, 3.35 TB/s",U["h100"]],
 ["H100 NVL (PCIe card)","350-400","","94 GB, 3.9 TB/s",U["h100"]],
 ["H200 SXM","700","137-300 W in LLM decode (arXiv 2605.11999)","141 GB HBM3e, 4.8 TB/s",U["h200"]+" ; "+U["pc"]],
 ["H200 NVL","600","","141 GB HBM3e, 4.8 TB/s",U["h200"]],
 ["DGX B200 (8x B200 system)","~14,300 system max (not per GPU)","","1,440 GB total (8 GPUs)",U["b200"]],
 ["GB200 Blackwell GPU (in GB200 superchip)","1,200 (press, GTC 2024)","","",U["reg"]],
 ["GB200 NVL72 rack (72 GPUs + 36 Grace CPUs)","~120,000 per rack (press, GTC 2024)","","13.4 TB HBM3e per rack (NVIDIA page)",U["reg"]+" ; "+U["gb200"]],
 ["AMD Instinct MI300X","750 (peak)","","192 GB HBM3, 5.3 TB/s",U["mi"]],
]
with open(OUT/"gpu_specs.csv","w",newline="") as fh:
    w = csv.writer(fh); w.writerow(["gpu","tdp_w","typical_inference_w_if_published","memory","source_url"]); w.writerows(gpus)
T = [
 ["Spin","C-rating","10","C",U["spin"]],
 ["Spin","full-cycle discharge time","6","minutes",U["spin"]],
 ["Spin","response time","milliseconds (no number on product page)","",U["spin"]],
 ["Spin","response time (R&D 100 post)","<250","ms",U["rd"]],
 ["Spin","cycle life (current pages)","25,000","cycles",U["spin"]],
 ["Spin","cycle life (older Station spec table; conflicts)","50,000+ over 25 years","cycles",U["st"]],
 ["Spin","power-to-energy vs traditional BESS","20","x",U["spin"]],
 ["Spin","per-unit power rating","not published on torus.co as of 2026-10-27","kW",U["spin"]],
 ["Spin","per-unit energy rating","not published on torus.co as of 2026-10-27","kWh",U["spin"]],
 ["Spin","recyclable materials","95","%",U["rd"]],
 ["Pulse","chemistry","LFP","",U["pulse"]],
 ["Pulse","C-rating","0.5","C",U["pulse"]],
 ["Pulse","cycle life","7,500","cycles",U["pulse"]],
 ["Pulse","sizing (older Station spec table)","270 kWh - 2.2 MWh (expandable to 40 MWh)","kWh",U["st"]],
 ["Pulse","round-trip efficiency (older Station spec table)","93","%",U["st"]],
 ["Pulse","lifespan when paired with Spin (older Station spec table)","20","years",U["st"]],
 ["Station","system size","modular, up to 100+","MW",U["nova"]],
 ["Station","lifespan","25","years",U["nova"]],
 ["Station","contract to operation","12-16","weeks",U["nova"]],
 ["Station","fleet uptime","99.9","%",U["nova"]],
 ["Station","certifications","UL 9540; IEEE 1547","",U["nova"]],
 ["Station","ramp to full power (utility dispatch)","<30","s",U["util"]],
 ["Station","facility size range served","500 kW machine shop to 15 MW plant","",U["ind"]],
 ["Lasso","dispatch latency","<250","ms",U["lasso"]],
 ["Lasso","uptime","99.9","%",U["lasso"]],
 ["RMP program","flexible capacity (being deployed; MOU scale, not operating MW)","500","MW",U["cs"]],
 ["RMP program","states","Utah, Wyoming, Idaho (3, not 6)","",U["cs"]],
 ["RMP program","ramp time (case-study headline)","19","s",U["cs"]],
 ["RMP program","unscheduled dispatches over 18 months (RMP quote)","520","events",U["cs"]],
 ["RMP program","unplanned events (case-study headline; differs from 520)","359","events",U["cs"]],
 ["RMP program","original MOU (2025-01-27)","70","MW",U["jan"]],
 ["RMP program","homes equivalent of 70 MW","~20,000","homes",U["jan"]],
 ["RMP program","response time in technical brief","<250","ms",U["feb"]],
 ["RMP program","system uptime in technical brief","99","%",U["feb"]],
 ["Company","US manufacturing facility","582,000 (mission page); 545,000 (Station page); 540,000 (2026-02 news)","sq ft",U["mis"]],
 ["Company","funding raised","267","$M",U["mis"]],
]
with open(OUT/"torus_specs.csv","w",newline="") as fh:
    w = csv.writer(fh); w.writerow(["product","spec","value","unit","source_url"]); w.writerows(T)
print(len(facts), "facts;", len(gpus), "gpus;", len(T), "torus rows; problems:", bad)
