# Sites: real data center sizes for Terra's four routing regions

Retrieved 2026-10-27. Collected to replace the simulated `SITE_GPUS` in `router/src/capacity.ts`
(PACE 1,000 / CISO 800 / BPAT 600 / ERCO 800 GPUs). This folder only gathers the data; nothing in `router/` was changed.

## Files

| File | Rows | What |
|---|---|---|
| `sites.csv` | 26 | Utah 11, California 4, PNW 5, Texas 6. The SVP aggregate (714 MW peak, 55 DCs) is context only, not a row |
| `utah_load_growth.csv` | 16 | Utah statewide data center MW, PacifiCorp IRP sensitivities, the PSC large-load docket, SB 132 threshold |
| `raw/` | 9 files, ~23 MB | PDFs and Epoch CSVs, as downloaded. Never executed. Text extracted with `pdftotext`. |

`lat`/`lon` are left blank: no source gave coordinates, and none were geocoded. Epoch street addresses are in `notes`.
Every `mw` is **reported** by the cited source (operator, press, regulator, aggregator or Epoch estimate). The only
**derived** numbers are in "What this replaces" below.

## Sources

### Primary documents (downloaded to raw/)
| File in raw/ | Source | URL | Used for |
|---|---|---|---|
| `343770Aplctn2-10-2026.pdf` | RMP Application, Utah PSC Docket 26-035-05 (filed 2026-02-10) | https://pscdocs.utah.gov/electric/26docs/2603505/343770Aplctn2-10-2026.pdf | First Large Load contract: >100 MW, executed 2026-01-20 (¶3–5, ¶21). Customer/site/MW are redacted. |
| `343771RdctdRMPDirTstmnyCraigEller2-10-2026.pdf` | Redacted direct testimony of Craig M. Eller, same docket | https://pscdocs.utah.gov/electric/26docs/2603505/343771RdctdRMPDirTstmnyCraigEller2-10-2026.pdf | Large Load Act 100 MW threshold (lines 40–51); interconnection paid by "the facility developer that is hosting Customer's infrastructure" (line 329). |
| `339034RMP2025IRPVlmI3-31-2025.pdf` | PacifiCorp 2025 IRP Vol I, Utah PSC Docket 25-035-22 | https://pscdocs.utah.gov/electric/25docs/2503522/339034RMP2025IRPVlmI3-31-2025.pdf | Large-metered load sensitivity (printed p.279), Table 10.3 (p.307), large loads outside planning (p.231 fn 5). |
| `339035RMP2025IRPVlmII3-31-2025.pdf` | PacifiCorp 2025 IRP Vol II (appendices) | https://pscdocs.utah.gov/electric/25docs/2503522/339035RMP2025IRPVlmII3-31-2025.pdf | App. A "High Data Center Scenario" (printed p.18). MW appear only in a chart (Figure A.5). |
| `342089RMPCmnts10-3-2025.pdf` | RMP comments, Utah PSC Docket 25-035-30 (2025-10-03) | https://pscdocs.utah.gov/electric/25docs/2503530/342089RMPCmnts10-3-2025.pdf | Utah 2025 IRP forecast is ~700 MW below the 2023 IRP Update forecast (p.2). |
| `2025_DataCenter_FactSheet_UT.pdf` | Western Resource Advocates, 2025 Data Center Fact Sheet (UT) | https://westernresourceadvocates.org/wp-content/uploads/2025/08/2025_DataCenter_FactSheet_UT.pdf | 6,000 MW (2030) / 7,000 MW (2035) system-wide data-center sensitivity; +511 MW Utah 2030 peak. |
| `epoch/data_centers.csv`, `epoch/data_center_timelines.csv`, `epoch/data_centers_chip_quantities.csv` | Epoch AI, Frontier AI Data Centers dataset (CC-BY 4.0) | https://epoch.ai/data/ai-data-centers | IT MW, facility MW and H100e for Meta Eagle Mountain, QTS Eagle Mountain, The Dalles, Hillsboro, Abilene, Temple, Denton, Midlothian, SAT40, Shackelford. |

**Epoch caveat:** Epoch's MW are *estimates* built from satellite imagery, permits and cooling-equipment counts. They are
not operator disclosures. `sites.csv` puts IT MW in `mw` and facility MW in `notes`. Epoch's H100-equivalent counts are
estimates too, so they stay out of `gpu_count_if_public` and appear only in `notes`.

### Secondary / web (cited per row in the CSVs)
- Kem C. Gardner Policy Institute figures, via KSL (2026-04-15): https://www.ksl.com/article/51483867/heres-how-utah-can-navigate-the-data-center-boom
  The original Gardner PDF, https://le.utah.gov/interim/2026/pdf/00003188.pdf, **could not be fetched on 2026-10-27**.
  le.utah.gov refused connections and the Wayback Machine returned a 404. The 735 MW "top 10" figure comes from a search
  snippet of that PDF and has not been checked against the document.
- Stargate Abilene GPU counts: DCD (400k GB200 via FT, 1.2 GW): https://www.datacenterdynamics.com/en/news/oracle-to-spend-40bn-on-nvidia-chips-for-openai-texas-data-center/ ;
  Ellison ">450,000 GB200": https://www.datacenterdynamics.com/en/news/openai-and-oracle-to-deploy-450000-gb200-gpus-at-stargate-abilene-data-center/
- Santa Clara stranded capacity: Bloomberg 2025-11-10 https://www.bloomberg.com/news/articles/2025-11-10/data-centers-in-nvidia-s-hometown-stand-empty-awaiting-power ;
  48 MW each comes from https://cloudnews.tech/silicon-valley-builds-data-centers-it-cant-power-on-nearly-100-mw-in-santa-clara-waiting-for-the-grid/
- SVP 714 MW peak / 55 data centers: https://www.ncpa.com/wp-content/uploads/2025/09/Nico-Procos-Presentation-NCPA-2025-Annual-Conference.pdf
- Novva 175 MW: https://www.stblaw.com/about-us/news/view/2025/03/04/cim-group-and-novva-data-centers-enter-into-$2-billion-construction-loan-for-development-of-175-mw-data-center-campus
- Grant County PUD (Quincy) large-load queue, for context only: 75 applicants, 2,897 MW peak; Quincy 1,578 MW.
  https://www.publicpower.org/periodical/article/grant-county-pud-details-queue-power-service-requests-large-load-customers
- Aggregator listings (Cleanview, Baxtel, DataCenterMap, Ocolo) are marked in the row notes. They are lower confidence
  and should not be used as anchors.

### Not done / skipped
- PacifiCorp OASIS large-load queue: not found as a public load spreadsheet within the time box. LBNL "Queued Up" covers generation only, so it was skipped.
- PNNL IM3 atlas and Overpass/OSM: skipped to stay inside the time box.
- The 2025 IRP's own data-center sensitivity MW appear only as a chart. The 6,000 / 7,000 MW numbers are WRA's reading of the IRP.

### Region labels
`region` is the routing grid Terra uses. It does not always match the facility's actual balancing authority:
- Quincy, WA is in the Grant County PUD BA, and Hillsboro, OR is in the PGE BA. Neither is BPAT, so both are PNW proxies.
  The Dalles is served by Northern Wasco PUD, a BPA wholesale customer; its BA was not verified.
- Santa Clara sites are served by Silicon Valley Power, a municipal utility inside the CAISO BA.
- The Delta/Millard sites (Joule, Creekstone) are labeled PACE by location but are largely behind-the-meter gas.

## What this replaces (derived)

The current simulation uses 276 W per GPU (an RTX 4080 equivalent). At that rate a simulated site draws:
`1,000 × 276 W = 0.276 MW` (Utah), `800 × 276 W = 0.221 MW` (CA, TX), `600 × 276 W = 0.166 MW` (PNW).
Each real site below is 100 to 1,000 times larger. Reading a simulated site as a real one would overstate how
representative the demo is, so there are two honest framings:

**A. Keep the GPU counts and label each site as a small slice of a real campus** (share = sim MW ÷ real IT MW):

| Sim site | Real anchor (reported IT MW) | Arithmetic (derived) | Sim = share of anchor |
|---|---|---|---|
| Utah (PACE), 1,000 GPUs | **Meta Eagle Mountain, 133 MW IT** (Epoch est., operating, Rocky Mountain Power–served) | 133,000,000 W ÷ 276 W ≈ **481,884** RTX-4080-eq | 0.276 ÷ 133 ≈ **0.21%** |
| California (CISO), 800 GPUs | **Digital Realty SJC37, 48 MW** (built, waiting on SVP power) | 48,000,000 ÷ 276 ≈ **173,913** | 0.221 ÷ 48 ≈ **0.46%** |
| PNW (BPAT), 600 GPUs | **Google The Dalles, 154 MW IT** (Epoch est.) | 154,000,000 ÷ 276 ≈ **557,971** | 0.166 ÷ 154 ≈ **0.11%** |
| Texas (ERCO), 800 GPUs | **Meta Temple, 178 MW IT** (Epoch est.) | 178,000,000 ÷ 276 ≈ **644,928** | 0.221 ÷ 178 ≈ **0.12%** |

Alternative anchors: for Utah, **Novva West Jordan, 175 MW** (operator financing announcement) works out to 634,058
equivalents, so the sim is ~0.16% of it. For Texas, **Stargate Abilene, 421 MW IT** works out to 1,525,362 equivalents,
so the sim is ~0.05% of it. Abilene also has a public GPU figure: ~400k–450k GB200 announced.

**B. Rescale `SITE_GPUS` so the relative sizes match the anchors.** Using the IT MW ratios
133 : 48 : 154 : 178 with Utah held at 1,000 gives roughly **PACE 1,000 / CISO 361 / BPAT 1,158 / ERCO 1,338**
(48/133×1000 = 361; 154/133×1000 = 1,158; 178/133×1000 = 1,338). The site sizes become proportional to real
campuses, but the absolute scale is still about 1/480 of real. This is derived and does not change the in-house load share.

**Recommended Utah anchor:** use Meta Eagle Mountain. It is the one Utah site that is both operating and has an
evidence-based MW figure (Epoch: 133 MW IT / 179 MW facility as of 2026-05-02), and it sits on Rocky Mountain Power's
grid, which is the utility that would make the curtailment call. Novva West Jordan (175 MW) is the better story
for a third-party routing target, because it is colocation and RMP couldn't serve its full load in time, so it
added ~200 MW of on-site gas. Its MW, however, comes from a financing press release, not a measurement.

**Single strongest citable fact:** Utah PSC Docket 26-035-05 (RMP Application ¶3–5, filed 2026-02-10) is the first
contract under Utah's 2025 Large Load Act (SB 132). In it, Rocky Mountain Power agreed on 2026-01-20 to firm,
full-requirements service for a customer whose load "exceeds 100 MW". The customer and site are redacted.
For the statewide headline (secondhand via KSL, citing the Gardner Institute): Utah has 48 operating data centers
totaling more than 920 MW, and 7 under construction add about 2,600 MW by 2028, of which about 1,700 MW is
behind-the-meter or off-grid.
