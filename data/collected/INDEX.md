# Collected real data (2026-10-27 evening)

Six agents went after every item that is simulated, a stand-in, or uncited in "What's real and what's
simulated" (README) and the judge Q&A in `deck/script.md`. Nothing outside `data/collected/` was changed:
deck/, demo/, web/, router/src/, train/ and README.md are claimed by other sessions. Each folder has a
`SOURCES.md` with URLs, retrieval dates, and reported vs derived. Total ~770 MB, mostly downloaded raw files.

## What each dataset replaces

| Folder | Replaces | What's real now | To use it |
|---|---|---|---|
| `dr-events/` | "RMP doesn't publish when it calls" (server.ts:29, `web/data/dr_event.json`, script.md Q&A) | **That claim is wrong.** RMP's annual Utah DSM reports to the PSC list every event. `events.csv`: 1,048 rows, 2022–2025. Wattsmart Business: 24 calls 2023–25, 15–60 min (mostly 20), January to December, incl. 1:23 AM; 2.7–4.5 h a year of the 65 h cap. None in Oct 19–25. | Script line: easy ("RMP's Business calls are 15–60 minutes; the demo stretches one to 2 hours so it's visible at replay speed"). A real-length 20 min call is NOT a JSON edit: the router and web `step()` tick hourly, and the week's $122 is per called hour, so it means router + web changes (claimed files) |
| `carbon/` | "Average carbon from EIA fuel + IPCC factors. Not marginal." | EPA AVERT 2023, eGRID2023, NREL Cambium 2024 (short- and long-run marginal) for PACE/CISO/BPAT/ERCO, plus a month × hour profile. Margin is ~450–750 g/kWh in all four; BPAT is 7× cleaner than PACE on average but ~1.3× at the margin. Our averages are lifecycle; AVERT/eGRID/Cambium are direct combustion (Cambium's lifecycle columns are in the CSV). Our PACE average (471) is low: eGRID's PACE coal rate is ~1,088 vs IPCC 820. | Q&A line: easy. Marginal in routing: swap the per-region `gco2` table (train/router, claimed) |
| `sites/` | Simulated sites of 1,000 / 800 / 600 / 800 GPUs (`router/src/capacity.ts` SITE_GPUS) | `sites.csv`: 26 real sites with MW (Utah 11). Anchor: Meta Eagle Mountain 133 MW IT (Epoch AI estimate). Utah PSC Docket 26-035-05: first SB 132 large-load contract (>100 MW), 2026-01-20. The simulated Utah site (0.28 MW) is ~0.2% of the anchor. | Label as "a slice of a real site": easy. Rescale SITE_GPUS: claimed file |
| `jobs/` | Illustrative JOBS list (router/src/server.ts:52) | Alibaba 2026 (155K GPUs): 53% of GPU-hours online inference (can't move), 42% training + offline (could wait). Caveat: 90% of training runs at guaranteed priority. PAI 2020 job-size percentiles; Azure LLM 2024 diurnal curve (peak 1.52× mean). `job_mix.csv` is in Terra's job shape, deadline rule labeled derived. | Cite the 42% / 53%: easy. Swap JOBS: claimed file |
| `live-apis/` | Replay-only data | Keyless, tested live 10-27 ~23:00 UTC: EIA-930 grid-monitor JSON (all 4 regions, <1 h behind), CAISO Outlook + OASIS, ERCOT dashboards, BPA 5-min, Open-Meteo, NWS. `scripts/live_now.py` gets current-hour demand for all four regions. `tomorrow_weather.json` covers 10-28. Feed the model EIA (CISO in EIA runs 5–8 GW above CAISO Outlook). CISO demand ran 27% over EIA's forecast at 22 UTC on 10-27; that's in the source, not a script bug: `hourly_v2.parquet` shows CISO demand 10–24% over forecast at 15–22 UTC all October 2026. | Wiring a live mode touches router (claimed) |
| `hardware/` | "Is the surge real?", Torus fit | 59 cited facts. Microsoft/OpenAI/NVIDIA (arXiv 2508.14318) name staggering GPU ramp-up as the fix: Terra's method. NERC: a real site ramped faster than our simulated one, so ours is conservative. PJM 2026-07-22: ~3,800 MW of data centers dropped at once. Torus+RMP program is 3 states (UT, WY, ID), not 6. Spin kW/kWh aren't published. | Slide/Q&A cites: easy |

| `nasa-power/` | Nothing yet (named on the slide, never pulled) | NASA POWER hourly satellite sunlight, temperature and wind for SLC, Milford, Cedar City and Delta, 2025-01-01 to 2026-07-31 (solar lags ~3 months, so no replay week or Wednesday). | Satellite check on the solar forecaster: new script, no claimed files |

## Against the Torus slide's data list

| Slide source | Status |
|---|---|
| EIA | Used: EIA-930 (training), EIA-860M (expansion slide), live grid-monitor JSON |
| CAISO | Used: OASIS PACE real-time prices; live Outlook + day-ahead tested |
| ERCOT | Partly: Texas grid comes through EIA-930; ERCOT's own dashboards tested live (`live-apis/`), its prices unused; its API needs a free key |
| Open-Meteo | Used: archived forecasts for 51 grids + solar sites; Wednesday's forecast saved |
| Electricity Maps | Not used: needs an account (free tier/trial, average carbon only); the data portal blocks unsigned access. AVERT/eGRID/Cambium cover carbon |
| NREL | Used: Cambium marginal carbon (`carbon/`). NSRDB/PVWatts need a key (NREL is now NLR) |
| NASA POWER | Pulled tonight (`nasa-power/`) |
| Cluster traces | Collected: Alibaba 2020/2026, Azure LLM 2023/2024 (`jobs/`) |

## Settle before judging

- `deck/index.html` changed at 17:06 during the sweep. It has nothing from these folders, so it's most likely another session's edit; no agent reported touching it.

- **344 W or 349 W?** README and the script say the 4080 reaches 344 W; `out/surge/metrics.json` says 349.4 W.
- **"Six states"** is only in `~/Documents/Research/2026-10-27-torus-dissection.md`, not in the deck or web pages.
- **Spin cycle life:** use 25,000 (current Torus pages); an older page says 50,000+.

## Agent rule slips (for the record)

- live-apis: one early NWS request carried Granite's email in its User-Agent; no saved file contains it.
  One PVWatts call used NREL's public `DEMO_KEY`.
- The Gardner Institute numbers in `sites/` (48 Utah data centers, >920 MW) are secondhand via KSL; le.utah.gov refused connections.
- The 2026 Alibaba trace folders have no license file. Azure and PAI 2020 are CC-BY 4.0.
