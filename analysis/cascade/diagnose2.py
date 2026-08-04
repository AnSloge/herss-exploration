#!/usr/bin/env python
"""
Per-instance diagnosis for res_casc_A.

The point of this module is that a gap number on its own says nothing about WHY
the gap is what it is. Every quantity here is something the report has to state:

  traversal        how much of the level range and head range the policy uses
  feasibility      aggressive-action, LRW, start/stop and overflow, with step
                   counts. Overflow is the key number for the working hypothesis
                   that difficulty appears when the spill constraint binds.
  threshold_fit    how well a pure price threshold reproduces the DP's on/off
                   decisions, and the price band where the two disagree
  production       how many distinct production levels the DP optimum actually
                   uses -- a bang-bang optimum is a different object from a
                   modulated one
  hatch            how often the hatch runs at its cap, and how much water is
                   stranded in RES_A at the horizon end. RES_A storage is worth
                   zero under CalcVF as written (see params2.py), so stranded
                   water is pure loss and is the direct cost of the rate limit.
"""

import numpy as np

import replica2 as R2


def traverse(p, actions, inflow_A, inflow_B, prices, restprice):
    vf, steps = R2.simulate_sequence(p, actions, inflow_A, inflow_B, prices, restprice)
    return vf, steps


def summarise(p, label, actions, inflow_A, inflow_B, prices, restprice):
    vf, steps = traverse(p, actions, inflow_A, inflow_B, prices, restprice)
    T = len(steps)
    dt = p.dt_seconds

    masl_A = np.array([s.masl_A_end for s in steps])
    masl_B = np.array([s.masl_B_end for s in steps])
    head = np.array([s.Hnetto for s in steps])
    power = np.array([s.power_MWh for s in steps])
    ovA = np.array([s.overflow_A_Mm3 for s in steps])
    ovB = np.array([s.overflow_B_Mm3 for s in steps])
    hatch = np.array([s.hatchflow_Mm3 for s in steps])
    agg = np.array([s.aggressive_cost for s in steps])
    ss = np.array([s.startstop_cost for s in steps])
    lrwA = np.array([s.lrw_cost_A for s in steps])
    lrwB = np.array([s.lrw_cost_B for s in steps])

    g0 = np.asarray(actions["g0"], float)
    g1 = np.asarray(actions["g1"], float)
    on = (g0 > 0.01) | (g1 > 0.01)

    hatch_cap_Mm3 = p.m3s_to_Mm3(p.upper.hatch_qmax)
    at_cap = np.isclose(hatch, hatch_cap_Mm3, rtol=1e-9, atol=1e-12)

    # RES_A water left at the horizon end, which the objective values at zero
    stranded = R2.remaining_active_Mm3(p.upper, steps[-1].res_A_Mm3_next)

    return {
        "label": label,
        "vf_replica": float(vf),
        "traversal": {
            "masl_A_min": float(masl_A.min()), "masl_A_max": float(masl_A.max()),
            "masl_A_range_used_frac": float((masl_A.max() - masl_A.min())
                                            / (p.upper.HRW - p.upper.LRW)),
            "masl_B_min": float(masl_B.min()), "masl_B_max": float(masl_B.max()),
            "masl_B_range_used_frac": float((masl_B.max() - masl_B.min())
                                            / (p.lower.HRW - p.lower.LRW)),
            "Hnetto_min": float(head.min()), "Hnetto_max": float(head.max()),
            "Hnetto_spread_pct": float(100 * (head.max() - head.min())
                                       / max(1e-9, head.mean())),
        },
        "feasibility": {
            "aggressive_cost_Euro": float(agg.sum()),
            "aggressive_steps": int((agg > 0).sum()),
            "lrw_cost_A_Euro": float(lrwA.sum()), "lrw_steps_A": int((lrwA > 0).sum()),
            "lrw_cost_B_Euro": float(lrwB.sum()), "lrw_steps_B": int((lrwB > 0).sum()),
            "startstop_cost_Euro": float(ss.sum()),
            "startstop_transitions": int(round(ss.sum() / (p.station.powstat_startstop / 2))),
            "overflow_A_Mm3": float(ovA.sum()), "overflow_A_steps": int((ovA > 1e-12).sum()),
            "overflow_B_Mm3": float(ovB.sum()), "overflow_B_steps": int((ovB > 1e-12).sum()),
        },
        "production": {
            "total_MWh": float(power.sum()),
            "steps_on": int(on.sum()),
            "distinct_power_levels": int(len(np.unique(np.round(power, 3)))),
            "distinct_total_Q_levels": int(len(np.unique(np.round(
                [s.total_Q for s in steps], 4)))),
            "steps_both_generators_on": int(((g0 > 0.01) & (g1 > 0.01)).sum()),
            "steps_one_generator_on": int(((g0 > 0.01) ^ (g1 > 0.01)).sum()),
        },
        "hatch": {
            "total_released_Mm3": float(hatch.sum()),
            "capacity_Mm3": float(hatch_cap_Mm3 * T),
            "utilisation_frac": float(hatch.sum() / (hatch_cap_Mm3 * T)),
            "steps_at_cap": int(at_cap.sum()),
            "steps_zero": int((hatch <= 1e-12).sum()),
            "stranded_upper_active_Mm3_at_T": float(stranded),
            "stranded_value_if_counted_Euro": float(
                stranded * p.station.local_energy_equivalent * 1000.0 * restprice),
        },
        "threshold_fit": threshold_separability(on, prices),
    }


def threshold_separability(on, prices):
    """
    Best single price threshold reproducing the policy's on/off pattern, its
    accuracy, and the price band where on and off decisions overlap.

    A high accuracy means the optimum IS essentially a threshold rule, which is
    what a constant marginal water value predicts (CLAUDE.md section 7). A low
    one means something else -- head dependence, spill avoidance, the hatch rate
    limit -- is doing the work.
    """
    prices = np.asarray(prices, float)
    on = np.asarray(on, bool)
    if on.all() or not on.any():
        return {"accuracy": 1.0, "threshold": None, "degenerate": True,
                "overlap_low": None, "overlap_high": None, "n_overlap_steps": 0}

    cands = np.unique(np.concatenate([[-1.0], prices]))
    best = max(cands, key=lambda tau: ((prices > tau) == on).sum())
    acc = float(((prices > best) == on).mean())

    p_on, p_off = prices[on], prices[~on]
    lo, hi = float(p_off.min()), float(p_on.max())
    lo2, hi2 = min(lo, float(p_on.min())), max(hi, float(p_off.max()))
    overlap_lo = max(float(p_on.min()), float(p_off.min()))
    overlap_hi = min(float(p_on.max()), float(p_off.max()))
    if overlap_hi < overlap_lo:
        overlap_lo = overlap_hi = None
        n_overlap = 0
    else:
        n_overlap = int(((prices >= overlap_lo) & (prices <= overlap_hi)).sum())

    return {
        "accuracy": acc,
        "threshold": float(best),
        "degenerate": False,
        "price_on_min": float(p_on.min()), "price_on_max": float(p_on.max()),
        "price_off_min": float(p_off.min()), "price_off_max": float(p_off.max()),
        "overlap_low": overlap_lo, "overlap_high": overlap_hi,
        "n_overlap_steps": n_overlap,
        "_span": [lo2, hi2],
    }
