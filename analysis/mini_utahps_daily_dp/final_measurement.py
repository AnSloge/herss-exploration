#!/usr/bin/env python
"""
The decisive measurement (CLAUDE.md section 10 item 6 / analysis report
section 11.4): DP-optimal vs tuned price-threshold on mini_utahps_daily,
cross-checked against the real HERSS simulator (not just replica.py).
"""

import json

import numpy as np

import dp
import oracle
import replica as R
import threshold
import validate as V_


def main():
    version, version_date = oracle.version_info()
    prices, inflows, restprice, reservoir_init_fr = V_.load_dataset()
    T = len(prices)

    print(f"HERSS VERSION {version} / VERSION_DATE {version_date}, upstream commit 029a2d5")
    print(f"Dataset: mini_utahps_daily, T={T} days, reservoir_init_fr={reservoir_init_fr}, restprice={restprice}")
    print()

    print("=== DP (backward induction + forward re-optimization) ===")
    V = dp.backward_induction(prices, inflows, restprice, verbose=False)
    dp_actions, dp_vf_rollout = dp.forward_rollout(V, prices, inflows, restprice, reservoir_init_fr)
    dp_vf_replica, _ = R.simulate_sequence(dp_actions, inflows, prices, reservoir_init_fr, restprice)
    dp_vf_real = oracle.evaluate_vf(dp_actions, restprice)
    n_evals_dp = T * 2 * len(dp.ACTION_GRID_DP) + T * len(dp.ACTION_GRID_FWD)
    print(f"  replica VF  = {dp_vf_replica:.4f}")
    print(f"  real HERSS VF = {dp_vf_real:.4f}  (replica-vs-real diff = {dp_vf_replica - dp_vf_real:.5f})")
    print(f"  grid: storage [{dp.S_MIN},{dp.S_MAX}] x {dp.N_GRID} pts, action grid {len(dp.ACTION_GRID_DP)} (DP) / {len(dp.ACTION_GRID_FWD)} (rollout)")
    print(f"  approx transition evaluations: {n_evals_dp:,}")
    print()

    print("=== Tuned price-threshold baseline ===")
    (K, L, thr_vf_replica), results = threshold.tune_threshold(prices, inflows, restprice, reservoir_init_fr)
    thr_actions = threshold.bangbang_actions(prices, K, L)
    thr_vf_real = oracle.evaluate_vf(thr_actions, restprice)
    n_evals_thr = len(results)
    print(f"  best: K={K} highest-price days on, L={L}")
    print(f"  replica VF  = {thr_vf_replica:.4f}")
    print(f"  real HERSS VF = {thr_vf_real:.4f}  (replica-vs-real diff = {thr_vf_replica - thr_vf_real:.5f})")
    print(f"  evaluations: {n_evals_thr:,} (K x L grid, exhaustive)")
    print()

    print("=== Shipped actions.txt (reference, for context) ===")
    shipped = oracle.load_shipped_actions()
    shipped_vf_real = oracle.evaluate_vf(shipped, restprice)
    print(f"  real HERSS VF = {shipped_vf_real:.4f}")
    print()

    gap_abs = dp_vf_real - thr_vf_real
    gap_pct = 100.0 * gap_abs / dp_vf_real

    print("=== GAP (DP optimal vs tuned threshold), on real HERSS VF ===")
    print(f"  DP        : {dp_vf_real:.4f}")
    print(f"  threshold : {thr_vf_real:.4f}")
    print(f"  gap       : {gap_abs:.4f} EUR  ({gap_pct:.4f} %)")
    print()
    if gap_pct < 1.0:
        verdict = "Gap < ~1%: per CLAUDE.md/report 11.4, formulation is NOT YET a thesis on this instance -- binding structure must be added before committing."
    elif gap_pct > 3.0:
        verdict = "Gap > ~3%: there is a problem worth solving on this instance."
    else:
        verdict = "Gap in the ambiguous 1-3% band."
    print(verdict)

    out = {
        "herss_version": version,
        "herss_version_date": version_date,
        "upstream_commit": "029a2d5",
        "dataset": "mini_utahps_daily",
        "T": T,
        "reservoir_init_fr": reservoir_init_fr,
        "restprice": restprice,
        "dp": {
            "actions": [float(a) for a in dp_actions],
            "vf_replica": dp_vf_replica,
            "vf_real_herss": dp_vf_real,
            "n_transition_evaluations_approx": n_evals_dp,
            "storage_grid": [dp.S_MIN, dp.S_MAX, dp.N_GRID],
            "action_grid_sizes": [len(dp.ACTION_GRID_DP), len(dp.ACTION_GRID_FWD)],
        },
        "threshold": {
            "K": K, "L": L,
            "actions": [float(a) for a in thr_actions],
            "vf_replica": thr_vf_replica,
            "vf_real_herss": thr_vf_real,
            "n_evaluations": n_evals_thr,
        },
        "shipped_actions_vf_real_herss": shipped_vf_real,
        "gap_abs_euro": gap_abs,
        "gap_pct": gap_pct,
        "verdict": verdict,
    }
    with open("result.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Full result written to result.json")


if __name__ == "__main__":
    main()
