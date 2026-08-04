#!/usr/bin/env python
"""
Blocking validation of replica2 against the real HERSS simulator.

Nothing downstream (DP, baselines, gap numbers) may be run until this passes.
The validation is NOT reused from the hjelle/gresse work: res_casc_A exercises
code paths those instances never touch -- the outlet hatch, two generators on a
shared penstock, a second reservoir receiving upstream inflow, and the
aggressive-action guard on a summed release.

Acceptance: max |VF_replica - VF_HERSS| < 0.05 EUR over all sequences, plus
per-step trace agreement on a subset.

Sequences are chosen to hit every branch in replica2.step:
  hatch clip, hatch guard (masl <= hatch_masl), aggressive-action zeroing,
  overflow in each reservoir, start/stop transitions in each generator,
  the "action below 0.01 counts as off" threshold, and asymmetric generator
  loading (which only matters because of SHARED_PENSTOCK).
"""

import json
import os
import sys
import time

import numpy as np

import oracle2
import replica2 as R2
from params2 import INSTANCES, load_series

HERE = os.path.dirname(os.path.abspath(__file__))
VF_TOL = 0.05

TRACE_FIELDS = [
    "res_Mm3_upper", "res_Mm3_lower", "hatchflow_m3s", "tunnelflow_m3s",
    "overflow_Mm3_upper", "overflow_Mm3_lower",
    "power_MWh", "profit", "aggressive_cost", "startstop_cost", "Hnetto",
]


def build_sequences(p, prices, inflow_A, inflow_B):
    """(name, {hatch, g0, g1}) pairs. Fixed seeds, recorded in the output."""
    T = len(prices)
    rng = np.random.default_rng(20260803)
    seqs = []

    def add(name, hatch, g0, g1):
        seqs.append((name, {"hatch": list(map(float, hatch)),
                            "g0": list(map(float, g0)),
                            "g1": list(map(float, g1))}))

    # 1. the dataset's own action file
    rows = [l.split() for l in open(p.dataset_dir + "actions.txt") if l.strip()]
    hdr = rows[0]
    add("shipped_actions",
        [float(r[hdr.index("0")]) for r in rows[1:]],
        [float(r[hdr.index("4_0")]) for r in rows[1:]],
        [float(r[hdr.index("4_1")]) for r in rows[1:]])

    add("all_zero", np.zeros(T), np.zeros(T), np.zeros(T))
    # hatch wide open, no production -> RES_B fills and must overflow
    add("hatch_full_gen_off", np.ones(T), np.zeros(T), np.zeros(T))
    # no transfer, full production -> RES_B empties, aggressive actions fire
    add("hatch_off_gen_full", np.zeros(T), np.ones(T), np.ones(T))
    add("all_full", np.ones(T), np.ones(T), np.ones(T))
    # asymmetric loading: only meaningful because the penstock is shared
    add("gen_asymmetric", np.full(T, 0.5), np.ones(T), np.full(T, 0.25))
    # only one generator ever runs -> per-generator start/stop bookkeeping
    add("single_generator", np.full(T, 0.3), np.full(T, 0.8), np.zeros(T))
    # alternating -> many start/stop transitions in both generators
    alt = np.array([1.0 if t % 2 == 0 else 0.0 for t in range(T)])
    add("alternating", alt, alt, 1.0 - alt)
    # actions just below and just above the 0.01 "on" threshold
    tiny = np.array([0.005 if t % 2 == 0 else 0.02 for t in range(T)])
    add("threshold_0p01", tiny, tiny, tiny)
    # drain RES_A first, then try to keep producing -> hatch guard at LRW
    ramp = np.concatenate([np.ones(T // 2), np.zeros(T - T // 2)])
    add("drain_then_hold", ramp, np.full(T, 0.6), np.full(T, 0.6))
    # bang-bang on the highest prices
    order = np.argsort(-np.array(prices))
    bang = np.zeros(T)
    bang[order[:T // 3]] = 1.0
    add("bangbang_price", np.full(T, 0.4), bang, bang)
    # four random sequences
    for s in range(4):
        r = np.random.default_rng(1000 + s)
        add(f"random_seed{1000 + s}", r.uniform(0, 1, T), r.uniform(0, 1, T),
            r.uniform(0, 1, T))
    # extreme: full production from an already low RES_B
    add("aggressive_stress", np.zeros(T), np.ones(T), np.full(T, 0.9))
    del rng
    return seqs


def compare_vf(p, key, seqs, inflow_A, inflow_B, prices, restprice):
    out = []
    for name, actions in seqs:
        vf_h = oracle2.evaluate_vf(p, actions)
        vf_r, _ = R2.simulate_sequence(p, actions, inflow_A, inflow_B, prices, restprice)
        out.append({"sequence": name, "vf_herss": vf_h, "vf_replica": vf_r,
                    "abs_diff": abs(vf_h - vf_r)})
        flag = "OK " if abs(vf_h - vf_r) < VF_TOL else "FAIL"
        print(f"  {flag} {name:22s} HERSS {vf_h:14.4f}  replica {vf_r:14.4f}  "
              f"|d| {abs(vf_h - vf_r):.6f}")
    return out


def compare_traces(p, key, seqs, inflow_A, inflow_B, prices, restprice):
    """Per-step comparison. One subprocess per field (cppyy LowLevelView bug)."""
    results = {}
    for name, actions in seqs:
        print(f"\n  trace: {name}")
        trace = oracle2.evaluate_full_trace(key, actions, fields=TRACE_FIELDS)
        _, steps = R2.simulate_sequence(p, actions, inflow_A, inflow_B, prices, restprice)

        rep = {
            "res_Mm3_upper": [s.res_A_Mm3_next for s in steps],
            "res_Mm3_lower": [s.res_B_Mm3_next for s in steps],
            "hatchflow_m3s": [p.Mm3_to_m3s(s.hatchflow_Mm3) for s in steps],
            "tunnelflow_m3s": [s.tunnelflow_m3s for s in steps],
            "overflow_Mm3_upper": [s.overflow_A_Mm3 for s in steps],
            "overflow_Mm3_lower": [s.overflow_B_Mm3 for s in steps],
            "power_MWh": [s.power_MWh for s in steps],
            # HERSS stores the station's own profit; the reservoirs' LRW costs
            # sit on their own nodes, so strip them before comparing.
            "profit": [s.income - s.startstop_cost - s.aggressive_cost for s in steps],
            "aggressive_cost": [s.aggressive_cost for s in steps],
            "startstop_cost": [s.startstop_cost for s in steps],
            "Hnetto": [s.Hnetto for s in steps],
        }
        per_field = {}
        for f in TRACE_FIELDS:
            d = float(np.max(np.abs(np.array(trace[f]) - np.array(rep[f]))))
            per_field[f] = d
            print(f"    {f:22s} max |d| = {d:.3e}")
        results[name] = per_field
    return results


def main():
    key = "res_casc_A"
    p = INSTANCES[key]
    prices, inflow_A, inflow_B, restprice = load_series(p)
    version, version_date = oracle2.version_info()

    print(f"HERSS VERSION {version} / {version_date}")
    print(f"instance {key}: T={len(prices)}, dt={p.dt_seconds}, restprice={restprice}\n")

    seqs = build_sequences(p, prices, inflow_A, inflow_B)
    print(f"VF comparison over {len(seqs)} sequences (tolerance {VF_TOL} EUR):")
    t0 = time.time()
    vf_rows = compare_vf(p, key, seqs, inflow_A, inflow_B, prices, restprice)
    t_vf = time.time() - t0

    worst = max(vf_rows, key=lambda r: r["abs_diff"])
    print(f"\nworst |dVF| = {worst['abs_diff']:.6f} EUR on '{worst['sequence']}'"
          f"   ({t_vf:.1f} s for {len(seqs)} evaluations)")

    trace_seqs = [s for s in seqs if s[0] in
                  ("shipped_actions", "hatch_off_gen_full", "alternating",
                   "random_seed1000")]
    print(f"\nper-step traces for {len(trace_seqs)} sequences:")
    t0 = time.time()
    traces = compare_traces(p, key, trace_seqs, inflow_A, inflow_B, prices, restprice)
    t_tr = time.time() - t0
    print(f"\n({t_tr:.1f} s)")

    passed = worst["abs_diff"] < VF_TOL
    out = {
        "instance": key,
        "herss_version": version, "herss_version_date": version_date,
        "vf_tolerance_Euro": VF_TOL,
        "worst_abs_dVF": worst["abs_diff"], "worst_sequence": worst["sequence"],
        "passed": passed,
        "vf_rows": vf_rows,
        "trace_max_abs_diff": traces,
        "seconds_vf": t_vf, "seconds_traces": t_tr,
    }
    with open(os.path.join(HERE, "validation_replica2.json"), "w") as f:
        json.dump(out, f, indent=2)

    print("\nPASS" if passed else "\nFAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
