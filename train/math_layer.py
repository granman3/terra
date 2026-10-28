"""The math under the AI: three proven results on top of the Terra model, scored on Utah (PACE).

1. Demand-response enrollment. No real Utah energy price pays for slowing a chip (wholesale rush-hour power is ~2 cents,
   breakeven is ~20 cents; train/rush_prices.py), but Rocky Mountain Power's Wattsmart Business program pays per kW
   the utility may cut, for up to 65 hours a year, any hour, events called by the utility. So the utility decides
   *when*; the decision left is *which chips to enroll*: a chip pays its way iff
   incentive * saved_kW >= max_hours * slow_pct * chip_hour_usd, i.e. it is cheaper than
   incentive * saved_kW / (max_hours * slow_pct) per hour. Plus a simulated event for the replay week (RMP doesn't
   publish its event history): the week's highest-demand hours.
2. Conformal prediction. Split conformal (Vovk et al.; Angelopoulos & Bates 2021) gives a set that holds the truth
   >= 1 - alpha of the time for any model, but only if the future is exchangeable with the calibration data, and on
   2026 it isn't (the grid shifted; see conformal_rush.split.test_coverage). Adaptive conformal inference (Gibbs &
   Candes 2021) fixes that: alpha_{t+1} = alpha_t + gamma (alpha - err_t) makes the long-run miss rate converge to
   alpha for ANY sequence, no assumptions. Here: per-hour rush-hour sets ({rush}, {clear} or "can't rule out"),
   run strictly in time order (an hour's outcome is only used once that hour has passed). Solar bands: train/solar.py.
3. LMSR forecast market (Hanson 2003). Terra, EIA's day-ahead forecast and "same as yesterday" each trade on
   "Will Utah be in rush hour at hour X?", 12 h ahead. The market maker's price is the softmax of its shares, its
   loss is capped at b ln 2 per question, and a trader who moves the price p -> q earns b ln(q_o / p_o): exactly its
   log-score gain. Profits are averaged over every trading order.

Inputs: data/train/dataset_v2.npz (same splits as train.py: val = 2025-07..12, test = 2026), out/v2/mycelium.pt,
data/train/hourly_v2.parquet. Writes out/math/metrics.json.
Run: uv run --with numpy --with pandas --with pyarrow --with torch python train/math_layer.py
"""
import itertools
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from conformal import aci, split_q
from train import build, kind_of

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "math"
TINY = Path(os.environ.get("TINY", ROOT / "out" / "v2" / "mycelium.pt")).resolve()
BA, ALPHA, LEAD, B = "PACE", 0.10, 12, 100.0
# real prices (sources in README, "What a rush-hour kWh is worth")
GPU_HOUR_USD = 0.27  # median on-demand RTX 4080 rental, getdeploying.com, 2026-10-27
SLOW_PCT, SAVED_W = 0.06, 80.0  # measured on the 4080: clock lock = 6% slower, 276 -> 196 W
# Rocky Mountain Power Wattsmart Business demand response (Utah Schedule 114, effective 2025-04-25): $ per kW a year,
# up to 65 dispatch hours a year, 4 a day, all hours of the year. $100 is the published rate for either dispatch type;
# $125 the tariff maximum; $175 both types. (The $45 summer peak-management option is left out: its hour cap isn't published.)
DR_USD_KW_YEAR, DR_MAX_HOURS, DR_EVENT_HOURS = 100.0, 65, 2
DR_LEVELS = {"Real-time or advance notice": 100.0, "Tariff maximum": 125.0, "Both": 175.0}
C_SLOW = SLOW_PCT * GPU_HOUR_USD  # $ per chip-hour slowed


def load():
    z = np.load(ROOT / "data" / "train" / "dataset_v2.npz")
    regions = list(z["regions"])
    m = z["region"] == regions.index(BA)
    split = z["split"][m]
    d = {k: z[k][m] for k in ("past", "fut", "cal", "mkt", "region", "y_peak", "base_share", "utc")}
    sd = torch.load(TINY, map_location="cpu")  # v2 MLP or v3 TerraNet, same forward and outputs
    model = build(kind_of(sd), len(regions), d["past"].shape[2], d["fut"].shape[2], d["mkt"].shape[1])
    model.load_state_dict(sd)
    model.eval()
    with torch.no_grad():
        t = lambda k: torch.as_tensor(d[k])
        logit, _, _ = model(t("past"), t("fut"), t("cal"), t("region"), t("mkt"))
        d["p"] = torch.sigmoid(logit / model.temperature).numpy()
    return d, split


def fit_logistic(x, y):
    """P(y) = sigmoid(a (x - c)), fit by maximum likelihood (the same calibrated-EIA baseline as train.py)."""
    ab = torch.tensor([20.0, 0.95], requires_grad=True)
    x, y = torch.as_tensor(x, dtype=torch.float32), torch.as_tensor(y, dtype=torch.float32)
    opt = torch.optim.LBFGS([ab], lr=0.1, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(ab[0] * (x - ab[1]), y)
        loss.backward()
        return loss
    opt.step(closure)
    a, c = ab.detach().numpy()
    return lambda v: 1 / (1 + np.exp(-a * (v - c)))


def breakeven(usd_kw_year):
    """Most a chip-hour can be worth and still pay its way in the program (all 65 h called, every one slowed)."""
    return usd_kw_year * SAVED_W / 1000 / (DR_MAX_HOURS * SLOW_PCT)


def enroll():
    """Per chip and per 1,000 chips a year: what the program pays, the worst-case cost of slowing, and the breakeven."""
    prices = json.loads((OUT / "prices.json").read_text()) if (OUT / "prices.json").exists() else None
    pay = DR_USD_KW_YEAR * SAVED_W / 1000  # $ per chip a year
    cost = DR_MAX_HOURS * C_SLOW  # $ per chip a year if all 65 h are called
    return {
        "rule": "slow down when the utility calls; enroll a chip iff it is worth less than the breakeven per hour",
        "assumptions": {"gpu_hour_usd": GPU_HOUR_USD, "slow_pct": SLOW_PCT, "saved_w": SAVED_W,
                        "dr_usd_kw_year": DR_USD_KW_YEAR, "dr_max_hours": DR_MAX_HOURS},
        "per_chip_year_usd": {"paid": round(pay, 2), "worst_case_cost": round(cost, 2), "net": round(pay - cost, 2)},
        "per_1000_chips_year_usd": {"paid": round(pay * 1000), "worst_case_cost": round(cost * 1000), "net": round((pay - cost) * 1000)},
        "breakeven_chip_hour_usd": round(breakeven(DR_USD_KW_YEAR), 2),
        "times_over_breakeven": round(breakeven(DR_USD_KW_YEAR) / GPU_HOUR_USD, 1),
        "wholesale_breakeven_usd_kwh": round(C_SLOW / (SAVED_W / 1000), 3),  # what a kWh would have to be worth without the program
        "wholesale_rush_usd_kwh": prices["wholesale"]["rush_mean_usd_kwh"] if prices else None,
        "levels": [{"program": k, "usd_kw_year": v, "net_per_1000_chips_year_usd": round((v * SAVED_W / 1000 - cost) * 1000),
                    "breakeven_chip_hour_usd": round(breakeven(v), 2)} for k, v in DR_LEVELS.items()],
        "replay_event": replay_event(),
    }


def replay_event():
    """Simulated: one DR_EVENT_HOURS-hour event at the replay week's highest-demand hours (the router and dashboard use it).
    65 h a year is ~1.25 h a week, so one 2 h event is a little above an average week."""
    hours = json.loads((ROOT / "data" / "train" / "replay_v2.json").read_text())["hours"]["PACE"]
    dem = [h["actual"]["demand"] for h in hours]
    k = max(range(len(hours) - DR_EVENT_HOURS + 1), key=lambda i: sum(dem[i:i + DR_EVENT_HOURS]))
    return {"utc": [hours[i]["utc"] for i in range(k, k + DR_EVENT_HOURS)], "simulated": True,
            "why": "Rocky Mountain Power doesn't publish its event history; placed at the replay week's highest demand"}


def conformal_rush(d, split):
    """Per-hour sets from nonconformity 1 - p(true label): calibrated on 2025 H2, then 2026 in time order.
    The set for an hour holds "rush" if p >= 1 - q and "clear" if p <= q; both = can't rule out."""
    va, te = split == 1, split == 2
    score = lambda p, y: 1 - np.where(y == 1, p, 1 - p)
    s_cal = score(d["p"][va].ravel(), d["y_peak"][va].ravel())
    pt, yt = d["p"][te], d["y_peak"][te]
    issue = np.repeat(d["utc"][te], pt.shape[1])
    target = issue + np.tile(np.arange(pt.shape[1]) * 3600, len(pt))
    pt, yt = pt.ravel(), yt.ravel()
    s_te = score(pt, yt)

    def summary(q):
        has_rush, has_clear = pt >= 1 - q, pt <= q
        return {"test_coverage": round(float((s_te <= q).mean()), 4), "share_decided": round(float((has_rush ^ has_clear).mean()), 4),
                "share_cant_rule_out": round(float((has_rush & has_clear).mean()), 4)}
    q_split = split_q(s_cal, ALPHA)
    q_aci, a_end = aci(s_cal, s_te, issue, target, ALPHA)
    months = pd.to_datetime(target, unit="s").month
    worst = min(float((s_te[months == m] <= q_aci[months == m]).mean()) for m in np.unique(months))
    return {"alpha": ALPHA, "calibration_hours": int(len(s_cal)), "test_hours": int(len(s_te)),
            "split": {"q_hat": round(q_split, 4), **summary(q_split)},
            "adaptive": {"gamma": 0.005, "alpha_end": round(a_end, 4), **summary(q_aci), "worst_month_coverage": round(worst, 4)}}


def market(d, split):
    """LMSR on 'rush hour at t + LEAD?', opening at 0.5; profits averaged over all trading orders."""
    va, te = split == 1, split == 2
    eia = fit_logistic(d["base_share"][va, LEAD][np.isfinite(d["base_share"][va, LEAD])],
                       d["y_peak"][va, LEAD][np.isfinite(d["base_share"][va, LEAD])])
    # same as yesterday: P(rush at hour X | rush at hour X yesterday), the two rates from 2025 H2
    h = pd.read_parquet(ROOT / "data" / "train" / "hourly_v2.parquet", columns=["utc", "ba", "peak"])
    pk = h[h["ba"] == BA].set_index("utc")["peak"]
    pk.index = pd.to_datetime(pk.index, utc=True)

    def yesterday(rows):
        t = pd.to_datetime(d["utc"][rows] + LEAD * 3600 - 86400, unit="s", utc=True)
        return pk.reindex(t).to_numpy()
    yv, lv = yesterday(va), d["y_peak"][va, LEAD]
    ok = np.isfinite(yv)
    rate = {k: float(lv[ok][yv[ok] == k].mean()) for k in (0, 1)}
    yt = yesterday(te)
    probs = {"Terra": d["p"][te, LEAD], "EIA forecast": eia(d["base_share"][te, LEAD]),
             "Same as yesterday": np.where(yt == 1, rate[1], rate[0])}
    ok = np.isfinite(probs["EIA forecast"]) & np.isfinite(yt)
    outcome = d["y_peak"][te, LEAD][ok]
    P = {k: np.clip(v[ok], 1e-3, 1 - 1e-3) for k, v in probs.items()}
    prob_of = lambda p: np.where(outcome == 1, p, 1 - p)
    profit = {k: 0.0 for k in P}
    orders = list(itertools.permutations(P))
    for order in orders:
        price = np.full(len(outcome), 0.5)
        for k in order:  # each trader moves the price to its own belief; LMSR pays b ln(q_o / p_o)
            profit[k] += float(np.sum(B * np.log(prob_of(P[k]) / prob_of(price)))) / len(orders)
            price = P[k]
    log_loss = {k: round(float(-np.mean(np.log(prob_of(v)))), 4) for k, v in P.items()}
    return {"question": f"Will Utah be in rush hour {LEAD} h from now?", "b_usd": B, "opening_price": 0.5,
            "max_loss_per_question_usd": round(B * np.log(2), 2), "questions": int(len(outcome)), "orders_averaged": len(orders),
            "profit_usd": {k: round(v) for k, v in profit.items()}, "log_loss": log_loss,
            "same_as_yesterday_rates": {"after_rush": round(rate[1], 3), "after_clear": round(rate[0], 3)}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d, split = load()
    m = {"region": BA, "model": str(TINY.relative_to(ROOT)), "enroll": enroll(),
         "conformal_rush": conformal_rush(d, split), "market": market(d, split)}
    (OUT / "metrics.json").write_text(json.dumps(m, indent=1))
    # what the deck's math slide shows (the router only serves deck/)
    sol = json.loads((ROOT / "out" / "solar" / "metrics.json").read_text()) if (ROOT / "out" / "solar" / "metrics.json").exists() else None
    e, c, mk = m["enroll"], m["conformal_rush"], m["market"]
    (ROOT / "deck" / "math.json").write_text(json.dumps({
        "source": "out/math/metrics.json", "model": m["model"],
        "enroll": {k: e[k] for k in ("assumptions", "per_1000_chips_year_usd", "breakeven_chip_hour_usd", "times_over_breakeven",
                                     "wholesale_breakeven_usd_kwh", "wholesale_rush_usd_kwh", "levels")},
        "rush_target": 1 - c["alpha"], "rush_adaptive": c["adaptive"]["test_coverage"], "rush_split": c["split"]["test_coverage"],
        "solar_adaptive": sol["band_90"]["adaptive"]["test_coverage"] if sol else None,
        "market": {"questions": mk["questions"], "profit_usd": mk["profit_usd"], "max_loss_usd": mk["max_loss_per_question_usd"], "lead_h": LEAD},
    }, indent=1))
    (ROOT / "web" / "data" / "dr_event.json").write_text(json.dumps(e["replay_event"]))  # the static dashboard's copy
    print(json.dumps({k: v for k, v in m.items()}, indent=1)[:3500])


if __name__ == "__main__":
    main()
