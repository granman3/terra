// Mirror of train/decide.py: the model predicts, this code decides.
// Cost per (region, start delay) = PEAK_WEIGHT x expected peak hours overlapped + mean gCO2/kWh / 1000.
type RegionId = string;

export const WAIT_HOURS = { now: 0, wait_3h: 3, wait_6h: 6, wait_12h: 12 } as const;
export type WaitId = keyof typeof WAIT_HOURS;
export const JOB_HOURS = 4;
export const PEAK_WEIGHT = 1.0;

export interface Forecast {
  pPeak: Float32Array; // next 24 h, calibrated
  gco2: Float32Array; // next 24 h, g/kWh
}

export function costs(f: Forecast, deadlineHours: number) {
  const out: { wait: WaitId; cost: number }[] = [];
  for (const [wait, start] of Object.entries(WAIT_HOURS) as [WaitId, number][]) {
    if (start + JOB_HOURS > Math.max(deadlineHours, JOB_HOURS)) continue;
    let peak = 0, g = 0;
    for (let h = start; h < start + JOB_HOURS; h++) {
      peak += f.pPeak[h];
      g += f.gco2[h];
    }
    out.push({ wait, cost: PEAK_WEIGHT * peak + g / JOB_HOURS / 1000 });
  }
  return out;
}

export function decide(forecasts: Record<RegionId, Forecast>, deadlineHours: number) {
  const options = (Object.entries(forecasts) as [RegionId, Forecast][]).flatMap(([region, f]) =>
    costs(f, deadlineHours).map((c) => ({ region, ...c })),
  );
  options.sort((a, b) => a.cost - b.cost);
  return { best: options[0], options };
}
