# NASA POWER (named on the Torus slide, Option 2)

- Source: NASA POWER hourly API, community RE, https://power.larc.nasa.gov/api/temporal/hourly/point
  (keyless; NASA data, free to use with credit). Retrieved 2026-10-27.
- Sites: SLC (40.76, -111.89), Milford (38.40, -113.01), Cedar City (37.68, -113.06), Delta (39.35, -112.58):
  the same Utah solar sites `train/solar.py` uses.
- Fields: ALLSKY_SFC_SW_DWN (sunlight reaching the ground, Wh/m² per hour), CLRSKY_SFC_SW_DWN (the same under clear
  sky), T2M (°C), WS10M (m/s). Hourly, UTC, 2025-01-01 to 2026-10-26.
- `hourly.csv`: 63,744 rows (4 sites). Blank = -999 in the source (not yet processed).
- **Lag:** satellite solar is final only through **2026-07-31**. It can't cover the replay week (Oct 19–25) or
  Wednesday. Good for: a satellite "what actually happened" check on the solar forecaster over Jan–Jul 2026, and
  clear-sky vs all-sky (how much clouds cost each site).
- Reported, not derived. `to_csv.py` only reshapes the JSON.
