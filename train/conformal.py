"""Conformal prediction helpers (numpy only), shared by train/math_layer.py and train/solar.py.

split_q:  split conformal (Vovk et al.; Angelopoulos & Bates 2021). The ceil((n+1)(1-alpha))/n quantile of the
          calibration scores; P(score <= q) >= 1 - alpha if future scores are exchangeable with them.
aci:      adaptive conformal inference (Gibbs & Candes, NeurIPS 2021). alpha_{t+1} = alpha_t + gamma (alpha - err_t):
          the long-run miss rate converges to alpha for any sequence, shifted or not. Run strictly in time order: an
          item's score only counts once its target time has passed.
"""
import numpy as np


def split_q(scores, alpha):
    n = len(scores)
    return float(np.quantile(scores, min(1.0, np.ceil((n + 1) * (1 - alpha)) / n), method="higher"))


def aci(cal_scores, scores, issue, target, alpha, gamma=0.005, window=20000):
    """Per-item threshold q_i (the set for item i is {score <= q_i}) and the final alpha_t.

    cal_scores: known before the first item (e.g. validation). scores/issue/target: the items, any order.
    """
    known = list(cal_scores[-window:])
    q = np.full(len(scores), np.nan)
    by_target = np.argsort(target, kind="stable")
    k, a_t = 0, alpha
    for t in np.unique(issue):
        # everything whose hour has passed by t: count its miss, then add its score
        while k < len(by_target) and target[by_target[k]] < t:
            i = by_target[k]
            k += 1
            a_t += gamma * (alpha - float(scores[i] > q[i]))
            known.append(scores[i])
        if len(known) > window:
            del known[: len(known) - window]
        level = 1 - a_t
        qt = np.inf if level >= 1 else -np.inf if level <= 0 else float(np.quantile(known, level, method="higher"))
        q[issue == t] = qt
    return q, a_t
