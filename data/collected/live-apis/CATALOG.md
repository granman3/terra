# Live data API catalog (tested 2026-10-27, ~22:57–23:10 UTC)

Every keyless row below was called for real from this Mac at the time shown; "latest" is the newest timestamp
in the response at that moment. All times converted to UTC unless noted. Samples in `samples/`, one fetch script
per source in `scripts/` (stdlib Python, run with `python3 -I scripts/<name>.py`; each prints the latest row).

## Keyless sources (work now)

| Source | What it gives | Latest observed (fetched ~23:00 UTC) | Key | Limits | Working curl | Sample / script |
|---|---|---|---|---|---|---|
| **EIA-930 grid monitor JSON** (`www.eia.gov/electricity/930-api/…`) | Hourly demand (D), EIA day-ahead demand forecast (DF), net gen (NG), interchange (TI) for any of the 80 respondents (all 51 Terra BAs), UTC **hour ending** | D for PACE/CISO/BPAT/ERCO: **22:00 UTC** hour ending (lag < 1 h). DF runs to 10-28 00:00–07:00 UTC. NG/TI lag ~17 h (through 04–06 UTC) | n | Undocumented internal endpoint behind the Grid Monitor (could change); no stated limit, keep it to a few calls/hour | `curl -g "https://www.eia.gov/electricity/930-api/region_data/series_data?type[0]=D&type[1]=DF&respondent[0]=PACE&respondent[1]=CISO&respondent[2]=BPAT&respondent[3]=ERCO&start=10262026%2000:00:00&end=10282026%2000:00:00&frequency=hourly&timezone=Eastern&limit=10000&offset=0"` (`-g` is required for the `[0]` brackets; start/end are `MMDDYYYY HH:MM:SS` and are read as UTC) | `eia930_gridmonitor_4ba.json`, `eia930_respondents.json` (BA list with lat/lon) / `eia930_gridmonitor.py`, `live_now.py` |
| **EIA-930 bulk 6-month CSV** (what `data/raw/eia930/` already holds) | Every column incl. generation by fuel (coal, gas, hydro, solar, wind…), all BAs, hourly | File Last-Modified **2026-10-27 14:42 UTC**; data through end of 10-26 local (~10-27 04:00–07:00 UTC). Refreshed ~daily | n | ~31 MB per half-year; server ignores Range requests (always sends the whole file) | `curl -sSI https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_2026_Jul_Dec.csv` (check Last-Modified before re-downloading) | `eia930_bulk_head_1500B.csv`, `eia930_bulk_tail_1500B.csv` |
| **CAISO OASIS** `PRC_INTVL_LMP` RTM | 5-min real-time LMP $/MWh (energy, congestion, loss, GHG parts) at PACE (`ELAP_PACE-APND`) and CAISO hubs (`TH_NP15_GEN-APND`, `TH_SP15_GEN-APND`) | **23:00 UTC** interval start (lag ~5 min). PACE was −$1.25/MWh | n | Throttles fast callers: ≥5–6 s between requests; ~10 days per request for 5-min data (as in `train/fetch_pace_lmp.py`) | `curl -o x.zip "https://oasis.caiso.com/oasisapi/SingleZip?resultformat=6&queryname=PRC_INTVL_LMP&version=3&market_run_id=RTM&node=ELAP_PACE-APND,TH_NP15_GEN-APND,TH_SP15_GEN-APND&startdatetime=20261027T21:00-0000&enddatetime=20261027T23:00-0000"` (zip with one CSV; price column `VALUE`, keep `LMP_TYPE==LMP`) | `oasis_rtm_lmp_pace.csv` / `caiso_oasis.py rtm` |
| **CAISO OASIS** `PRC_LMP` DAM | **Tomorrow's** hourly day-ahead LMP, same nodes | All 24 h of **2026-10-28** (to 10-29 06:00 UTC). PACE peak $59.25/MWh at 10-29 00:00 UTC (6 PM MDT) | n | as above | `…&queryname=PRC_LMP&version=12&market_run_id=DAM&node=ELAP_PACE-APND,TH_NP15_GEN-APND,TH_SP15_GEN-APND&startdatetime=20261028T07:00-0000&enddatetime=20261029T07:00-0000` (price column `MW`) | `oasis_dam_lmp_tomorrow.csv` / `caiso_oasis.py dam` |
| **CAISO OASIS** `SLD_FCST` DAM | **Tomorrow's** hourly load forecast by TAC area: `CA ISO-TAC`, **`PACE`**, **`BPAT`**, PACW and 30+ other WEIM areas | All 24 h of 10-28. Peaks: CAISO 27,270 MW, PACE 6,035 MW, BPAT 7,969 MW | n | as above | `…&queryname=SLD_FCST&version=1&market_run_id=DAM&startdatetime=20261028T07:00-0000&enddatetime=20261029T07:00-0000` (column `MW`, `TAC_AREA_NAME`) | `oasis_sld_fcst_dam.csv` / `caiso_oasis.py load` |
| **CAISO Today's Outlook** (`www.caiso.com/outlook/current/`) | 5-min CAISO demand (+DA/hour-ahead forecast), net demand, fuel mix (solar, wind, batteries, imports…), CO2 t/h; `stats.txt` (JSON) has today/tomorrow forecast peak, reserves | **15:55 PT = 22:55 UTC** (then 16:00 PT on re-run). Demand 22,307 MW | n | None stated | `curl -O https://www.caiso.com/outlook/current/demand.csv` (also `fuelsource.csv`, `co2.csv`, `netdemand.csv`, `renewables.csv`, `stats.txt`; past days at `outlook/history/YYYYMMDD/demand.csv`) | `caiso_outlook_*.csv`, `caiso_outlook_stats.json` / `caiso_outlook.py` |
| **ERCOT dashboards JSON** (`www.ercot.com/api/1/services/read/dashboards/`) | `supply-demand` (5-min demand + capacity, hourly forecast demand 6 days out), `fuel-mix` (5-min by fuel), `system-wide-prices` (15-min RT hub/zone SPP + DAM), `combine-wind-solar` (actual + next-day forecast), `daily-prc` (reserves) | **17:55 CDT = 22:55 UTC** (23:00 UTC on re-run). Demand 60,348 MW; RT hub avg $39.14 (interval ending 17:45 CDT) | n | None stated; no User-Agent needed | `curl https://www.ercot.com/api/1/services/read/dashboards/supply-demand.json` (also `fuel-mix.json`, `system-wide-prices.json`, `combine-wind-solar.json`, `daily-prc.json`; `todays-outlook.json` is 403) | `ercot_*.json` / `ercot_dashboard.py` |
| **BPA BA 5-min** (`transmission.bpa.gov`) | BPAT load, VER (wind+solar), hydro, fossil/biomass, nuclear, 5-min, last 7 days (TSV, Pacific local time) | **15:55 PT = 22:55 UTC** (16:00 PT on re-run). Load 7,231 MW, hydro 4,159 MW | n | None stated | `curl https://transmission.bpa.gov/business/operations/wind/baltwg.txt` | `bpa_baltwg.txt` / `bpa_baltwg.py` |
| **Open-Meteo forecast** | Hourly forecast up to 16 days: temperature, cloud cover, shortwave/direct/diffuse radiation, wind 10/100 m, etc.; multiple points per call | Full 2026-10-28 for SLC, Milford, Cedar City, Delta | n | Free for non-commercial use (Open-Meteo terms list a daily/minute call cap; not re-checked today) | `curl "https://api.open-meteo.com/v1/forecast?latitude=40.76,38.40,37.68,39.35&longitude=-111.89,-113.01,-113.06,-112.58&hourly=temperature_2m,cloud_cover,shortwave_radiation,direct_radiation,diffuse_radiation,wind_speed_10m,wind_speed_100m&start_date=2026-10-28&end_date=2026-10-28&timezone=America%2FDenver&wind_speed_unit=ms"` | `openmeteo_tomorrow_raw.json`, `../tomorrow_weather.json` / `openmeteo_forecast.py` |
| **NWS api.weather.gov** | SLC gridpoint `SLC/100,175`: hourly forecast 156 h (°F, sky text, wind, dew point, RH, PoP); raw gridpoint has skyCover, temperature, windSpeed series | Forecast updated **18:31 UTC**, generated 22:08 UTC | n (User-Agent required) | Undisclosed, generous; must send a User-Agent naming the app + contact | `curl -A "terra-live-check/0.1 (contact)" https://api.weather.gov/gridpoints/SLC/100,175/forecast/hourly` | `nws_points_slc.json`, `nws_slc_hourly.json`, `nws_slc_gridpoint_raw.json` / `nws_hourly.py` |
| **gridstatus (open-source lib 0.37.0)** | Python wrappers over the same ISO public pages | `CAISO().get_load("latest")` → 15:55 PT keyless; `Ercot().get_load("today")`, `get_fuel_mix("today")` → 17:55 CDT keyless (`"latest"` not accepted for ERCOT). **No BPA class; PACE only via `gridstatus.EIA`, which refuses to start without `EIA_API_KEY`** | n for CAISO/ERCOT | inherits ISO limits | `uv run --with gridstatus python -I -c "import gridstatus; print(gridstatus.CAISO().get_load('latest').tail(1))"` | (not needed: the stdlib scripts cover the same pages without pandas) |

### Gotchas found while testing

- **Hour convention:** the EIA JSON labels are UTC **hour ending**, identical to the bulk CSV's "UTC Time at End of Hour"
  (checked: PACE 10-25 15:00/16:00/17:00 UTC = 5299/5552/5713 MW in both). Live D can feed the model with no shift.
- **CISO: EIA ≠ CAISO Outlook.** EIA-930 CISO demand runs ~5–8 GW above CAISO Outlook "Current demand" in daytime
  (10-27 hour ending 22 UTC: EIA 28,504 vs Outlook ~20,000; same gap on 10-25). EIA's own DF tracks the Outlook DA
  forecast. The model was trained on EIA, so feed it EIA; use the Outlook only for the 5-min display.
- **caiso.com and oasis.caiso.com fail Python's bundled CA store** (`CERTIFICATE_VERIFY_FAILED`) on this Mac's uv
  Python; curl works. The CAISO scripts shell out to curl, like `train/fetch_pace_lmp.py`. Don't disable verification.
- CAISO Outlook CSVs carry the whole day with blank future rows: take the last row with a value, not the last line.
- EIA grid-monitor fuel-mix route was not found (7 guessed paths, all 404). Fuel mix is in the bulk CSV (daily) or
  needs the EIA v2 key (`electricity/rto/fuel-type-data`).
- Open-Meteo radiation is the mean over the *preceding* hour, so "14:00" = 13:00–14:00. Training used
  `historical-forecast-api` with `timezone=GMT` and default units (°C, km/h). `tomorrow_weather.json` is the Denver day
  in m/s for display; for model input use `scripts/openmeteo_forecast.py --model` (same vars as `fetch_weather.py` +
  `fetch_solar_sites.py`, GMT, km/h) → `tomorrow_weather_model_units.json`. Model-compatible curl:
  `curl "https://api.open-meteo.com/v1/forecast?latitude=40.76&longitude=-111.89&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,cloud_cover,shortwave_radiation,wind_speed_100m,precipitation&start_date=2026-10-28&end_date=2026-10-28&timezone=GMT"`
- Wednesday is still daylight time everywhere (US DST ends Nov 1): MDT = UTC−6, PDT = UTC−7, CDT = UTC−5.
- **NREL is now NLR** (National Laboratory of the Rockies): `developer.nrel.gov` no longer resolves; the API lives at
  `developer.nlr.gov` (one PVWatts call with the public `DEMO_KEY` returned 200). NSRDB downloads need a real key + email.

## Key-gated (not signed up; nothing in `~/Documents/Credentials/` for any of these)

Each returned 401/403 without a key today. Note Granite's secrets now live in Vaultwarden, so the file is a local
copy for scripts.

| Service | What it adds over the keyless set | Free tier | Sign up | File to create |
|---|---|---|---|---|
| **EIA API v2** | Official, documented route for the same EIA-930 data, plus fuel mix (`rto/fuel-type-data`), interchange, subregions, retail prices; what `gridstatus.EIA` needs | Free; ≤5,000 rows per JSON response; keep < ~9,000 req/h and < 5 req/s ([EIA FAQ](https://www.eia.gov/opendata/faqs.php)) | https://www.eia.gov/opendata/register.php | `~/Documents/Credentials/eia-api-key.txt` |
| **ERCOT Public API** (`api.ercot.com/api/public-reports`) | Official ERCOT reports (load by weather zone, settlement point prices, forecasts, historical archives) | Free; needs subscription key **and** an ID token from an ERCOT B2C username/password; ~30 req/min, US IPs only ([ERCOT dev docs](https://developer.ercot.com/applications/pubapi/user-guide/registration-and-authentication)) | https://apiexplorer.ercot.com | `~/Documents/Credentials/ercot-api.env` (`ERCOT_SUBSCRIPTION_KEY`, `ERCOT_USERNAME`, `ERCOT_PASSWORD`) |
| **gridstatus.io hosted API** | One clean API over all ISOs incl. EIA, PACE-relevant WEIM data, history | Free: 500,000 rows/month ([gridstatusio README](https://github.com/gridstatus/gridstatusio)) | https://www.gridstatus.io/ (Settings → API) | `~/Documents/Credentials/gridstatus-api-key.txt` |
| **WattTime** | Marginal CO2 (MOER) signal + 72 h forecast | Free plan: all signals for **CAISO_NORTH only**; elsewhere paid ([WattTime plans](https://watttime.org/docs-dev/data-plans/)) | https://watttime.org (API: `POST /register`) | `~/Documents/Credentials/watttime.env` (`WATTTIME_USERNAME`, `WATTTIME_PASSWORD`) |
| **Electricity Maps** | Average carbon intensity + power breakdown per zone (e.g. `US-NW-PACE`, `US-CAL-CISO`, `US-NW-BPAT`, `US-TEX-ERCO`) | Free non-commercial tier, limited zones/datasets, no forecasts; ~50 req/h reported ([free tier](https://electricitymaps.com/free-tier)) | https://portal.electricitymaps.com | `~/Documents/Credentials/electricitymaps-api-key.txt` |
| **NLR (ex-NREL) developer API** | NSRDB solar irradiance history, PVWatts production estimates for the Utah solar sites | Free key (api.data.gov), ~1,000 req/h; `DEMO_KEY` works for a few calls (~30/h per IP) | https://developer.nlr.gov/signup/ | `~/Documents/Credentials/nlr-api-key.txt` |

None of these are needed for Wednesday: the keyless set covers demand, prices, and weather for all four regions.

## Best live feed for the Wednesday demo

**Current-hour demand for PACE, CISO, BPAT, ERCO: one keyless call.**
`python3 -I scripts/live_now.py` → EIA-930 grid-monitor JSON, hour-ending UTC, lag under an hour, same source and
convention the model trained on. At 22:57 UTC it returned the 22:00 hour for all four (PACE 6,157; CISO 28,504;
BPAT 7,294; ERCO 61,075 MW). It is the only keyless live demand for **PACE**. Poll at ~:10 past the hour.

For 5-minute "right now" numbers on screen (not model input): `caiso_outlook.py` (CISO), `ercot_dashboard.py` (ERCO),
`bpa_baltwg.py` (BPAT), all < 10 min behind. Utah's real-time price: `caiso_oasis.py rtm` (PACE LMP, ~5 min behind).

**Tomorrow, already published today:** `caiso_oasis.py dam load` gives Wednesday's (on Wednesday itself, run `caiso_oasis.py dam load 2026-10-28`) hourly day-ahead PACE/CAISO price
and the CAISO, PACE and BPAT load forecasts; `ercot_dashboard.py` gives ERCOT's hourly forecast. These are an
independent yardstick for Terra's own day-ahead forecast.

**Tomorrow's SLC + solar-site weather:** `python3 -I scripts/openmeteo_forecast.py 2026-10-28 --model` (model units,
GMT) or the display copy already in `tomorrow_weather.json` (Denver time, m/s). NWS (`nws_hourly.py`) is a second
opinion for SLC.

Fallback if `930-api` changes before 5 PM: the EIA bulk CSV is a day behind, so use the ISO-native feeds for CISO/ERCO/BPAT
and the OASIS `SLD_FCST` DAM PACE forecast for Utah (the RTM variant was not tested), or get the free EIA v2 key (minutes to issue).
