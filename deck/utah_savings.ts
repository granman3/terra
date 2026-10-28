// How much rush-hour power Terra moved off Utah's grid in the replay week, and what it was worth.
// Replays the same week, jobs and capacity rule as router/src/server.ts (one job per replay hour), and
// compares each flexible job with running it right away in Utah. Counts only hours Utah was really in
// rush hour (EIA-930 actual, demand >= 95% of the day's high). The site and jobs are simulated, as on the map.
//   kWh moved   = job kW x Utah rush hours it would have hit now - Utah rush hours it hits with Terra
//   energy $    = kWh moved x PACE real-time price that hour (CAISO OASIS, web/data/prices.json)
//   capacity $  = average kW off Utah's rush hours x $100/kW-yr (Rocky Mountain Power Wattsmart Business), one week's share
// Writes deck/utah_savings.json (totals + per-hour running ledger for demo/live.html).
// Run: node deck/utah_savings.ts
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { forecastAll, load } from "../router/src/model.ts";
import { JOB_HOURS } from "../router/src/decide.ts";
import { Sites } from "../router/src/capacity.ts";
import { JOBS } from "../router/src/jobs.ts";  // the real job mix, shared with the router and the phone

const ROOT = new URL("..", import.meta.url).pathname;
const GPU_KW = 0.276; // one RTX 4080 Super running AI work, measured (out/sweep/jtoken.csv)
const USD_KW_YEAR = 100; // Wattsmart Business, real-time or advance notice
const WAIT: Record<string, number> = { now: 0, wait_3h: 3, wait_6h: 6, wait_12h: 12 };

const replay = JSON.parse(await readFile(join(ROOT, "data/train/replay_v2.json"), "utf8"));
const price: Record<string, number> = JSON.parse(await readFile(join(ROOT, "web/data/prices.json"), "utf8")).usd_per_kwh;
const byUtc = Object.fromEntries(replay.regions.map((r: string) => [r, new Map(replay.hours[r].map((h: any) => [h.utc, h]))])) as Record<string, Map<number, any>>;
const TIMES: number[] = replay.hours.PACE.map((h: any) => h.utc).filter((t: number) => replay.route.every((r: string) => byUtc[r].has(t)));
await load(replay.regions);
const sites = new Sites(Object.fromEntries(replay.route.map((r: string) => [r, replay.meta[r].tz])));
const rush = (utc: number) => byUtc.PACE.get(utc)?.actual.peak === 1;

// Utah's AI load from flexible jobs, kW per UTC hour: run-now-in-Utah vs Terra
const naive = new Map<number, number>(), terra = new Map<number, number>();
const add = (m: Map<number, number>, t: number, kw: number) => m.set(t, (m.get(t) ?? 0) + kw);
let jobs = 0, moved = 0, delayed = 0;
const seen = new Map<number, [number, number]>(); // utc -> [flexible jobs so far, moved out of Utah so far]
for (let tick = 0; tick < TIMES.length; tick++) {
  const utc = TIMES[tick], job = JOBS[tick % JOBS.length];
  const hours = Object.fromEntries(replay.regions.flatMap((r: string) => (byUtc[r].has(utc) ? [[r, byUtc[r].get(utc)]] : [])));
  const { forecasts } = await forecastAll(hours);
  sites.advance(utc);
  if (!job.deadlineHours) continue;
  const gpus = Math.round(job.gpuHours / JOB_HOURS), kw = gpus * GPU_KW;
  const best = sites.decide(Object.fromEntries(replay.route.map((r: string) => [r, forecasts[r]])), job.deadlineHours, gpus).best;
  jobs++;
  for (let h = 0; h < JOB_HOURS; h++) add(naive, utc + h * 3600, kw);
  if (best?.region === "PACE") { if (best.wait !== "now") delayed++; for (let h = 0; h < JOB_HOURS; h++) add(terra, utc + (WAIT[best.wait] + h) * 3600, kw); }
  else moved++;
  seen.set(utc, [jobs, moved]);
}

// ledger over the replay hours, in order: what Terra kept off Utah's grid during Utah's real rush hours
let kwh = 0, usd = 0, rushHours = 0, peakKw = 0;
const ledger: Record<number, { kwh: number; usd: number; jobs: number; moved: number }> = {};
let last: [number, number] = [0, 0];
for (const t of TIMES) {
  if (rush(t)) {
    const off = (naive.get(t) ?? 0) - (terra.get(t) ?? 0);
    rushHours++; kwh += off; usd += off * (price[t] ?? 0); peakKw = Math.max(peakKw, off);
  }
  last = seen.get(t) ?? last;
  ledger[t] = { kwh: Math.round(kwh), usd: +usd.toFixed(2), jobs: last[0], moved: last[1] };
}
const avgKw = kwh / rushHours, capUsdWeek = avgKw * USD_KW_YEAR / 52;
const out = {
  week: `${new Date(TIMES[0] * 1000).toISOString().slice(0, 10)}..${new Date(TIMES.at(-1)! * 1000).toISOString().slice(0, 10)}`,
  site: "one simulated 1,000-chip AI data center in Utah (RTX 4080-class, 276 W each), jobs as on the map",
  flexible_jobs: jobs, moved_out_of_utah: moved, delayed_in_utah: delayed,
  utah_rush_hours: rushHours, kwh_off_utah_rush: Math.round(kwh), avg_kw_off_rush: Math.round(avgKw), max_kw_off_rush: Math.round(peakKw),
  energy_usd: +usd.toFixed(2), avg_price_usd_kwh: +(usd / kwh).toFixed(4),
  capacity_usd_week: Math.round(capUsdWeek), capacity_usd_year: Math.round(avgKw * USD_KW_YEAR),
  usd_kw_year: USD_KW_YEAR,
  ledger,
};
await writeFile(join(ROOT, "deck/utah_savings.json"), JSON.stringify(out));
const { ledger: _, ...summary } = out;
console.log(summary);
