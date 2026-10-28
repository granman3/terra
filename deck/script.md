# Terra: 3-minute script (6 slides)

Story: problem → solution and why → what I built → proof → impact (the strip at the top right shows where you are).
About 430 spoken words: ~2:55 at 150 words a minute, ~3:10 with the demo pause, inside the 5-minute slot. Arrow key
= next slide. The cut slides (data sources, Utah problem, why, math, model-size chart) stay in the file as `data-cut`
backups.

Before you start: deck open full screen (`f`), router running (`npm --prefix router start`) or the hosted deck at
terra-live.granitetait.com/deck/.

**Mirrored projector setup (during the room check):**
- Plug in the charger, turn on Do Not Disturb, mirror the display, press `f` on the first slide.
- On the live slide, **P** skips the replay to two hours before Rocky Mountain Power's call (simulated: Tue Oct 20,
  noon–2 PM, the week's highest demand). Utah's rush hours start right there, so the savings ledger fills in.
  Arrow keys still move on.
- After any change to the replay or routing: `node deck/utah_savings.ts`, then
  `uv run --with pandas --with pyarrow python deck/make_numbers.py`, then reload.

---

**1 · Terra + QR code (0:00–0:10)**

Scan the code. That's Terra, live. I'm Granite. Terra is a custom AI model I built that moves AI work off the grid's
rush hours.

**2 · The problem (0:10–0:45)**

US power companies plan to spend 1.1 trillion dollars on the grid in just five years, the most ever, and data
centers are the main new driver of demand. Peak demand grows 224 gigawatts in ten years. Making data centers' power
takes 211 billion gallons of water a year, and the plants that cover the worst hours burn 40 percent more fuel. In
Utah, the top 10 percent of the grid was needed for just 153 hours last year: up to two billion dollars of plants for
2 percent of the year. It's hard because every load is treated as fixed.

**3 · The solution, and why (0:45–1:15)**

But power plants can't move. AI work can. Grids peak at different hours: Texas at 4, Utah at 5, California at 7. In
85 percent of Utah's rush hours, another grid had room. Why this solution? A new peaker costs up to two thousand
dollars a kilowatt. Batteries like Torus Pulse cover the load that can't move. Moving the load that can costs nothing
to build. Duke found 98 gigawatts of new data centers fit on today's grid if they flex half a percent of the time.

**4 · What I built (1:15–1:45)**

So I built a custom model for that one job: 33 million public data points, five training runs, three designs,
trained at home on my own graphics card. 561,000 parameters, made for one job. Underneath is one equation: for every job, pick the region and hour with the
least chance of rush hour. It makes 29 percent fewer mistakes than the utility's own forecast. And I tested going
bigger: a 4-billion-parameter model used 690,000 times the energy and barely beat the utility. We don't spend energy
to save energy.

**5 · Live demo (1:45–2:30)**

This is last week's real grid data, replayed at about a second an hour. Copper means rush hour is coming.
*(press **P**)* Tuesday, Utah's highest demand of the week. Every job that can wait leaves Utah for a grid with room.
Underneath is the proof, live: real power out of Utah's rush hour, at Utah's real prices. *(pause on the ledger)*

**6 · Impact (2:30–3:05)**

For Utah, that's 10 million dollars a year for every 100 megawatts of AI work that can wait. For every grid, it's how
98 gigawatts of new AI fits without new plants. Staggered starts shrink a site's power spike 50 times, so Spin has
less to catch. Torus has Spin for milliseconds and Pulse for hours. Terra moves the load itself. Next is a pilot with
one Utah AI site, plugged into Lasso. Let the grid's newest load be its most flexible one. Thank you!

---

## If they ask

- **"Where does the 153 hours come from?"** EIA-930, Rocky Mountain Power's grid (PACE), 2025: the year's peak was
  9,717 MW; demand was at or above 90% of it for 153 hours (1.7% of the year), and above 95% for 26.
- **"$0.7–1.9 billion?"** 972 MW × new simple-cycle gas plant costs of $728–1,969 per kW (GridLab/EFG, Sept 2025,
  utility filings for 2025–29 in-service dates). It's what building that top slice new would cost, not a bill Utah paid.
- **"Are the problem numbers Utah's?"** The 4.4% → 12% is DOE/Lawrence Berkeley Lab (Dec 2024), all US. The $16.4B is
  PJM's 2028/29 capacity auction (July 2026), the Mid-Atlantic grid: a preview of where Utah could go. The 10 GW is
  Creekstone's request, and Novva was told 2031 (Lehi Free Press, Feb 2026). Utah's consumer office says data centers
  haven't moved Utah rates yet; that's why the Utah number on the slide is our own measurement.
- **"How is the live dollar figure computed?"** `deck/utah_savings.ts` replays the same week, jobs and routing. For every
  hour Utah was really in rush hour, kW the jobs would have drawn in Utah minus what they drew with Terra. Energy is
  priced at that hour's PacifiCorp East real-time price (CAISO OASIS); capacity at $100 per kW a year (Wattsmart
  Business), one week's share of the average kW moved. One week, one simulated 1,000-chip site running the real job
  mix (Alibaba's 2026 trace: 42% of GPU-hours can wait): about 780 kWh and about $67. The $10 million is just 100,000 kW × $100.
- **"85% had room?"** EIA-930, 2026: of the 2,105 hours Utah was within 5% of its daily high, at least one of
  California, the Pacific NW or Texas was not.
- **"Less energy than one answer?"** A year of hourly forecasts for 50 regions is about 20 joules on this laptop; one
  answer from the 4-billion-parameter fine-tune on the same laptop is about 39 joules.
- **"Where did the math slide go?"** The routing equation is on slide 4; the full math slides (loss, Brier, the
  market and conformal slide) are cut backups, still in the file.

- **"So the problem is a bad forecast?"** No, that's a symptom. A better forecast tells you when the strain comes; it
  doesn't move anything. Today the grid answers every peak by building more plants, lines and batteries, because the
  demand sits still. Terra uses the forecast to move the demand.
- **"Is that 1.8 GW just Utah?"** It's Rocky Mountain Power's grid (PACE), which is Utah plus parts of Wyoming and
  Idaho. On the median full day of 2026 (298 days), demand peaked about 1.8 GW above its low: about 5.2 GW at night,
  7.2 GW at the top, on average.
- **"How much better is the forecast overall?"** 29% fewer prediction mistakes than the official forecast (Brier score)
  across all 50 regions, on 2026 data it never saw. A full year of forecasts for every region takes about 20 joules
  on this laptop.

- **"Why such a small model? Wouldn't bigger be better?"** I tested that. A transformer 8× bigger (4.8 million parameters)
  was only about 2% more accurate, and used about 590 times the energy per forecast. A 4-billion-parameter AI model
  fine-tuned on the same question was *less* accurate than the small one, about as good as the official forecast,
  at roughly 1.8 million times the energy per forecast. Small wins. *(The 590× is from timing both small models back to back on the same laptop core; slide 3's 20 joules comes from a
  separate v2 run. The 4B test used an earlier 4-region version of the data; the 8× test used the same 50 regions as
  everything on screen.)*

- **"How efficient is it, really?"** On one CPU core of this MacBook it makes about 300,000 forecasts a second, at
  about 45 millionths of a joule each (chip power above idle; `demo/measure_tiny.py`). The 4-billion-parameter model on
  the same laptop needs about 39 J per forecast: roughly 700,000× more (measured 10-27, page in front). On the earlier 4-region test it was also less
  accurate (error 0.100 vs 0.077).

- **"Where do the dollar figures come from?"** Real prices. Rocky Mountain Power's Wattsmart Business program pays
  $100 per kW a year for load it can cut, up to 65 hours a year, if it answers every call. A 4080 saves 80 W when
  slowed, so that's $8 a chip a year, for at most $1.05 of slower work (65 h × 6% × $0.27, the going rental rate). A
  chip with the same power profile pays its way if it rents under $2.05 an hour; other chips need their own measurement. The phone demo's dollars are Utah's real wholesale price each hour (CAISO).
- **"Why not just slow down every rush hour?"** Utah's rush-hour power costs about 2 cents a kWh wholesale, and it's
  cheaper than other hours: demand peaks in the afternoon, prices peak after sunset. Slowing a chip for energy alone
  pays only above 20 cents. The utility's program is what makes it worth it.
- **"Is the utility's call real?"** The program, its price and its calls are real: Rocky Mountain Power reports every
  Wattsmart Business event to the Utah Public Service Commission. It called 24 in 2023–25, each 15 to 60 minutes, at any
  time of year, using under 5 of its 65 allowed hours a year. None fell in our replay week, so the demo places one at that
  week's highest demand and stretches it to 2 hours so you can see it at replay speed. *(Utah PSC Docket 26-035-24, RMP
  2025 DSM report, Table 16; `data/collected/dr-events/events.csv`.)*
- **"What market?"** 3,523 questions in 2026 ("will Utah be in rush hour 12 hours from now?"); Terra $70,299 vs the
  official forecast $20,487 (3.4×), play money in a standard forecasting market (LMSR).

- **"How good is the solar forecast?"** On 2026 daylight hours it misses by 7.1% of capacity; yesterday-same-hour
  misses by 12.5% (42% lower error). On cloudy days it's half the error. Weather at the solar sites beats Salt Lake
  City weather (10.5%). Inputs are archived forecasts, so no peeking. It tends to run a bit high in the early morning.
- **"Are those sites real?"** No. Site sizes (600–1,000 GPUs) and their own in-house load are simulated and labeled.
  The routing logic and the forecasts are real.
- **"Is the surge number measured?"** One RTX 4080 starting a job is measured (27 W to about 350 W in about 1.5 seconds, at the
  driver's 0.5 s refresh). The 1 MW site is 2,862 copies of it, simulated.
- **"Wired to LA?"** EIA-860M lists each planned plant's balancing authority. 2.5 GW of Utah's 3.6 GW is in LADWP's,
  mostly around Delta and Milford (the Intermountain Power Project's lines run to Los Angeles).

- **"Is the peak real?"** Peak here means demand within 5% of that day's max. Rocky Mountain Power's actual
  dispatch times aren't public, so I used the cleanest label I could build from EIA-930.
- **"Carbon?"** Average carbon of each grid's mix, from EIA fuel data and IPCC factors. Not marginal.
- **"Where does Texas stand?"** EIA's forecast is already good there. The edge is Utah and California.
- **"Is this forecast always late?"** No. Over five years it lines up. This fall it drifted. That's the point:
  a forecast that can drift needs a second opinion that updates every hour.
- **"How long did this take?"** Two days, mostly on a home server and this laptop.

- **"Where do the problem-slide numbers come from?"** $1.1 trillion: Edison Electric Institute, investor-owned utility
  capital spending 2025–29 (all grid spending, not only for peaks). +224 GW: NERC 2025 Long-Term Reliability
  Assessment, summer peak growth over 10 years, data centers the main driver; 13 of 23 areas at elevated or high risk.
  4.4% → 12%: DOE/LBNL, Dec 2024 (high case). 211 billion gallons: LBNL's estimate of water used to generate data
  centers' electricity in 2023, about 12× the ~17 billion gallons used on site. +40%: EIA average heat rates,
  simple-cycle gas ~10,000 Btu/kWh vs combined cycle 7,146 (2020). 48 Utah data centers, "a couple thousand to a couple
  million gallons a day": Deseret News, Aug 2026.
- **"98 GW?"** Duke Nicholas Institute, "Rethinking Load Growth" (Norris et al., Feb 2025): the 22 largest US
  balancing areas could add 76 GW of new load at 0.25% curtailment, 98 GW at 0.5%, 126 GW at 1%; average curtailment
  about 1.7–2.5 hours. It's their study of flexible load in general; Terra is one way AI load gets that flexible.
- **"What's the equation, exactly?"** It's `router/src/decide.ts`: for each region and start delay (0, 3, 6, 12 h)
  that fits the deadline, cost = sum over the job's 4 hours of the forecast rush-hour chance + mean gCO2/kWh / 1000;
  take the lowest. The model (`train/train.py`) is trained with binary cross-entropy on rush hour plus two MSE terms
  (fuel share, carbon), temperature-calibrated on validation, scored by Brier on 2026.
- **"Five training runs?"** v1 (4 grids), v2 (50 grids, shipped), the 4.8M transformer (a 40-epoch run that overfit,
  then a 10-epoch rerun), and the 4B LLM fine-tune.
- **"The chart's two energy bases?"** Transformer vs Terra was timed back to back on one laptop CPU core (590×). The
  LLM vs Terra was total chip power on the same MacBook (690,000×). The LLM's accuracy (3% better than the utility) is
  from the earlier 4-region test; the other two are all 50 regions, 2026.
