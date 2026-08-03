#!/usr/bin/env python
"""
Diagnostics for a solved action sequence: what the policy actually did, which
constraints were actually active, and what shape the policy has.

Everything here is read off the replica trace, which validate_replica.py has
shown to agree with real HERSS to |dVF| < 0.03 EUR on values of 1.3-7.4 MEUR.
"""

import numpy as np

import replica as R


def traverse(p, actions, inflows, prices, restprice, reservoir_init_fr=None):
    vf, steps = R.simulate_sequence(p, actions, inflows, prices, restprice, reservoir_init_fr)

    masl = np.array([s.end_of_stp_masl for s in steps])
    on = np.array([a > 0.01 for a in actions])
    H = np.array([s.Hnetto for s, o in zip(steps, on)])
    H_prod = H[on] if on.any() else np.array([np.nan])
    Q = np.array([s.tunnel_flow_m3s for s in steps])

    masl_lo, masl_hi = float(masl.min()), float(masl.max())
    available = p.HRW - p.LRW
    H_available_max = p.HRW - p.powstat_masl
    H_available_min = p.LRW - p.powstat_masl

    return {
        "vf_replica": vf,
        "steps": steps,
        # --- reservoir level actually traversed ---
        "masl_min": masl_lo,
        "masl_max": masl_hi,
        "masl_span": masl_hi - masl_lo,
        "masl_span_frac_of_LRW_HRW": (masl_hi - masl_lo) / available,
        "LRW": p.LRW, "HRW": p.HRW,
        # --- net head actually traversed (production steps only) ---
        "Hnetto_min": float(np.min(H_prod)),
        "Hnetto_max": float(np.max(H_prod)),
        "Hnetto_rel_span_traversed": float((np.max(H_prod) - np.min(H_prod)) / np.max(H_prod)),
        "H_rel_span_available": (H_available_max - H_available_min) / H_available_max,
        # --- feasibility table ---
        "aggressive_cost_total": sum(s.aggressive_cost for s in steps),
        "aggressive_steps": int(sum(1 for s in steps if s.aggressive_cost > 0)),
        "lrw_cost_total": sum(s.res_cost_lrw for s in steps),
        "lrw_steps": int(sum(1 for s in steps if s.res_cost_lrw > 0)),
        "startstop_cost_total": sum(s.startstop_cost for s in steps),
        "startstop_transitions": int(sum(1 for s in steps if s.startstop_cost > 0)),
        "overflow_total_Mm3": sum(s.overflow_Mm3 for s in steps),
        "overflow_steps": int(sum(1 for s in steps if s.overflow_Mm3 > 1e-12)),
        "at_lrw_steps": int(sum(1 for s in steps
                                if s.res_Mm3_next <= p.filling_at_lrw_Mm3 + 1e-9)),
        # --- policy shape ---
        "n_on": int(on.sum()),
        "n_off": int((~on).sum()),
        "n_full": int(sum(1 for a in actions if a > 0.999)),
        "n_partial": int(sum(1 for a in actions if 0.01 < a <= 0.999)),
        "Q_mean_when_on": float(Q[on].mean()) if on.any() else 0.0,
        "income_total": sum(s.income for s in steps),
        "production_MWh": sum(s.power_MWh for s in steps),
        "terminal_value": R.terminal_value_Euro(p, steps[-1].res_Mm3_next, restprice),
        "final_res_Mm3": steps[-1].res_Mm3_next,
    }


def threshold_separability(actions, prices):
    """
    How close is the policy to a pure price threshold?

    Reports the best achievable accuracy of the rule "on iff p_t > tau" against
    the policy's own on/off pattern, and the price overlap between on- and
    off-steps. A policy that a threshold rule cannot express shows up as
    misclassified steps that no tau removes.
    """
    T = len(actions)
    on = np.array([a > 0.01 for a in actions])
    pr = np.array(prices, dtype=float)
    if on.all() or (~on).any() is False:
        pass
    best = (0.0, -1.0)
    for tau in np.unique(pr):
        pred = pr > tau
        acc = float((pred == on).mean())
        if acc > best[1]:
            best = (float(tau), acc)
    out = {
        "best_tau": best[0],
        "best_accuracy": best[1],
        "misclassified_steps": int(round((1 - best[1]) * T)),
    }
    if on.any() and (~on).any():
        out["min_price_when_on"] = float(pr[on].min())
        out["max_price_when_off"] = float(pr[~on].max())
        out["price_overlap"] = float(pr[~on].max() - pr[on].min())
    return out


def level_modulation(actions, p, steps):
    """
    Does the policy modulate the production LEVEL, and does that level co-vary
    with reservoir filling? A pure threshold rule cannot express either.
    """
    a = np.array(actions, dtype=float)
    on = a > 0.01
    if on.sum() < 3:
        return {"n_distinct_levels_when_on": int(len(np.unique(np.round(a[on], 3))))}
    fill = np.array([s.res_Mm3_next for s in steps])[on]
    lvl = a[on]
    out = {
        "n_distinct_levels_when_on": int(len(np.unique(np.round(lvl, 3)))),
        "level_mean": float(lvl.mean()),
        "level_std": float(lvl.std()),
        "level_min": float(lvl.min()),
        "level_max": float(lvl.max()),
    }
    if lvl.std() > 1e-9 and fill.std() > 1e-9:
        out["corr_level_vs_filling"] = float(np.corrcoef(lvl, fill)[0, 1])
    # best efficiency point of the turbine curve
    k = int(np.argmax(p.turbine_curve_pct))
    out["turbine_best_eff_q"] = float(p.turbine_curve_q[k])
    out["turbine_best_eff_pct"] = float(p.turbine_curve_pct[k])
    q = np.array([s.tunnel_flow_m3s for s in steps])[on]
    out["frac_steps_within_5pct_of_best_eff_q"] = float(
        np.mean(np.abs(q - p.turbine_curve_q[k]) <= 0.05 * p.turbine_curve_q[k]))
    return out


def summarise(p, label, actions, inflows, prices, restprice):
    d = traverse(p, actions, inflows, prices, restprice)
    steps = d.pop("steps")
    d["label"] = label
    d["threshold_shape"] = threshold_separability(actions, prices)
    d["level_shape"] = level_modulation(actions, p, steps)
    return d
