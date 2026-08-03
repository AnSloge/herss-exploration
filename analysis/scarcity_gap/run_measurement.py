#!/usr/bin/env python
"""
The scarcity-regime gap measurement: exact DP vs four baselines on one
single-reservoir instance, cross-checked against real HERSS.

Usage:
    python run_measurement.py hjelle
    python run_measurement.py gresse
    python run_measurement.py hjelle --energy-equivalent 0.163   # sensitivity

Writes result_<name>.json next to this file. Every run records the upstream
commit, HERSS VERSION/VERSION_DATE, dataset, horizon, seeds and grid sizes.
"""

import argparse
import json
import subprocess
import time

import numpy as np

import baselines
import diagnose
import dp
import oracle
import replica as R
from params import INSTANCES, load_series, regime_numbers

UPSTREAM_PINNED = "029a2d5"
B4_SEEDS = (1, 2)


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def real_vf(key, actions):
    """Cross-check on the real simulator, in an isolated subprocess."""
    return oracle.evaluate_vf_subprocess(key, [float(a) for a in actions])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instance", choices=["hjelle", "gresse", "mini", "hjelle_e163"])
    ap.add_argument("--energy-equivalent", type=float, default=None,
                    help="override LOCAL_ENERGY_EQUIVALENT (sensitivity run)")
    ap.add_argument("--n-grid", type=int, default=None)
    ap.add_argument("--skip-b4", action="store_true")
    args = ap.parse_args()

    key = args.instance
    p = INSTANCES[key]
    if args.energy_equivalent is not None:
        p = p.with_energy_equivalent(args.energy_equivalent)
    prices, inflows, restprice = load_series(p)
    T = len(prices)

    version, version_date = oracle.version_info()
    reg = regime_numbers(p)
    # Grid sizes chosen for EQUAL resolution relative to one step's maximum
    # discharge (~169 grid cells per full-discharge step on both instances),
    # not equal point counts: GRESSE's reachable storage span is ~5x HJELLE's.
    n_grid = args.n_grid or (26001 if key == "gresse" else 8001)

    print(f"=== {p.name} ===")
    print(f"HERSS {version}/{version_date}, upstream pinned {UPSTREAM_PINNED}, "
          f"worktree {git_commit()}")
    print(f"T={T}  restprice={restprice}  init_fr={p.reservoir_init_fr}  "
          f"e={p.local_energy_equivalent}")
    print(f"REGIME:  rho={reg['rho']:.4f}   R={reg['R']:.4f}   "
          f"active={reg['active_Mm3']:.2f} Mm3  init={reg['init_active_Mm3']:.2f} Mm3  "
          f"inflow={reg['inflow_Mm3']:.2f} Mm3  turbine cap={reg['turbine_capacity_Mm3']:.2f} Mm3")
    if reg["rho"] > 1.0:
        print("!! rho > 1: this is NOT the scarcity regime. Stopping.")
        return 2
    print(f"Water value: {restprice * p.local_energy_equivalent * 1000:.0f} EUR/Mm3   "
          f"(price median {np.median(prices):.2f}, mean {np.mean(prices):.2f})")
    print()

    worst = dp.check_against_replica(p, prices, inflows, restprice)
    print(f"dp.transition_block vs replica.step: max abs diff {worst:.2e}\n")

    # ---------------------------------------------------------------- DP
    t0 = time.time()
    sol = dp.solve(p, prices, inflows, restprice, n_grid=n_grid)
    t_dp = time.time() - t0
    print(f"DP: VF(replica) = {sol['vf_replica']:.4f}   [{t_dp:.1f}s]")
    print(f"    grid {sol['state_grid']}, actions {sol['n_action_bwd']}/{sol['n_action_fwd']}, "
          f"{sol['n_transition_evaluations']:,} transition evals")
    print(f"    max res under all-off = {sol['max_res_Mm3_all_off']:.3f} Mm3 "
          f"(grid top {sol['state_grid'][1]:.3f})")

    # convergence: double the storage grid AND the action grids
    t0 = time.time()
    sol2 = dp.solve(p, prices, inflows, restprice, n_grid=2 * n_grid - 1,
                    n_action_bwd=401, n_action_fwd=4001)
    t_conv = time.time() - t0
    dv = sol2["vf_replica"] - sol["vf_replica"]
    print(f"    convergence check (grid x2, actions x2): VF = {sol2['vf_replica']:.4f}, "
          f"delta = {dv:+.4f} EUR ({100*dv/sol['vf_replica']:+.6f} %)  [{t_conv:.1f}s]")
    dp_actions = sol2["actions"] if sol2["vf_replica"] > sol["vf_replica"] else sol["actions"]
    dp_vf_replica = max(sol2["vf_replica"], sol["vf_replica"])
    dp_vf_real = real_vf(key, dp_actions)
    print(f"    DP on REAL HERSS = {dp_vf_real:.4f}  "
          f"(replica-real = {dp_vf_replica - dp_vf_real:+.5f})\n")

    # ---------------------------------------------------------- baselines
    results = {}

    t0 = time.time()
    (tau, vf_b1), n1 = baselines.b1_threshold_full(p, prices, inflows, restprice)
    a1 = [1.0 if pr > tau else 0.0 for pr in prices]
    results["B1"] = {"desc": "price threshold, full production", "params": {"tau": tau},
                     "vf_replica": vf_b1, "evaluations": n1, "actions": a1,
                     "seconds": time.time() - t0}

    t0 = time.time()
    (K, L, vf_b2), n2 = baselines.b2_threshold_level(p, prices, inflows, restprice)
    a2 = baselines.bangbang_actions(prices, K, L)
    results["B2"] = {"desc": "price threshold with tuned level", "params": {"K": K, "L": L},
                     "vf_replica": vf_b2, "evaluations": n2, "actions": a2,
                     "seconds": time.time() - t0}

    t0 = time.time()
    a3, vf_b3, n3 = baselines.b3_myopic(p, prices, inflows, restprice)
    results["B3"] = {"desc": "myopic, no lookahead",
                     "params": {"w_EUR_per_Mm3": restprice * p.local_energy_equivalent * 1000},
                     "vf_replica": vf_b3, "evaluations": n3, "actions": a3,
                     "seconds": time.time() - t0}

    if not args.skip_b4:
        t0 = time.time()
        best4, runs4 = baselines.b4_multistart(p, prices, inflows, restprice,
                                               seeds=B4_SEEDS, verbose=True)
        results["B4"] = {"desc": "multi-start coordinate ascent (Matheussen et al. 2019)",
                         "params": {"seeds": list(B4_SEEDS), "epsilon": 0.01},
                         "vf_replica": best4["fine"]["vf"],
                         "vf_replica_coarse": best4["coarse"]["vf"],
                         "evaluations": sum(r["coarse"]["evaluations"] + r["fine"]["evaluations"]
                                            for r in runs4),
                         "actions": best4["actions"],
                         "runs": [{k: v for k, v in r.items() if k != "actions"} for r in runs4],
                         "seconds": time.time() - t0}

    for name, r in results.items():
        r["vf_real_herss"] = real_vf(key, r["actions"])
        r["gap_pct_vs_dp"] = 100.0 * (dp_vf_real - r["vf_real_herss"]) / dp_vf_real
        print(f"{name} {r['desc']}: params={r['params']}")
        print(f"    VF replica={r['vf_replica']:.4f}  real={r['vf_real_herss']:.4f}  "
              f"gap vs DP = {r['gap_pct_vs_dp']:.4f} %  "
              f"({r['evaluations']:,} evals, {r['seconds']:.1f}s)")

    best_key = max(results, key=lambda k: results[k]["vf_real_herss"])
    gap_pct = results[best_key]["gap_pct_vs_dp"]
    print(f"\nBest baseline: {best_key}   GAP = {gap_pct:.4f} %")
    if gap_pct < 1.0:
        verdict = ("Gap < ~1%: the single-reservoir problem is easy in this regime too. "
                   "All remaining difficulty must come from cascade coupling.")
    elif gap_pct > 3.0:
        verdict = ("Gap > ~3%: 0.29% on mini_utahps_daily was an artefact of water abundance; "
                   "the scarcity regime contains a real optimization problem.")
    else:
        verdict = "Gap in the 1-3% band: report as UNRESOLVED. Do not round toward a wanted answer."
    print(verdict)

    # ---------------------------------------------------------- diagnosis
    print("\n=== diagnosis ===")
    diag = {
        "DP": diagnose.summarise(p, "DP", dp_actions, inflows, prices, restprice),
        best_key: diagnose.summarise(p, best_key, results[best_key]["actions"],
                                     inflows, prices, restprice),
    }
    for lbl, d in diag.items():
        print(f"  {lbl}: masl [{d['masl_min']:.2f}, {d['masl_max']:.2f}] = "
              f"{100*d['masl_span_frac_of_LRW_HRW']:.1f}% of [LRW,HRW]; "
              f"Hnetto traversed {100*d['Hnetto_rel_span_traversed']:.1f}% "
              f"(available {100*d['H_rel_span_available']:.1f}%)")
        print(f"        feasibility: aggressive {d['aggressive_cost_total']:.2f} EUR "
              f"({d['aggressive_steps']} steps), LRW {d['lrw_cost_total']:.2f} EUR "
              f"({d['lrw_steps']} steps), startstop {d['startstop_cost_total']:.2f} EUR "
              f"({d['startstop_transitions']} transitions), overflow "
              f"{d['overflow_total_Mm3']:.3f} Mm3 ({d['overflow_steps']} steps), "
              f"at LRW {d['at_lrw_steps']} steps")
        print(f"        shape: on={d['n_on']} off={d['n_off']} full={d['n_full']} "
              f"partial={d['n_partial']}; threshold accuracy "
              f"{100*d['threshold_shape']['best_accuracy']:.1f}% "
              f"({d['threshold_shape']['misclassified_steps']} misclassified); "
              f"levels when on = {d['level_shape']['n_distinct_levels_when_on']}")

    # ------------------------------------------------ gap decomposition
    decomposition = None
    if gap_pct > 1.0:
        print("\n=== gap decomposition (three SEPARATE restricted DPs; they do NOT sum) ===")
        frozen = (p.LRW + p.HRW) / 2.0   # EXOGENOUS, not read off the DP optimum
        runs = {}
        s_bin = dp.solve(p, prices, inflows, restprice, n_grid=n_grid, binary_actions=True)
        runs["a_timing_only"] = {"desc": "actions restricted to {0,1}, full foresight, full physics",
                                 "vf_replica": s_bin["vf_replica"]}
        s_frz = dp.solve(p, prices, inflows, restprice, n_grid=n_grid, frozen_masl=frozen)
        vf_frz, _ = R.simulate_sequence(p, s_frz["actions"], inflows, prices, restprice)
        runs["b_level_modulation_frozen_head"] = {
            "desc": f"full action grid, head frozen at the exogenous LRW/HRW midpoint {frozen} masl",
            "vf_replica_under_full_physics": vf_frz,
            "frozen_masl": frozen}
        runs["c_full_model"] = {"desc": "full model", "vf_replica": dp_vf_replica}
        for k, v in runs.items():
            val = v.get("vf_replica", v.get("vf_replica_under_full_physics"))
            print(f"  {k}: VF = {val:.2f}  ({100*(dp_vf_replica-val)/dp_vf_replica:.4f} % below full DP)")
        decomposition = runs

    # ---------------------------------------------------------------- out
    out = {
        "herss_version": version, "herss_version_date": version_date,
        "upstream_pinned_commit": UPSTREAM_PINNED, "worktree_commit": git_commit(),
        "instance": p.name, "dataset_dir": p.dataset_dir,
        "T": T, "restprice": restprice, "reservoir_init_fr": p.reservoir_init_fr,
        "local_energy_equivalent": p.local_energy_equivalent,
        "energy_equivalent_override": args.energy_equivalent,
        "regime": reg,
        "dp": {"actions": [float(a) for a in dp_actions],
               "vf_replica": dp_vf_replica, "vf_real_herss": dp_vf_real,
               "grid": sol["state_grid"], "grid_doubled": sol2["state_grid"],
               "vf_base_grid": sol["vf_replica"], "vf_doubled_grid": sol2["vf_replica"],
               "convergence_delta_euro": dv,
               "convergence_delta_pct": 100 * dv / sol["vf_replica"],
               "n_transition_evaluations": sol["n_transition_evaluations"],
               "seconds": t_dp, "seconds_convergence": t_conv},
        "baselines": results,
        "best_baseline": best_key,
        "gap_pct": gap_pct,
        "gap_abs_euro": dp_vf_real - results[best_key]["vf_real_herss"],
        "verdict": verdict,
        "diagnosis": diag,
        "gap_decomposition": decomposition,
    }
    suffix = "" if args.energy_equivalent is None else f"_e{args.energy_equivalent}"
    fn = f"result_{key}{suffix}.json"
    with open(fn, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nWritten to {fn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
