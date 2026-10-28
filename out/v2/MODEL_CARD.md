# Model card: Terra v2

The model Terra ships. Files: `mycelium.onnx` (for the router), `mycelium.pt` (PyTorch weights),
`metrics.json` (every score below), `reliability.json` (calibration curve). The file names keep the build's
working name, Mycelium.

## What it does

For one power region at one hour, it forecasts each of the next 24 hours:

- **P(rush hour):** the chance demand is at or above 95% of that day's high
- **Demand share:** demand as a share of the day's high
- **Carbon:** grams of CO2 per kWh, from the region's fuel mix

The router (`router/src/decide.ts`) uses the rush-hour chances to pick where and when each AI job runs.

## Design

| | |
|---|---|
| Type | MLP with a region embedding and three output heads, built in `train/train.py` (`MODEL=mlp`) |
| Parameters | 561,016 |
| Inputs | 492 numbers per region per hour, as five ONNX inputs (`past`, `fut`, `cal`, `region`, `mkt`): 48 h of grid history, 24 h of the utility's and the weather's forecasts, sun position and calendar, the region, hub power and gas prices |
| Calibration | temperature scaling on the validation set (T = 1.214) |
| Loss | binary cross-entropy on rush hour + 4 × MSE on demand share + 4 × MSE on carbon |

## Data

Public data only: 32.6 million values from 50 US regions, January 2022 to October 2026 (EIA-930 grid data, archived
weather forecasts from Open-Meteo, EIA hub and Henry Hub prices, US holidays, plus computed sun position). Details
and counts are in `data/train/checks_v2.json`.

Split by time, so the test set is entirely in the future of the training data:

| Split | Dates | Examples |
|---|---|---:|
| Train | before July 2025 | 754,786 |
| Validation | July to December 2025 | 109,476 |
| Test | January 2026 onward | 171,836 |

## Training cost

80 seconds on one RTX 4080 Super, 5.6 Wh (average 251 W, measured from the GPU while training).

## Results (test set, 2026)

| | Terra | Utility's day-ahead forecast, calibrated |
|---|---:|---:|
| Rush-hour Brier score, all 50 regions (lower is better) | **0.050** | 0.071 |
| Rush-hour accuracy | **93.0%** | 90.9% (uncalibrated rule) |
| Utah (PACE): rush hours caught a day ahead | **80.3%** | 68.7% |
| Utah (PACE): Brier score | **0.102** | 0.134 |

Other heads: carbon error 27 g CO2/kWh (mean absolute), demand-share error 2.8 points.

**Routing** (1,162 held-out decisions; a 4-hour job that can wait up to 16 hours): rush hours run into drop from
1.14 (start now in Utah) to 0.04 with Terra.

## Energy per forecast

On one MacBook CPU core: 305,389 forecasts a second, 0.000056 J per forecast counting all chip power. A year of
forecasts for all 50 regions takes about 20 J. The 4.8M-parameter transformer (`out/v3_candidate/`) was about 2%
better and used about 590× the energy per forecast, so it isn't shipped.

## Limits

- **It doesn't win everywhere.** Its Brier score beats the utility's in every region but one (SRP, Arizona, about
  even), but it catches fewer rush hours than the utility's forecast in 7 of 50 regions, including the Pacific
  Northwest (88.0% vs 88.6%).
- **Homestead, Florida (HST) isn't scored:** EIA has no day-ahead forecast there to compare with.
- **"Rush hour" is a stand-in.** It means demand at or above 95% of the day's high. Utilities' real demand-response
  calls aren't scheduled that way; Rocky Mountain Power's calls are 15–60 minutes, a few hours a year.
- **Carbon is an average, not marginal.** It comes from the region's own fuel mix, not the plant that would
  actually ramp.
- **The test year is 2026 only.** A year with very different weather or a big new load could behave differently.
