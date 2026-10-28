// Mycelium router: replays a real grid week for 51 US grids, runs the model on all of them every
// tick, routes AI jobs between the four routing grids, and bridges the live demand-response agent
// (the Mac's own GPU, demo/mac_agent.py) to the browser.
//
//   GET  /            live map page (demo/live.html)
//   GET  /stream      server-sent events: one replay hour per tick, forecasts for every grid + the routing call,
//                     site room (capacity.ts), the job's start surge (surge.ts) and Utah solar (train/solar.py)
//   GET  /power       proxy of the agent's power stream
//   POST /dr/:action  load | unload | event | restore, forwarded to the agent
//   POST /jump        skip the replay to 2 h before the next (simulated) Rocky Mountain Power event
//
// Env (router/.env.demo): DR_URL, DR_TOKEN, TICK_MS, AUTO_DR=1 (downshift when the utility calls an event)
// Run: npm start
import { createServer, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { forecastAll, load, type ModelInput } from "./model.ts";
import { JOB_HOURS, WAIT_HOURS } from "./decide.ts";
import { Sites } from "./capacity.ts";
import { JOBS } from "./jobs.ts";
import { surge } from "./surge.ts";

const ROOT = new URL("../..", import.meta.url).pathname;
const PORT = Number(process.env.PORT ?? 8787);
const TICK_MS = Number(process.env.TICK_MS ?? 1200);
// Utah's rush hours replay slower so the live map's moves can be followed on stage
const RUSH_SLOWDOWN = Number(process.env.RUSH_SLOWDOWN ?? 2.5);
const DR_URL = process.env.DR_URL ?? "http://127.0.0.1:8765";
const DR_TOKEN = process.env.DR_TOKEN ?? "";
const AUTO_DR = process.env.AUTO_DR === "1";
// Slow down when Rocky Mountain Power calls a Wattsmart Business event (the utility decides when; up to 65 h a year).
// RMP reports every event to the Utah PSC (24 Business calls in 2023-25, 15-60 min; data/collected/dr-events), but none
// fell in the replay week, so the replay's event is simulated and stretched to 2 h: its highest-demand hours
// (train/math_layer.py, enroll.replay_event). No file, no events.
const EVENT_UTC = new Set<number>(await readFile(join(ROOT, "out/math/metrics.json"), "utf8")
  .then((t) => JSON.parse(t).enroll.replay_event.utc).catch(() => []));

interface ReplayHour extends ModelInput {
  utc: number;
  actual: { demand: number; forecast: number; gco2: number; peak: number; share: number };
}
const replay: {
  regions: string[]; route: string[];
  meta: Record<string, { tz: string; city: string; ll: [number, number] }>;
  hours: Record<string, ReplayHour[]>;
} = JSON.parse(await readFile(join(ROOT, "data/train/replay_v2.json"), "utf8"));
// replay hours by UTC, so every grid is read at the same moment (grids can miss different hours)
const byUtc = Object.fromEntries(replay.regions.map((r) => [r, new Map(replay.hours[r].map((h) => [h.utc, h]))]));
const TIMES = replay.hours.PACE.map((h) => h.utc).filter((t) => replay.route.every((r) => byUtc[r].has(t)));

const sites = new Sites(Object.fromEntries(replay.route.map((r) => [r, replay.meta[r].tz])));

// Utah solar, forecast from archived desert weather forecasts (train/solar.py), by UTC hour
const solarReplay: { capacity_mw: number; hours: { utc: number; pred: number | null; actual: number | null }[] } =
  JSON.parse(await readFile(join(ROOT, "data/train/solar_replay.json"), "utf8"));
const solarBy = new Map(solarReplay.hours.map((h) => [h.utc, h]));
const solarTomorrow = await readFile(join(ROOT, "out/solar/tomorrow.json"), "utf8").then(JSON.parse).catch(() => null);
function solar(utc: number) {
  const next = Array.from({ length: 24 }, (_, h) => solarBy.get(utc + h * 3600));
  return { pred: next.map((h) => h?.pred ?? null), actual: next.map((h) => h?.actual ?? null), band: next.map((h) => h?.band ?? null) };
}

const clients = new Set<ServerResponse>();
let tick = 0;
let drMode = "normal";

async function dr(action: string) {
  const r = await fetch(`${DR_URL}/${action}`, { method: "POST", headers: { "X-Token": DR_TOKEN } });
  const body = await r.json();
  drMode = body.mode ?? drMode;
  return body;
}

function send(obj: unknown) {
  const line = `data: ${JSON.stringify(obj)}\n\n`;
  for (const c of clients) c.write(line);
}

/** Stage control: move the replay to 2 hours before the next (simulated) utility event. */
function jumpToUtahPeak() {
  const peak = (k: number) => EVENT_UTC.has(TIMES[k % TIMES.length]);
  const now = tick % TIMES.length;
  for (let d = 3; d < TIMES.length + 3; d++) {
    const k = now + d;
    if (peak(k) && !peak(k - 1)) {
      tick = (k - 2) % TIMES.length;
      return { jumped: true, peakAt: TIMES[k % TIMES.length] };
    }
  }
  return { jumped: false };
}

async function step() {
  const utc = TIMES[tick % TIMES.length];
  const job = JOBS[tick % JOBS.length];
  tick++;
  const hours = Object.fromEntries(replay.regions.flatMap((r) => (byUtc[r].has(utc) ? [[r, byUtc[r].get(utc)!]] : [])));
  const { forecasts, ms } = await forecastAll(hours);
  const utahPeak = forecasts.PACE.pPeak[0];
  const utilityCall = EVENT_UTC.has(utc);
  const interactive = job.deadlineHours === 0;
  const routeF = Object.fromEntries(replay.route.map((r) => [r, forecasts[r]]));
  sites.advance(utc);
  const gpus = Math.round(job.gpuHours / JOB_HOURS);
  const call = interactive ? null : sites.decide(routeF, job.deadlineHours, gpus);
  const ours = interactive
    ? { region: "PACE", wait: "now", action: utilityCall ? "stay, shed" : "stay", ms }
    : call!.best
      ? { region: call!.best.region, wait: call!.best.wait, action: "route", ms, gpus, skipped: call!.skipped, surge: surge(gpus) }
      : { region: null, wait: "queued", action: "no room anywhere", ms, gpus, skipped: call!.skipped };

  if (AUTO_DR) {
    if (utilityCall && drMode !== "event") await dr("event").catch(() => {});
    if (!utilityCall && drMode === "event") await dr("restore").catch(() => {});
  }

  const regions = Object.fromEntries(Object.entries(hours).map(([r, h]) => [r, {
    gco2: Math.round(h.actual.gco2), inPeak: h.actual.peak === 1, share: +h.actual.share.toFixed(3),
    pPeakNow: +forecasts[r].pPeak[0].toFixed(3),
  }]));
  const nPeak = Object.values(regions).filter((r) => r.pPeakNow > 0.5).length;
  send({ tick, utc, job, ours, utahPeak, utilityCall, drMode, autoDr: AUTO_DR, grids: Object.keys(hours).length, nPeak, regions,
    sites: sites.snapshot(), solar: solar(utc) });
  return regions.PACE?.inPeak || utahPeak > 0.5;
}

const TYPES: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg" };

createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  try {
    if (url.pathname === "/stream") {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
      res.write(`data: ${JSON.stringify({ hello: true, autoDr: AUTO_DR, waits: WAIT_HOURS, route: replay.route, meta: replay.meta, solarTomorrow, events: [...EVENT_UTC] })}\n\n`);
      clients.add(res);
      req.on("close", () => clients.delete(res));
      return;
    }
    if (url.pathname === "/power") {
      const up = await fetch(`${DR_URL}/power`);
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
      const reader = up.body!.getReader();
      req.on("close", () => reader.cancel().catch(() => {}));
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        res.write(value);
      }
      return res.end();
    }
    if (req.method === "POST" && url.pathname === "/jump") {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify(jumpToUtahPeak()));
    }
    if (req.method === "POST" && url.pathname.startsWith("/dr/")) {
      const action = url.pathname.slice(4);
      if (!["load", "unload", "event", "restore"].includes(action)) throw new Error("bad action");
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify(await dr(action)));
    }
    let rel = url.pathname === "/" ? "demo/live.html" : normalize(url.pathname).replace(/^\/+/, "");
    if (rel.endsWith("/")) rel += "index.html";
    if (!/^(demo|mockups|deck)\//.test(rel) || rel.includes(".venv")) throw Object.assign(new Error("not found"), { code: 404 });
    const body = await readFile(join(ROOT, rel));
    res.writeHead(200, { "Content-Type": TYPES[extname(rel)] ?? "application/octet-stream" });
    res.end(body);
  } catch (e: any) {
    if (!res.headersSent) res.writeHead(e.code === 404 || e.code === "ENOENT" ? 404 : 500, { "Content-Type": "text/plain" });
    res.end(String(e.message ?? e));
  }
}).listen(PORT, async () => {
  await load(replay.regions);
  console.log(`mycelium router on http://localhost:${PORT}  replay ${TIMES.length} h x ${replay.regions.length} grids, tick ${TICK_MS} ms, dr ${DR_URL}${AUTO_DR ? ", auto-DR" : ""}`);
  const loop = () => step().catch((e) => { console.error("step", e); return false; }).then((rush) => setTimeout(loop, rush ? TICK_MS * RUSH_SLOWDOWN : TICK_MS));
  loop();
});
