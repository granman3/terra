"""Utah's planned power plants, from EIA-860M (the deck's "where next" slide).

Reads the monthly generator inventory (data/raw/eia860m/<month>_generator<year>.xlsx, from
eia.gov/electricity/data/eia860m/) and writes out/expansion/utah.json: every planned Utah generator
with its county, technology, size, year, status and balancing authority, the operating fleet for
context, and the totals the slide quotes.
Run: uv run --with pandas --with openpyxl python train/expansion.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = sorted((ROOT / "data" / "raw" / "eia860m").glob("*_generator*.xlsx"))[-1]
OUT = ROOT / "out" / "expansion"
CAP = "Nameplate Capacity (MW)"
KIND = {"Solar Photovoltaic": "solar", "Batteries": "battery", "Hydroelectric Pumped Storage": "pumped hydro",
        "Geothermal": "geothermal", "Onshore Wind Turbine": "wind"}
# the Wasatch Front, where Utah's load and its data centers are
FRONT = {"Salt Lake", "Utah", "Davis", "Weber"}


def sheet(name):
    d = pd.read_excel(SRC, name, header=2)
    return d[d["Plant State"] == "UT"].copy()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan, op = sheet("Planned"), sheet("Operating")
    plan["kind"] = plan["Technology"].map(KIND).fillna("gas/other")
    total = float(plan[CAP].sum())
    gen = plan[plan["kind"].isin(["solar", "geothermal", "wind"])]  # makes energy (storage only moves it)
    by_ba = plan.groupby("Balancing Authority Code")[CAP].sum()
    plants = (plan.groupby(["Plant Name", "County", "kind", "Balancing Authority Code", "Status", "Latitude", "Longitude"], as_index=False)
              .agg(mw=(CAP, "sum"), year=("Planned Operation Year", "min")))
    out = {
        "source": f"EIA-860M, {SRC.stem.replace('_generator', ' ')} ({SRC.name})",
        "planned_mw": round(total),
        "planned_by_kind_mw": plan.groupby("kind")[CAP].sum().round().astype(int).sort_values(ascending=False).to_dict(),
        "planned_by_county_mw": plan.groupby("County")[CAP].sum().round().astype(int).sort_values(ascending=False).to_dict(),
        "planned_by_ba_mw": by_ba.round().astype(int).to_dict(),
        "ldwp_share_pct": round(float(by_ba.get("LDWP", 0) / total * 100)),
        "planned_generation_mw": round(float(gen[CAP].sum())),
        "planned_generation_ldwp_pct": round(float(gen.loc[gen["Balancing Authority Code"] == "LDWP", CAP].sum() / gen[CAP].sum() * 100)),
        "planned_on_wasatch_front_mw": round(float(plan.loc[plan["County"].isin(FRONT), CAP].sum())),
        "operating_solar_mw": round(float(op.loc[op["Technology"] == "Solar Photovoltaic", CAP].sum())),
        "operating_coal_mw": round(float(op.loc[op["Technology"] == "Conventional Steam Coal", CAP].sum())),
        "plants": plants.sort_values("mw", ascending=False).round({"mw": 1, "Latitude": 4, "Longitude": 4}).rename(columns={
            "Plant Name": "name", "County": "county", "Balancing Authority Code": "ba", "Status": "status",
            "Latitude": "lat", "Longitude": "lon"}).to_dict("records"),
        "operating_solar": op.loc[op["Technology"] == "Solar Photovoltaic"].groupby(["Plant Name", "Latitude", "Longitude"], as_index=False)[CAP]
                             .sum().rename(columns={"Plant Name": "name", "Latitude": "lat", "Longitude": "lon", CAP: "mw"}).round(4).to_dict("records"),
    }
    (OUT / "utah.json").write_text(json.dumps(out, indent=1, default=int))
    (ROOT / "deck" / "utah.json").write_text(json.dumps(out, default=int))  # the slide's map (the router only serves deck/)
    print(json.dumps({k: v for k, v in out.items() if k not in ("plants", "operating_solar")}, indent=1, default=int))


if __name__ == "__main__":
    main()
