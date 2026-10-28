"""Build marginal_by_region.csv and hourly_profile_month_hour.csv from the files in raw/.

Sources (all public, downloaded 2026-10-27, see SOURCES.md):
  raw/avert/avert_emission_rates_04-11-24_0.xlsx        EPA AVERT v4.3 avoided (marginal) rates, data years 2017-2023
  raw/egrid/egrid2023_data_rev2.xlsx                     EPA eGRID2023 rev2: BA23 and SRL23 sheets
  raw/cambium/sv/annual/Cambium24_allScenarios_annual_gea.csv          NREL/NLR Cambium 2024, all scenarios, annual
  raw/cambium/sv/monthhour/Cambium24_allScenarios_month-hour_gea.csv   same, 12 months x 24 hours
  raw/cambium/sv/historical/GEA_historical_emissions_intensities 3-17-25.csv
  ../../train/hourly_v2.parquet                          the project's own average gCO2/kWh (EIA-930 x IPCC lifecycle)

Run from anywhere:
  uv run --with pandas --with openpyxl --with pyarrow python -I data/collected/carbon/build_carbon_tables.py
Raw files are parsed as data only (openpyxl data_only/read_only, pandas CSV); nothing in raw/ is executed.
"""
from pathlib import Path

import openpyxl
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROJECT = HERE.parents[2]
LB = 0.45359237  # kg per lb

# Our four routing regions -> each source's region. PACE straddles: see SOURCES.md.
AVERT = {"PACE": "Northwest", "BPAT": "Northwest", "CISO": "California", "ERCO": "Texas"}
AVERT_ALT = {"PACE": "Rocky Mountains"}  # Wyoming share of PacifiCorp East (Utah 97% Northwest / 3% Rocky Mtns)
EGRID_SR = {"PACE": "NWPP", "BPAT": "NWPP", "CISO": "CAMX", "ERCO": "ERCT"}
GEA = {"PACE": "NorthernGrid_South", "BPAT": "NorthernGrid_West", "CISO": "CAISO", "ERCO": "ERCOT"}
STD_OFFSET = {"PACE": -7, "BPAT": -8, "CISO": -8, "ERCO": -6}  # local STANDARD time, to match Cambium

URL = {
    "AVERT": "https://www.epa.gov/system/files/documents/2024-04/avert_emission_rates_04-11-24_0.xlsx",
    "eGRID": "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx",
    "Cambium": "https://scenarioviewer.nlr.gov/ (project 'Cambium 2024', GEA Regions Annual / Month-Hour files)",
    "Cambium-hist": "https://scenarioviewer.nlr.gov/ (project 'Cambium 2024', GEA Historical Intensities)",
    "project": "data/train/hourly_v2.parquet (train/build_dataset.py: EIA-930 fuel mix x IPCC lifecycle medians)",
}

rows = []


def add(region, source, source_region, metric, scope, value, units, year, granularity, derived, note=""):
    kg = value * LB if units.startswith("lb") else value
    rows.append(dict(region=region, source=source, source_region=source_region, metric=metric, emissions_scope=scope,
                     value=round(value, 2), units=units, kg_per_MWh=round(kg, 1), year=year, granularity=granularity,
                     reported_or_derived=derived, notes=note, source_url=URL[source if source in URL else "project"]))


# ---------- AVERT: regional avoided CO2 rates, every year sheet ----------
wb = openpyxl.load_workbook(RAW / "avert" / "avert_emission_rates_04-11-24_0.xlsx", read_only=True, data_only=True)
for year in ("2023", "2022", "2021"):
    grid = [list(r) for r in wb[year].iter_rows(values_only=True)]
    hdr_i = next(i for i, r in enumerate(grid) if r[0] and str(r[0]).startswith("Avoided CO2 Rate (lb/MWh)"))
    hdr = grid[hdr_i + 1]
    cols = {str(h).strip(): j for j, h in enumerate(hdr[:10]) if h}
    table = {r[0]: r for r in grid[hdr_i + 2: hdr_i + 20] if isinstance(r[0], str)}
    for reg, avert_reg in list(AVERT.items()) + list(AVERT_ALT.items()):
        r = table[avert_reg]
        alt = reg in AVERT_ALT and avert_reg == AVERT_ALT[reg]
        for metric, col in (("marginal (AVERT uniform EE: flat load, T&D losses included)", "Uniform EE"),
                            ("marginal (AVERT portfolio EE)", "Portfolio EE")):
            if year != "2023" and col == "Portfolio EE":
                continue
            add(reg, "AVERT", avert_reg, metric, "CO2, direct combustion, fossil EGUs (CEMS)", float(r[cols[col]]),
                "lb CO2/MWh", int(year), "annual average of hourly marginal", "reported (region mapping derived)",
                ("secondary region: Wyoming part of PACE" if alt else "") + ("; " if alt else "")
                + "0.5% load displacement; EPA: not for >5 yr ahead; not for GHG accounting")

# ---------- eGRID2023: BA and subregion ----------
wb = openpyxl.load_workbook(RAW / "egrid" / "egrid2023_data_rev2.xlsx", read_only=True, data_only=True)
EG_METRICS = [  # (suffix, metric, scope)
    ("CO2RTA", "average (total output, all generation)", "CO2, direct combustion"),
    ("C2ERTA", "average (total output, all generation)", "CO2e, direct combustion"),
    ("NBCO2", "non-baseload output rate (eGRID marginal proxy)", "CO2, direct combustion"),
    ("CO2CRT", "average of combustion generation only (fossil+biomass)", "CO2, direct combustion"),
]
for sheet, prefix, key, mapping, level in (("BA23", "BA", "BACODE", {r: r for r in AVERT}, "balancing authority"),
                                           ("SRL23", "SR", "SUBRGN", EGRID_SR, "eGRID subregion")):
    grid = list(wb[sheet].iter_rows(values_only=True))
    codes = grid[1]
    idx = {c: i for i, c in enumerate(codes) if c}
    by = {r[idx[key]]: r for r in grid[2:]}
    for reg, code in mapping.items():
        r = by[code]
        for suf, metric, scope in EG_METRICS:
            add(reg, "eGRID", f"{code} ({level})", metric, scope, float(r[idx[prefix + suf]]),
                "lb/MWh", 2023, "annual", "reported (subregion mapping derived)" if level != "balancing authority" else "reported",
                "generation-based (in-region plants, no imports)")

# ---------- Cambium 2024: annual, MidCase ----------
ann = pd.read_csv(RAW / "cambium" / "sv" / "annual" / "Cambium24_allScenarios_annual_gea.csv", skiprows=5)
mid = ann[(ann["scenario"] == "MidCase") & (ann["t"].isin([2025, 2030]))]
CAM_METRICS = [
    ("srmer_co2_c", "marginal short-run (SRMER)", "CO2, direct combustion"),
    ("lrmer_co2_c", "marginal long-run (LRMER)", "CO2, direct combustion"),
    ("srmer_co2e", "marginal short-run (SRMER)", "CO2e, combustion + precombustion (lifecycle fuel)"),
    ("lrmer_co2e", "marginal long-run (LRMER)", "CO2e, combustion + precombustion (lifecycle fuel)"),
    ("aer_load_co2_c", "average (consumption-based, incl. imports)", "CO2, direct combustion"),
    ("aer_load_co2e", "average (consumption-based, incl. imports)", "CO2e, combustion + precombustion (lifecycle fuel)"),
]
for reg, gea in GEA.items():
    for _, r in mid[mid["gea"] == gea].iterrows():
        for col, metric, scope in CAM_METRICS:
            add(reg, "Cambium", gea, metric, scope, float(r[col]), "kg/MWh", int(r["t"]),
                "annual (modeled, weather year 2012)", "reported (GEA mapping derived)",
                "Mid-case scenario; kg per MWh of end-use demand (distribution losses included); modeled projection, not observed")

# ---------- Cambium historical (eGRID-derived) in-region intensity ----------
hist = pd.read_csv(next((RAW / "cambium" / "sv" / "historical").glob("*.csv")), skiprows=3)
for reg, gea in GEA.items():
    h = hist[(hist["gea"] == gea) & (hist["year"] == 2023)].iloc[0]
    add(reg, "Cambium-hist", gea, "average (in-region generation, observed)", "CO2, direct combustion",
        float(h["co2_kg_per_mwh"]), "kg/MWh", 2023, "annual", "reported (GEA mapping derived)", "NLR aggregation of eGRID plant data")

# ---------- the project's own average (what Terra uses today) ----------
h = pd.read_parquet(PROJECT / "data" / "train" / "hourly_v2.parquet", columns=["utc", "ba", "gco2"])
h = h[h["ba"].isin(AVERT)].copy()
h["utc"] = pd.to_datetime(h["utc"], utc=True)
h["year"] = h["utc"].dt.year
for (reg, year), g in h[h["year"].isin([2023, 2024, 2025])].groupby(["ba", "year"]):
    add(reg, "project", "EIA-930 " + reg, "average (in-region generation mix)",
        "CO2e lifecycle (IPCC AR5 medians per fuel), as used by Terra", float(g["gco2"].mean()), "kg/MWh", int(year),
        "annual mean of hourly", "derived (computed here from Terra's training table)", "g/kWh = kg/MWh; generation-based, no imports")

out = pd.DataFrame(rows)
out.to_csv(HERE / "marginal_by_region.csv", index=False)
print(f"marginal_by_region.csv: {len(out)} rows")

# ---------- month x hour profiles: Cambium MidCase 2025 + project 2025 ----------
mh = pd.read_csv(RAW / "cambium" / "sv" / "monthhour" / "Cambium24_allScenarios_month-hour_gea.csv", skiprows=5,
                 usecols=["scenario", "gea", "t", "month", "hour", "srmer_co2_c", "lrmer_co2_c", "srmer_co2e", "lrmer_co2e",
                          "aer_load_co2_c", "aer_load_co2e"])
mh = mh[(mh["scenario"] == "MidCase") & (mh["t"] == 2025) & (mh["gea"].isin(GEA.values()))]
inv = {v: k for k, v in GEA.items()}
mh = mh.assign(region=mh["gea"].map(inv)).rename(columns={"t": "year"})
prof = mh[["region", "gea", "year", "month", "hour", "srmer_co2_c", "lrmer_co2_c", "srmer_co2e", "lrmer_co2e",
           "aer_load_co2_c", "aer_load_co2e"]].copy()

h25 = h[h["year"] == 2025].copy()
h25["local_std"] = h25.apply(lambda r: r["utc"] + pd.Timedelta(hours=STD_OFFSET[r["ba"]]), axis=1)
h25["month"], h25["hour"] = h25["local_std"].dt.month, h25["local_std"].dt.hour
ours = h25.groupby(["ba", "month", "hour"])["gco2"].mean().round(1).rename("terra_avg_lifecycle_2025").reset_index()
prof = prof.merge(ours.rename(columns={"ba": "region"}), on=["region", "month", "hour"], how="left")
prof = prof.sort_values(["region", "month", "hour"])
prof.to_csv(HERE / "hourly_profile_month_hour.csv", index=False)
print(f"hourly_profile_month_hour.csv: {len(prof)} rows")

# console summary for SOURCES.md
pick = out[(out["metric"].str.startswith(("marginal (AVERT uniform", "marginal short-run", "marginal long-run",
                                          "non-baseload", "average (total", "average (in-region generation mix)")))
           & (out["year"].isin([2023, 2025])) & (out["emissions_scope"].str.startswith(("CO2,", "CO2e lifecycle")))
           & (out["source_region"] != "Rocky Mountains") & ~out["source_region"].str.contains("subregion")]
print(pick.pivot_table(index=["source", "metric", "year"], columns="region", values="kg_per_MWh").round(0).to_string())
print(prof.groupby("region")[["srmer_co2_c", "lrmer_co2_c", "terra_avg_lifecycle_2025"]].agg(["min", "max"]).round(0).to_string())
