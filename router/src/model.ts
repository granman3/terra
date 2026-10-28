// Our model side: the Terra grid model (v3 transformer if present, else the v2 MLP; trained on the RTX 4080), run with ONNX Runtime.
import ort from "onnxruntime-node";
import { existsSync } from "node:fs";
import type { Forecast } from "./decide.ts";

export interface ModelInput {
  past: number[][]; // 48 x 5: demand, gCO2, solar, wind, interchange
  fut: number[][]; // 24 x 10: EIA forecast, 7 weather forecasts, sun elevation, holiday
  cal: number[]; // 6
  mkt: number[]; // 6: yesterday's hub prices + Henry Hub
}

let session: ort.InferenceSession | undefined;
let regionIndex: Record<string, number> = {};

const MODEL_PATH = ["v3", "v2"].map((v) => new URL(`../../out/${v}/mycelium.onnx`, import.meta.url).pathname).find((f) => existsSync(f))!;
export const MODEL_VERSION = MODEL_PATH.includes("/v3/") ? "v3" : "v2";

/** regions: the training order (index = region embedding id). */
export async function load(regions: string[], path = MODEL_PATH) {
  regionIndex = Object.fromEntries(regions.map((r, i) => [r, i]));
  session ??= await ort.InferenceSession.create(path);
}

/** One batched call for every grid; returns per-grid 24 h forecasts and the time it took. */
export async function forecastAll(inputs: Record<string, ModelInput>) {
  const ids = Object.keys(inputs);
  const n = ids.length;
  const P = inputs[ids[0]].past[0].length, F = inputs[ids[0]].fut[0].length, M = inputs[ids[0]].mkt.length;
  const past = new Float32Array(n * 48 * P), fut = new Float32Array(n * 24 * F), cal = new Float32Array(n * 6), mkt = new Float32Array(n * M);
  const region = new BigInt64Array(n);
  ids.forEach((id, i) => {
    past.set(inputs[id].past.flat(), i * 48 * P);
    fut.set(inputs[id].fut.flat(), i * 24 * F);
    cal.set(inputs[id].cal, i * 6);
    mkt.set(inputs[id].mkt, i * M);
    region[i] = BigInt(regionIndex[id]);
  });
  const t0 = performance.now();
  const out = await session!.run({
    past: new ort.Tensor("float32", past, [n, 48, P]),
    fut: new ort.Tensor("float32", fut, [n, 24, F]),
    cal: new ort.Tensor("float32", cal, [n, 6]),
    region: new ort.Tensor("int64", region, [n]),
    mkt: new ort.Tensor("float32", mkt, [n, M]),
  });
  const ms = performance.now() - t0;
  const p = out.p_peak.data as Float32Array, g = out.gco2.data as Float32Array;
  const forecasts = Object.fromEntries(
    ids.map((id, i) => [id, { pPeak: p.slice(i * 24, i * 24 + 24), gco2: g.slice(i * 24, i * 24 + 24) } satisfies Forecast]),
  );
  return { forecasts, ms };
}
