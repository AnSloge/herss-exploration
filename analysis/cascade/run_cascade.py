#!/usr/bin/env python
"""
The res_casc_A measurement.

Stages, written incrementally to result_res_casc_A*.json so partial results
survive an interrupted run:

  1  provenance and regime numbers, timestep verified from the simulator
  2  main DP + blocking cross-check of the DP policy against real HERSS
  3  baselines B0, B2, B3 (two water-value variants), B4 and B5, each winner
     cross-checked against real HERSS
  4  diagnosis of the DP optimum and of the best baseline
  5  DP convergence: state grid doubled, and action grid refined
  6  the synthetic corrected-objective variant (task A4), reported separately

Gaps are computed on HERSS values, never on replica values.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

import baselines2 as BL
import diagnose2 as DG
import dp2
import oracle2
import replica2 as R2
from params2 import INSTANCES, load_series, regime_numbers

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = (1, 2)


def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()


def save(obj, name):
    with open(os.path.join(HERE, name), "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  [saved {name}]", flush=True)


def herss_vf(p, actions):
    return oracle2.evaluate_vf(p, actions)


def run_instance(key, do_convergence, out_name, seeds=SEEDS):
    p = INSTANCES[key]
    prices, qA, qB, rp = load_series(p)
    s = BL.Series(p, prices, qA, qB, rp)
    version, version_date = oracle2.version_info()

    result = {
        "instance": key,
        "value_upper_storage": p.value_upper_storage,
        "git_commit": git_commit(),
        "herss_version": version,
        "herss_version_date": version_date,
        "seeds": list(seeds),
        "restprice": rp,
        "regime": regime_numbers(p),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ---- 1 provenance -------------------------------------------------------
    dts = oracle2.evaluate_dt(p)
    result["dt_verified"] = {"distinct": sorted(set(dts)), "T": len(dts)}
    assert len(set(dts)) == 1 and dts[0] == p.dt_seconds, dts[:5]
    print(f"[{key}] T={len(dts)}, dt={dts[0]} (verified from Dataset::getDeltaT)")
    print(f"[{key}] regime: rho_system={result['regime']['rho_system']:.4f}, "
          f"R_system={result['regime']['R_system']:.4f}, "
          f"hatch_binding_ratio={result['regime']['hatch_binding_ratio']:.4f}",
          flush=True)
    save(result, out_name)

    # ---- 2 main DP ----------------------------------------------------------
    print(f"[{key}] DP main (161x161 state, 21x21 action) ...", flush=True)
    t0 = time.time()
    dp_main = dp2.solve(p, prices, qA, qB, rp, n_a=161, n_b=161,
                        n_hatch_bwd=21, n_gen_bwd=21,
                        n_hatch_fwd=201, n_gen_fwd=101, verbose=True)
    dp_main["seconds"] = time.time() - t0
    dp_main["vf_herss"] = herss_vf(p, dp_main["actions"])
    dp_main["herss_minus_replica"] = dp_main["vf_herss"] - dp_main["vf_replica"]
    print(f"[{key}] DP main: replica {dp_main['vf_replica']:.4f}, "
          f"HERSS {dp_main['vf_herss']:.4f}, "
          f"|d| {abs(dp_main['herss_minus_replica']):.6f}  "
          f"[{dp_main['seconds'] / 60:.1f} min]", flush=True)
    # Blocking: the generator-relabelling reduction is only valid if the emitted
    # per-generator action sequence reproduces the DP value in the real simulator.
    assert abs(dp_main["herss_minus_replica"]) < 0.05, (
        "DP policy does not reproduce in HERSS -- the relabelling reduction is "
        "not valid; fall back to full (a_g0, a_g1) enumeration with 4 prev-states")
    result["dp_main"] = dp_main
    save(result, out_name)

    dp_vf = dp_main["vf_herss"]

    def gap(vf_h):
        return 100.0 * (dp_vf - vf_h) / dp_vf

    # ---- 3 baselines --------------------------------------------------------
    baselines = {}

    a0, vf0, b0 = BL.b0_shipped(s)
    baselines["B0"] = {"description": "shipped actions.txt",
                       "vf_replica": vf0, "vf_herss": herss_vf(p, a0),
                       "budget": b0.as_dict(), "actions": a0}

    print(f"[{key}] B2 ...", flush=True)
    a2, vf2, par2, b2 = BL.b2_threshold_level_hatch(s)
    baselines["B2"] = {"description": "price threshold + level + constant hatch level",
                       "parameters": par2, "vf_replica": vf2,
                       "vf_herss": herss_vf(p, a2), "budget": b2.as_dict(),
                       "actions": a2}

    print(f"[{key}] B3 ...", flush=True)
    w = rp * p.station.local_energy_equivalent * 1000.0
    a3, vf3, b3 = BL.b3_myopic(s)
    baselines["B3"] = {"description": f"myopic, PRIMARY: w_upper = w_lower = {w:.1f} EUR/Mm3",
                       "w_lower": w, "w_upper": w, "vf_replica": vf3,
                       "vf_herss": herss_vf(p, a3), "budget": b3.as_dict(),
                       "actions": a3}
    a3b, vf3b, b3b = BL.b3_myopic(s, w_upper=0.0)
    baselines["B3_wA0"] = {
        "description": "myopic, SECONDARY: w_upper = 0 (true terminal derivative "
                       "for RES_A, but conflates lookahead loss with the "
                       "modelling artefact -- see baselines2.b3_myopic)",
        "w_lower": w, "w_upper": 0.0, "vf_replica": vf3b,
        "vf_herss": herss_vf(p, a3b), "budget": b3b.as_dict(), "actions": a3b}

    for tag, pairwise in (("B4", False), ("B5", True)):
        print(f"[{key}] {tag} (pairwise={pairwise}, seeds={seeds}) ...", flush=True)
        best, runs, spread = BL.multistart(s, pairwise=pairwise, seeds=seeds)
        acts = best["actions"]
        baselines[tag] = {
            "description": ("coordinate ascent, single-variable moves"
                            if not pairwise else
                            "coordinate ascent, single + pairwise moves (a,b,c)"),
            "vf_replica": best["fine"]["vf"], "vf_herss": herss_vf(p, acts),
            "restart_spread_Euro": spread,
            "runs": [{k: v for k, v in r.items() if k != "actions"} for r in runs],
            "budget": {
                "n_full_evaluations": sum(r["budget"]["n_full_evaluations"] for r in runs),
                "n_step_cells": sum(r["budget"]["n_step_cells"] for r in runs),
                "seconds": round(sum(r["budget"]["seconds"] for r in runs), 2)},
            "actions": acts,
        }

    for tag, b in baselines.items():
        b["gap_vs_dp_pct"] = gap(b["vf_herss"])
        print(f"[{key}] {tag:8s} HERSS {b['vf_herss']:12.4f}   "
              f"gap {b['gap_vs_dp_pct']:8.4f} %", flush=True)
    result["baselines"] = baselines
    result["dp_vf_herss"] = dp_vf

    b4, b5 = baselines["B4"], baselines["B5"]
    result["B5_minus_B4"] = {
        "euro": b5["vf_herss"] - b4["vf_herss"],
        "pct_of_vf": 100.0 * (b5["vf_herss"] - b4["vf_herss"]) / dp_vf,
        "B4_restart_spread_pct_of_vf": 100.0 * b4["restart_spread_Euro"] / dp_vf,
        "B5_restart_spread_pct_of_vf": 100.0 * b5["restart_spread_Euro"] / dp_vf,
        "significance_threshold_pct": 0.49,
        "note": "threshold fixed before measurement at the HJELLE B4 restart "
                "spread, 0.49 % of VF",
    }
    save(result, out_name)

    # ---- 4 diagnosis --------------------------------------------------------
    diag = {"DP": DG.summarise(p, "DP", dp_main["actions"], qA, qB, prices, rp)}
    for tag in ("B2", "B4", "B5"):
        diag[tag] = DG.summarise(p, tag, baselines[tag]["actions"], qA, qB, prices, rp)
    result["diagnosis"] = diag
    print(f"[{key}] DP overflow: A {diag['DP']['feasibility']['overflow_A_Mm3']:.3f} Mm3 "
          f"({diag['DP']['feasibility']['overflow_A_steps']} steps), "
          f"B {diag['DP']['feasibility']['overflow_B_Mm3']:.3f} Mm3 "
          f"({diag['DP']['feasibility']['overflow_B_steps']} steps)", flush=True)
    print(f"[{key}] DP hatch utilisation "
          f"{diag['DP']['hatch']['utilisation_frac']:.3f}, stranded "
          f"{diag['DP']['hatch']['stranded_upper_active_Mm3_at_T']:.3f} Mm3", flush=True)
    save(result, out_name)

    # ---- 5 convergence ------------------------------------------------------
    if do_convergence:
        conv = {}
        print(f"[{key}] convergence: state grid doubled (321x321) ...", flush=True)
        t0 = time.time()
        d = dp2.solve(p, prices, qA, qB, rp, n_a=321, n_b=321,
                      n_hatch_bwd=21, n_gen_bwd=21,
                      n_hatch_fwd=201, n_gen_fwd=101, verbose=True)
        d["seconds"] = time.time() - t0
        d["vf_herss"] = herss_vf(p, d["actions"])
        conv["state_321"] = {k: v for k, v in d.items() if k != "actions"}
        conv["state_321"]["delta_vs_main_Euro"] = d["vf_herss"] - dp_vf
        print(f"[{key}]   321x321 HERSS {d['vf_herss']:.4f} "
              f"(d = {d['vf_herss'] - dp_vf:+.4f} EUR, "
              f"{100 * (d['vf_herss'] - dp_vf) / dp_vf:+.5f} %)"
              f"  [{d['seconds'] / 60:.1f} min]", flush=True)
        result["convergence"] = conv
        save(result, out_name)

        print(f"[{key}] convergence: action grid refined (41 hatch x 31 gen) ...",
              flush=True)
        t0 = time.time()
        d = dp2.solve(p, prices, qA, qB, rp, n_a=161, n_b=161,
                      n_hatch_bwd=41, n_gen_bwd=31,
                      n_hatch_fwd=201, n_gen_fwd=101, verbose=True)
        d["seconds"] = time.time() - t0
        d["vf_herss"] = herss_vf(p, d["actions"])
        conv["action_41x31"] = {k: v for k, v in d.items() if k != "actions"}
        conv["action_41x31"]["delta_vs_main_Euro"] = d["vf_herss"] - dp_vf
        print(f"[{key}]   41x31 HERSS {d['vf_herss']:.4f} "
              f"(d = {d['vf_herss'] - dp_vf:+.4f} EUR, "
              f"{100 * (d['vf_herss'] - dp_vf) / dp_vf:+.5f} %)"
              f"  [{d['seconds'] / 60:.1f} min]", flush=True)
        result["convergence"] = conv
        save(result, out_name)

    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save(result, out_name)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="res_casc_A")
    ap.add_argument("--no-convergence", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = args.out or f"result_{args.instance}.json"
    run_instance(args.instance, not args.no_convergence, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
