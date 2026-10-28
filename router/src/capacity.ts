// Capacity-aware routing: the model's cost ranking from decide.ts, but a job only goes where it fits.
// Each routing grid gets one AI site with a fixed number of GPUs and its own in-house load. Both are
// simulated and labeled on screen: real site sizes aren't public. Jobs run JOB_HOURS on gpuHours / JOB_HOURS GPUs.
import { costs, JOB_HOURS, WAIT_HOURS, type Forecast, type WaitId } from "./decide.ts";

// sized so that over the replay week ~1 job in 3 finds its first choice full and none is left queued
export const SITE_GPUS: Record<string, number> = { PACE: 1000, CISO: 800, BPAT: 600, ERCO: 800 };
const HORIZON = 48;

/** Share of a site's GPUs busy with its own interactive work: 45% at night, up to 75% mid-afternoon local. */
function inHouse(utc: number, tz: string) {
  const h = +new Date(utc * 1000).toLocaleString("en-US", { timeZone: tz, hour: "numeric", hourCycle: "h23" });
  return 0.45 + 0.3 * Math.exp(-(((h - 14) / 4) ** 2));
}

export class Sites {
  booked: Record<string, Float64Array>; // GPUs booked by routed jobs, hour 0 = now
  last = 0;
  tz: Record<string, string>;
  constructor(tz: Record<string, string>) {
    this.tz = tz;
    this.booked = Object.fromEntries(Object.keys(SITE_GPUS).map((r) => [r, new Float64Array(HORIZON)]));
  }

  /** Move the booking window to this replay hour (the replay can skip hours or wrap around). */
  advance(utc: number) {
    const dh = this.last ? Math.round((utc - this.last) / 3600) : 0;
    this.last = utc;
    for (const b of Object.values(this.booked)) {
      if (dh < 0 || dh >= HORIZON) b.fill(0);
      else if (dh > 0) { b.copyWithin(0, dh); b.fill(0, HORIZON - dh); }
    }
  }

  used(region: string, h: number) {
    return SITE_GPUS[region] * inHouse(this.last + h * 3600, this.tz[region]) + this.booked[region][h];
  }

  fits(region: string, start: number, gpus: number) {
    for (let h = start; h < start + JOB_HOURS; h++) if (this.used(region, h) + gpus > SITE_GPUS[region]) return false;
    return true;
  }

  /** Cheapest (region, wait) with room for the whole run; `skipped` = cheaper options that were full. */
  decide(forecasts: Record<string, Forecast>, deadlineHours: number, gpus: number) {
    const options = Object.entries(forecasts).flatMap(([region, f]) => costs(f, deadlineHours).map((c) => ({ region, ...c })));
    options.sort((a, b) => a.cost - b.cost);
    const best = options.find((o) => this.fits(o.region, WAIT_HOURS[o.wait], gpus));
    const skipped = best ? [...new Set(options.slice(0, options.indexOf(best)).map((o) => o.region))].filter((r) => r !== best.region) : [];
    if (best) for (let h = WAIT_HOURS[best.wait]; h < WAIT_HOURS[best.wait] + JOB_HOURS; h++) this.booked[best.region][h] += gpus;
    return { best: best as { region: string; wait: WaitId; cost: number } | undefined, skipped, unconstrained: options[0] };
  }

  snapshot() {
    return Object.fromEntries(Object.keys(SITE_GPUS).map((r) => [r, { gpus: SITE_GPUS[r], busy: +(this.used(r, 0) / SITE_GPUS[r]).toFixed(3) }]));
  }
}
