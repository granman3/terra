// Surge smoothing, the TypeScript twin of train/surge.py: the biggest 1 s rise in power when a job's GPUs
// start, all at once vs staggered evenly over STAGGER_S. One RTX 4080 start is measured; the job's GPUs are
// identical copies of it.
import { readFileSync } from "node:fs";

export const STAGGER_S = 60;
const g: { dt_s: number; idle_w: number; watts: number[] } = JSON.parse(
  readFileSync(new URL("../../out/surge/gpu_start.json", import.meta.url), "utf8"),
);

function jump(n: number, staggerS: number) {
  const offs = Array.from({ length: n }, (_, i) => (staggerS ? Math.round((i * staggerS) / n / g.dt_s) : 0));
  const steps = Math.max(...offs) + g.watts.length + 10, total = new Float64Array(steps);
  for (const o of offs) for (let t = 0; t < steps; t++) total[t] += t < o ? g.idle_w : g.watts[Math.min(t - o, g.watts.length - 1)];
  const win = Math.round(1 / g.dt_s);
  let best = 0;
  for (let t = 0; t + win < steps; t++) best = Math.max(best, total[t + win] - total[t]);
  return best;
}

const oneGpu = jump(1, 0);

/** kW of 1 s jump for a job of `gpus` GPUs. */
export function surge(gpus: number) {
  return { gpus, staggerS: STAGGER_S, atOnceKw: +((gpus * oneGpu) / 1e3).toFixed(1), staggeredKw: +(jump(gpus, STAGGER_S) / 1e3).toFixed(2) };
}
