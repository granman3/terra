// Export the replay week for the hosted phone demo (web/): the real model's forecasts for every grid,
// every hour, so the static site needs no server. Routing runs in the browser with the same rule as decide.ts.
// Run: node router/src/export-web.ts   ->  web/data/week.json
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { forecastAll, load, type ModelInput } from "./model.ts";
import { JOBS, JOB_MIX_SOURCE } from "./jobs.ts";

const ROOT = new URL("../..", import.meta.url).pathname;
interface ReplayHour extends ModelInput { utc: number; actual: { demand: number; gco2: number; peak: number; share: number } }
const replay: {
  regions: string[]; route: string[];
  meta: Record<string, { tz: string; city: string; ll: [number, number] }>;
  hours: Record<string, ReplayHour[]>;
} = JSON.parse(await readFile(join(ROOT, "data/train/replay_v2.json"), "utf8"));
const numbers = JSON.parse(await readFile(join(ROOT, "deck/numbers.json"), "utf8"));
// one measured 4080 job start (train/surge.py)
const gpuStart = JSON.parse(await readFile(join(ROOT, "out/surge/gpu_start.json"), "utf8"));

await load(replay.regions);
const byUtc = Object.fromEntries(replay.regions.map((r) => [r, new Map(replay.hours[r].map((h) => [h.utc, h]))]));
const times = replay.hours.PACE.map((h) => h.utc).filter((t) => replay.route.every((r) => byUtc[r].has(t)));
const grids = replay.regions.filter((r) => times.some((t) => byUtc[r].has(t)));

const hours = [];
let ms = 0;
for (const utc of times) {
  const inputs = Object.fromEntries(grids.flatMap((r) => (byUtc[r].has(utc) ? [[r, byUtc[r].get(utc)!]] : [])));
  const out = await forecastAll(inputs);
  ms += out.ms;
  const g: Record<string, unknown> = {};
  for (const r of Object.keys(inputs)) {
    const a = inputs[r].actual, f = out.forecasts[r];
    // p: P(peak) for each of the next 24 h in percent; c: gCO2/kWh next 24 h (routing grids only)
    g[r] = { p: Array.from(f.pPeak, (x) => Math.round(x * 100)), s: +a.share.toFixed(2), k: a.peak === 1 ? 1 : 0, g: Math.round(a.gco2),
             ...(replay.route.includes(r) ? { c: Array.from(f.gco2, (x) => Math.round(x)) } : {}) };
  }
  hours.push({ utc, g });
}

const pick = (k: string) => numbers[k]?.value;
const week = {
  made: new Date().toISOString(), route: replay.route,
  grids: Object.fromEntries(grids.map((r) => [r, { city: replay.meta[r].city, ll: replay.meta[r].ll, tz: replay.meta[r].tz }])),
  modelMsPerHour: +(ms / times.length).toFixed(2),
  numbers: { grids: pick("grids"), rawValues: pick("raw_values"), brierVsEia: pick("brier_vs_eia_pct"), utahCatch: pick("utah_catch"),
             peakHoursHit: pick("peak_hours_hit"), gpu4080: pick("gpu_4080"), tinyParams: pick("tiny_params"),
             surge1mw: pick("surge_1mw"),
             // this fall's miss: Utah's actual rush hour vs the official day-ahead forecast, October 2026
             fallActualHour: pick("fall_peak_actual_hour"), fallForecastHour: pick("fall_peak_forecast_hour"), octErr: pick("october_forecast_error_pct"),
             // the problem: the grid can move plants and energy, not demand (PLACE: Utah's planned plants; TIME: the daily swing)
             utah: pick("utah_expansion"), dailySwingMw: pick("daily_swing_mw") },
  jobs: JOBS, jobMixSource: JOB_MIX_SOURCE,
  gpuStart: { dt: gpuStart.dt_s, idle: gpuStart.idle_w, watts: gpuStart.watts.map((w: number) => Math.round(w)) },
  hours,
};
await mkdir(join(ROOT, "web/data"), { recursive: true });
const body = JSON.stringify(week);
await writeFile(join(ROOT, "web/data/week.json"), body);
console.log(`web/data/week.json: ${hours.length} h x ${grids.length} grids, ${(body.length / 1e6).toFixed(2)} MB, model ${week.modelMsPerHour} ms/hour`);
