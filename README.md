# Terra

A small custom AI model that moves AI work off the grid's rush hours.

Built by Granite Tait for the Hard Tech Hackathon (Torus bounty, Salt Lake City, Oct 2026).

- **Live demo (phone):** https://terra.granitetait.com
- **Live map + deck:** https://terra-live.granitetait.com (deck at [/deck/](https://terra-live.granitetait.com/deck/), arrow keys, `f` for full screen)
- **Slides (PDF):** [deck/Terra-slides.pdf](deck/Terra-slides.pdf)

## The idea

Power plants can't move. AI work can. Utah builds plants for its worst few hours: the top 10% of its grid
(972 MW) was needed for only 153 hours in 2025. Most AI work (training, batch jobs) can wait a few hours or run
in another region. Terra forecasts each grid's rush hours a day ahead and decides where and when every AI job
should run, and how hard. For Torus, that makes the load itself a third asset next to Spin (milliseconds) and
Pulse (hours), with nothing new to build.

## What's in it

| Path | What |
|---|---|
| `train/` | Data pipeline and training (Python, PyTorch). `build_dataset.py` pulls 50 US grids × 6 kinds of public data into 1.04M examples; `train.py` trains the 561K-parameter model and exports ONNX; `train_big.py` fine-tunes a 4B model on the same task for comparison; `solar.py`, `surge.py`, `math_layer.py`, `conformal.py` are the supporting models |
| `out/v2/` | **The shipped model**: `mycelium.onnx` (561K parameters, 2.2 MB) and its test metrics |
| `out/v3_candidate/` | A 4.8M-parameter transformer: about 2% better, about 590× more energy per forecast, so not shipped |
| `router/` | TypeScript server: loads the ONNX model, routes jobs between four regions (`decide.ts`), tracks site room (`capacity.ts`), staggers job starts (`surge.ts`), serves the live map and deck |
| `demo/` | Live map (`live.html`) and the GPU demand-response agent (`dr_agent.py`, RTX 4080 clock lock) |
| `web/` | The phone demo: a replay of a held-out week, routing in the browser with the same rule as `decide.ts` |
| `deck/` | The slides (`index.html`), the 3-minute script, and `numbers.json` (every number on the slides, rebuilt by `make_numbers.py`) |
| `data/train/` | The held-out replay week and solar replay the demos run on |
| `data/collected/` | Real-data sweep: `INDEX.md` maps each dataset to the number it backs (raw downloads not included; scripts fetch them) |

## Numbers

- **Data:** 33 million public data points, hourly since January 2022, 50 US grids (EIA-930, EIA-860M, archived
  weather forecasts, sun position, holidays, hub and gas prices). 492 inputs per decision.
- **Model:** 561K parameters, trained at home on one RTX 4080. Peak-hour forecast error (Brier) 29% lower than a
  calibrated EIA day-ahead baseline. Utah: 80% of rush hours caught vs 69%.
- **Routing:** a 4-hour job that can wait runs into 0.04 rush hours, vs 1.14 if started now in Utah. In 85% of
  Utah's 2026 rush hours, California, the Pacific Northwest or Texas had room to spare.
- **Right-sized:** about 690,000× less energy per decision than a 4B-parameter model, measured on the same MacBook.
- **Demand response:** an RTX 4080 clock lock takes it from 276 W to 196 W (−29%) for 6% less decode speed.
- **Money:** Rocky Mountain Power's Wattsmart Business pays $100/kW a year for peak cuts, so 100 MW of AI work that
  can wait is worth about $10 million a year.

## What's real and what's simulated

Real: EIA grid data, archived weather forecasts, Utah prices and tariffs, the GPU's measured power, the model and
its test scores (held-out 2026 data). Simulated and labeled as such: the AI sites, their size and in-house load,
the 1 MW site in the surge number, and the utility's demand-response call in the replay week (Tue Oct 20,
noon–2 PM, that week's highest demand). "Rush hour" means demand at or above 95% of that day's high.

## Run it

```bash
# Router, live map and deck at http://localhost:8787 (/deck/ for the slides). Node 24+.
npm --prefix router install
npm --prefix router start

# Phone demo: any static server
python3 -m http.server -d web 8798

# Rebuild the phone demo's data after a retrain or replay change
node router/src/export-web.ts
```

Retraining needs the full dataset (`data/train/dataset_v2.npz`, 2.5 GB, not in the repo): run
`train/fetch_weather.py` and `train/build_dataset.py` to rebuild it, then
`PYTHONPATH=train python train/train.py data/train/dataset_v2.npz` with `OUT=out/v2`. The 4B fine-tune's weights
(8 GB) aren't in the repo either; `train/train_big.py` rebuilds them from Qwen3-4B.
