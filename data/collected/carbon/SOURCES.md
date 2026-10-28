# Carbon: marginal emission factors for Terra's four routing regions

Collected 2026-10-27 for the Torus "Energy x AI Infrastructure" judging. Only free, public data. No accounts were
created, no keys were used, and no macros were run. `build_carbon_tables.py` rebuilds both CSVs from `raw/`:

```
uv run --with pandas --with openpyxl --with pyarrow python -I data/collected/carbon/build_carbon_tables.py
```

## Files

| File | What it is |
|---|---|
| `marginal_by_region.csv` | 116 rows: region (PACE/CISO/BPAT/ERCO) x source (AVERT, eGRID, Cambium, Cambium-hist, project) x metric. Native value + units, plus a `kg_per_MWh` column (1 lb = 0.45359 kg; kg/MWh = g/kWh, the unit Terra uses). Columns `emissions_scope`, `granularity`, `reported_or_derived` and `notes` say what each number is. |
| `hourly_profile_month_hour.csv` | 1,152 rows = 4 regions x 12 months x 24 hours. Cambium 2024 Mid-case **2025** SRMER, LRMER (combustion CO2 and combustion+precombustion CO2e), consumption-based average, plus `terra_avg_lifecycle_2025` = Terra's own 2025 average for the same month-hour. Hours are **local standard time, hour-beginning** (Cambium's convention; Terra's column was recomputed from UTC with fixed offsets: PACE -7, CISO/BPAT -8, ERCO -6). |
| `build_carbon_tables.py` | Extraction script (reads raw/ as data only). |
| `raw/avert/avert_emission_rates_04-11-24_0.xlsx` | EPA AVERT v4.3 avoided emission rates, data years 2017–2023 (260 KB). |
| `raw/egrid/egrid2023_data_rev2.xlsx` | EPA eGRID2023 rev 2 full data file (21 MB). |
| `raw/cambium/Cambium24_Workbook.xlsx` | NLR (formerly NREL) Cambium 2024 workbook: LRMER and costs only, levelization tool (26 MB). |
| `raw/cambium/sv/*.zip` + extracted `annual/`, `monthhour/`, `historical/` | Cambium 2024 Scenario Viewer files: all scenarios, GEA regions, annual (0.3 MB zip) and month-hour (26 MB zip, 81 MB CSV); GEA historical intensities 2014–2023 (eGRID-derived). |
| `raw/docs/avert-user-manual-v4.3.pdf` | Used for the region mapping (Table 6, state apportionment). |

raw/ total: about 157 MB.

## Sources

| Source | URL | Retrieved | License / terms | Used as |
|---|---|---|---|---|
| EPA AVERT v4.3 emission rates (released 2024-04-11; 2023 is the latest data year, and no 2024 rates were found) | https://www.epa.gov/system/files/documents/2024-04/avert_emission_rates_04-11-24_0.xlsx (page: https://www.epa.gov/avert/avoided-emission-rates-generated-avert) | 2026-10-27 | US federal government work (public domain) | Reported annual marginal CO2 rates. The region mapping is derived (see below). |
| EPA AVERT User Manual v4.3 | https://www.epa.gov/system/files/documents/2024-04/avert-user-manual-v4.3.pdf | 2026-10-27 | US gov | Region definitions |
| EPA eGRID2023 rev 2 (released 2025-06-12; latest) | https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx (page: https://www.epa.gov/egrid/download-data) | 2026-10-27 | US gov (public domain) | Reported BA and subregion average, non-baseload, and combustion-only rates |
| NLR Cambium 2024 (released March 2025; latest is the 5th annual edition), Scenario Viewer files | https://scenarioviewer.nlr.gov/ → project "Cambium 2024" → Download (file ids 69141 annual GEA, 69143 month-hour GEA, 69180 historical intensities). Docs: https://www.nlr.gov/docs/fy25osti/93005.pdf | 2026-10-27 | DOE/NLR disclaimer on the viewer: reference use, no warranty, and "the user agrees to credit" DOE/NLR/Alliance in publications. There was no login or click-through. **Cite as: NLR, Cambium 2024.** | Reported modeled SRMER/LRMER. The GEA mapping is derived. |
| NLR Cambium 2024 workbook | https://data.nlr.gov/submissions/289 (file https://data.nlr.gov/system/files/289/1744314776-Cambium24_Workbook.xlsx) | 2026-10-27 | The data catalog links a license page that returned 404 when fetched, so no license was confirmed beyond the DOE/NLR credit clause | Cross-check: its LRMER values match the viewer CSV (e.g. CAISO 2025 Mid-case 228.3 kg/MWh) |
| Terra's own average | `data/train/hourly_v2.parquet`, built by `train/build_dataset.py` (EIA-930 hourly fuel mix x `EF` = IPCC lifecycle medians: coal 820, gas 490, oil 650, other 500, nuclear 12, hydro 24, solar 48, wind 11, geo 38 g/kWh) | computed 2026-10-27 | n/a | **Derived** here: annual means and month-hour means |

NREL was renamed the National Laboratory of the Rockies (NLR), and the old `*.nrel.gov` hostnames no longer
resolve. The live hosts are `www.nlr.gov`, `data.nlr.gov` and `scenarioviewer.nlr.gov`.

## Region mapping (derived; this is the judgment call)

| Terra | AVERT region | eGRID | Cambium GEA |
|---|---|---|---|
| PACE (PacifiCorp East) | **Northwest**. AVERT assigns each BA to one region, and its Table 6 puts Utah at 97% Northwest / 3% Rocky Mountains and Wyoming at 62% / 38%. PACE also serves WY and ID, so the Rocky Mountains rate is included as a secondary row. | BA `PACE`; subregion NWPP | **NorthernGrid_South**: all 29 Utah counties in the workbook's County Mapping. PACE's ID and WY load falls in NorthernGrid_East and WestConnect_North, which were not used. |
| BPAT (Bonneville) | **Northwest** (the same AVERT region as PACE) | BA `BPAT`; NWPP | **NorthernGrid_West** (all OR and WA counties) |
| CISO (CAISO) | California | BA `CISO`; CAMX | CAISO |
| ERCO (ERCOT) | Texas | BA `ERCO`; ERCT | ERCOT |

## Key numbers (kg CO2/MWh = g/kWh)

| Region | Terra avg 2025 (lifecycle, derived) | eGRID 2023 BA avg | eGRID 2023 BA non-baseload | AVERT 2023 marginal (uniform EE) | Cambium 2025 SRMER (Mid-case) | Cambium 2025 LRMER (Mid-case) |
|---|---|---|---|---|---|---|
| PACE | 471 | 640 | 949 | 728 (Rocky Mtns 835) | 603 | 459 |
| BPAT | 65 | 96 | 514 | 728 | 462 | 288 |
| CISO | 246 | 168 | 398 | 470 | 517 | 228 |
| ERCO | 316 | 333 | 565 | 587 | 605 | 409 |

In native units, AVERT 2023 uniform EE is 1,604 / 1,604 / 1,037 / 1,294 lb/MWh, and eGRID BA averages are
1,410 / 212.5 / 369.3 / 734.0 lb/MWh (PACE / BPAT / CISO / ERCO).

Scopes differ, and the CSV labels each one. AVERT, eGRID and Cambium `_c` are direct combustion CO2. Terra uses
lifecycle CO2e (IPCC). Cambium also gives combustion+precombustion CO2e, the closest to Terra's basis: SRMER 755 / 574 /
686 / 758 and LRMER 582 / 376 / 311 / 547 (PACE / BPAT / CISO / ERCO). Cambium is per MWh of end-use demand
(distribution losses included), and so is AVERT uniform EE (T&D losses included). eGRID is per MWh generated.

Hourly (Cambium Mid-case 2025 SRMER, combustion CO2, month-hour range): PACE 349–902, BPAT 9–789, CISO 349–717,
ERCO 450–777 kg/MWh. Terra's own 2025 month-hour average ranges are PACE 253–620, BPAT 34–100, CISO 142–357 and
ERCO 177–426.

## Findings worth knowing

1. **Averages exaggerate the spread between regions.** On Terra's average, BPAT is 7x cleaner than PACE (65 vs 471).
   At the margin the gap shrinks to 1.3x (Cambium SRMER 462 vs 603) or disappears (AVERT puts both in "Northwest" at 728).
   BPAT's average is low because of hydro, but hydro is energy-limited and almost never the marginal unit. A new MW of
   load in BPAT is met by gas and coal in the Northwest market, not by more dam water.
2. **The rankings change.** Terra's average ranks BPAT < CISO < ERCO < PACE. AVERT's marginal ranking is
   CISO < ERCO < BPAT = PACE. Cambium SRMER ranks BPAT < CISO < PACE ≈ ERCO, and LRMER ranks CISO < BPAT < ERCO < PACE.
   The only claim every source supports is that **PACE is the worst place to add load**.
3. **Terra understates PACE even as an average.** For 2023, Terra computes 514 g/kWh for PACE, while eGRID's PACE BA
   rate is 1,410 lb/MWh (640 kg/MWh, combustion only). The IPCC lifecycle median for coal (820 g/kWh) is below the
   actual US coal fleet's combustion rate (eGRID PACE coal 2,399 lb/MWh, about 1,088 kg/MWh). On gas the IPCC factor
   (490) sits above eGRID's fleet rate (912 lb/MWh, about 414 kg/MWh) because it includes upstream emissions. That is
   why CISO comes out higher in Terra (246) than in eGRID (168). This is a finding, not a fix: `train/` is owned by
   another session.
4. **Time of day matters less at the margin.** Terra's average for CISO drops from about 280 at night to about 190 at
   midday (solar). Cambium's modeled SRMER for CISO stays at roughly 490–545 through the day, because gas is on the
   margin in most hours. That weakens the "wait for midday solar" story for CISO. The one strong time signal in
   Cambium is **BPAT in May daytime** (spring runoff), where SRMER drops to 9–27 kg/MWh. Load there soaks up
   surplus hydro, which is the real version of the hydro story.
5. **Caveats.**
   - Cambium is a model (ReEDS + PLEXOS, weather year 2012). The workbook itself says it is "not recommended to use
     Cambium data for estimating current conditions or historical accounting" for near-term questions.
   - AVERT is empirical (2023 CEMS) and models a 0.5% load displacement. EPA says not to use it more than 5 years out
     or for corporate GHG accounting.
   - eGRID non-baseload is a proxy, not a true marginal rate.
   - Hourly AVERT would require running the AVERT Excel tool (macros) or the AVERT Web Edition, which was not done. Its
     published rates are annual only.

## Key-gated live marginal sources (not signed up)

- **WattTime** (https://watttime.org/docs-dev/data-plans/, checked 2026-10-27). The free Basic plan gives "All signals
  & endpoints for one region: CAISO_NORTH" plus a CO2 *percentile* (relative 0–100 index) for all regions, a 72 h
  forecast and history. Absolute MOER (`co2_moer`, lbs CO2/MWh) for PACE, BPAT and ERCOT needs a paid plan. That
  makes it a live 5-minute marginal signal for CISO only, plus a relative signal everywhere. Which plans include what
  was not fully verified, because the plan table renders poorly.
- **Electricity Maps** (https://www.electricitymaps.com/pricing, checked 2026-10-27). The page shows a 14-day API trial
  with no payment information, not a permanent free tier. Its signal is carbon intensity in gCO2eq/kWh with forecasts
  and 3 months of trailing history. The page does not mention marginal emissions, so treat it as an *average* source.
  Not verified further.
- To use either one, Granite would need to create the account himself and store the key in
  `~/Documents/Credentials/` (e.g. `~/Documents/Credentials/watttime.env` with `WATTTIME_USER`/`WATTTIME_PASSWORD`) or
  in the Vaultwarden vault. Nothing was signed up here.

## What this replaces

Terra's carbon today is the **average** lifecycle intensity of each grid's in-region generation (EIA-930 fuel mix x
IPCC medians): PACE 471, BPAT 65, CISO 246 and ERCO 316 g/kWh (2025). Marginal factors from public sources are much
higher and much closer together:
- **PACE**: 603 (Cambium SRMER 2025) / 728 (AVERT 2023) / 949 (eGRID non-baseload). PACE stays the dirtiest by every
  measure, and even its average is too low.
- **BPAT**: 462 / 728 / 514 against an average of 65. This is the biggest change: hydro sets the average, but gas and
  coal set the margin.
- **CISO**: 517 / 470 / 398 against an average of 246. Gas is on the margin almost all day.
- **ERCO**: 605 / 587 / 565 against an average of 316. All three marginal sources agree closely.

Routing on averages overstates the PACE→BPAT saving. The average gap is 406 g/kWh, against 141 for Cambium SRMER
(about 2.9x smaller), 171 for LRMER, and 0 for AVERT, which uses one Northwest rate for both. The direction (move
*out of* PACE) holds on every source. Swapping in marginal factors means adding a per-region table (annual or Cambium month-hour) in
place of `gco2` in `decide.py`'s cost. Both tables are in this folder.

**"Carbon?" (one line for the judge):** "Today Terra scores carbon with each grid's average mix, which is honest but
not marginal. We collected EPA AVERT, eGRID and NREL Cambium marginal rates for all four grids, and they show the
margin is about 450–750 g/kWh in all four grids. The real carbon win is moving load out of Utah, not chasing
Bonneville's hydro average, and the marginal tables are ready to swap in."
