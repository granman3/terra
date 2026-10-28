"""The router's decision rule, in one place (the numbers a human should review).

The model predicts; this code decides. For a deferrable job of JOB_HOURS that must
finish within DEADLINE_H, every (region, start delay) option gets a cost:
  PEAK_WEIGHT x (expected peak hours the job overlaps) + (mean gCO2/kWh while it runs) / 1000
and the cheapest option wins. Peak relief comes first, carbon second.
The TypeScript router mirrors this (router/src/decide.ts).
"""
import numpy as np

WAITS = {"now": 0, "wait_3h": 3, "wait_6h": 6, "wait_12h": 12}
JOB_HOURS = 4
DEADLINE_H = 16
PEAK_WEIGHT = 1.0


def job_hours_mask(wait_index, horizon=24):
    start = list(WAITS.values())[wait_index]
    m = np.zeros(horizon, bool)
    m[start:start + JOB_HOURS] = True
    return m


def cost_matrix(p_peak, gco2):
    """p_peak, gco2: (..., regions, 24) -> cost (..., regions, waits)."""
    costs = []
    for w in range(len(WAITS)):
        m = job_hours_mask(w, p_peak.shape[-1])
        costs.append(PEAK_WEIGHT * p_peak[..., m].sum(-1) + gco2[..., m].mean(-1) / 1000)
    return np.stack(costs, -1)
