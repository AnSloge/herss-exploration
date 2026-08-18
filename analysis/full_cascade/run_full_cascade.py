#!/usr/bin/env python
"""
The utahps_daily measurement.

Stages, each written incrementally to result_utahps_daily.json so partial results
survive an interrupted run:

  provenance  commit, HERSS version, verified timestep, regime numbers,
              channel impulse response
  baselines   B0, B1, B2, B3, each winner cross-checked against real HERSS
  b4          >= 8 independent restarts, one process per seed, run in parallel.
              THE RESTART SPREAD IS THE HEADLINE RESULT and is reported as min,
              max, median, standard deviation and the full distribution.
  b5          pairwise moves continued from B4's best, gain decomposed by
              neighbourhood type
  diagnose    spill, feasibility, operation and coupling for every method

There is no DP and no MILP bound. The state space is 4 reservoir volumes + 11
channel linear-reservoir storages + 4 commitment states, about 19 dimensions;
exact DP is not merely expensive but impossible. Without a bound, every gap in
this report is a DIFFERENCE BETWEEN METHODS and is never phrased as a percentage
from optimum.

Gaps are computed on HERSS values, never on replica values.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baselines3 as BL
import diagnose3 as DG
import oracle3
import params3
import replica3

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
RESULT = "result_utahps_daily.json"


def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()


def load_result(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  [saved {os.path.basename(path)}]", flush=True)


def make_series():
    p = params3.get()
    plan = replica3.build_plan(p)
    prices, inflow, restprice = params3.load_series(p)
    return p, plan, BL.Series(plan, prices, inflow, restprice)


def herss_vf(p, s, M):
    return float(oracle3.evaluate_vf(p, s.to_dict(M)))


# ------------------------------------------------------------------ provenance

def stage_provenance(p, s, result, path):
    version, version_date = oracle3.version_info()
    dts = oracle3.evaluate_dt(p)
    assert len(set(dts)) == 1 and dts[0] == p.dt_seconds, dts[:5]

    result.update({
        "instance": p.name,
        "git_commit": git_commit(),
        "herss_version": version,
        "herss_version_date": version_date,
        "upstream_pinned": "029a2d5298bddff55740c33a5971343df74824b7",
        "T": s.T,
        "n_decision_variables": s.T * s.n_sta,
        "restprice": s.restprice,
        "dt_verified": {"distinct": sorted(set(dts)), "T": len(dts),
                        "source": "Dataset::getDeltaT"},
        "chain_equivalent_kWh_m3": {r.name: p.chain_equivalent[r.idnr]
                                    for r in p.reservoirs},
        "regime_static": params3.regime_numbers(p),
        "channel_impulse_response": {
            str(k): {kk: (vv if not isinstance(vv, list) else [float(x) for x in vv])
                     for kk, vv in v.items()}
            for k, v in params3.channel_impulse_response(p).items()},
        "state_space_note": (
            f"{len(p.reservoirs)} reservoir volumes + "
            f"{plan_linres(p)} channel linear-reservoir storages + "
            f"{len(p.stations)} commitment states: exact DP is not attempted"),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    print(f"[provenance] T={s.T}, dt={dts[0]} s (verified), "
          f"{s.T * s.n_sta} decision variables", flush=True)
    for r in p.reservoirs:
        d = result["regime_static"]["per_reservoir"][r.idnr]
        print(f"[regime] {r.name:12s} R={d['R']:.3f} rho_own={d['rho_own']:.3f} "
              f"rho_full<={d['rho_full_bound']:.3f} "
              f"e_chain={d['chain_equivalent_kWh_m3']:.2f}", flush=True)
    save(result, path)
    return result


def plan_linres(p):
    return sum(c.n_linres for c in p.channels)


# ------------------------------------------------------------------ baselines

def stage_baselines(p, s, result, path, verbose=False):
    bl = result.get("baselines", {})

    print("[B0] shipped actions_utahps.txt ...", flush=True)
    r = BL.b0_shipped(s, params3.load_actions(p))
    bl["B0"] = _record(p, s, "shipped actions_utahps.txt", r)

    print("[B1] price threshold per station ...", flush=True)
    r = BL.b1_threshold(s, verbose=verbose)
    bl["B1"] = _record(p, s, "price threshold per station, full production", r)

    print("[B2] price threshold + level per station ...", flush=True)
    r = BL.b2_threshold_level(s, verbose=verbose)
    bl["B2"] = _record(p, s, "price threshold + tuned level per station", r)

    print("[B3] myopic, water valued at RESTPRICE * chain equivalent ...", flush=True)
    r = BL.b3_myopic(s, verbose=verbose)
    bl["B3"] = _record(p, s, "myopic, no lookahead, chain-equivalent water value", r)

    result["baselines"] = bl
    for tag, b in bl.items():
        print(f"[{tag}] HERSS {b['vf_herss']:16.4f}  "
              f"replica {b['vf_replica']:16.4f}  "
              f"|d| {abs(b['herss_minus_replica']):.4f}", flush=True)
    save(result, path)
    return result


def _record(p, s, description, r):
    M = r["M"]
    vf_h = herss_vf(p, s, M)
    out = {"description": description, "vf_replica": float(r["vf"]),
           "vf_herss": vf_h, "herss_minus_replica": vf_h - float(r["vf"]),
           "budget": r["budget"],
           "actions": s.to_dict(M)}
    for k in ("parameters", "water_value_EUR_per_Mm3"):
        if k in r:
            out[k] = r[k]
    return out


# ------------------------------------------------------------------ B4

def b4_worker(seed, out_path, time_limit, epsilon):
    p, plan, s = make_series()
    t0 = time.time()
    r = BL.b4_restart(s, seed=seed, epsilon=epsilon, time_limit=time_limit,
                      verbose=True)
    payload = {"seed": seed, "coarse": r["coarse"], "fine": r["fine"],
               "polish_gain": r["polish_gain"], "converged": r["converged"],
               "budget": r["budget"], "wall_clock_seconds": time.time() - t0,
               "vf_replica": r["fine"]["vf"],
               "M": [[float(x) for x in row] for row in r["M"]]}
    with open(out_path, "w") as f:
        json.dump(payload, f)
    print(f"[b4 seed {seed}] VF {r['fine']['vf']:.4f} "
          f"converged={r['converged']} {(time.time() - t0) / 3600:.2f} h", flush=True)


def stage_b4(p, s, result, path, seeds, time_limit, epsilon, jobs):
    """
    One process per seed. Restarts are independent, so this is scheduling, not an
    approximation: each restart's own wall clock is reported, never the sum.
    """
    # one thread per worker: eight of these share sixteen cores, and BLAS threads
    # inside each would make per-restart wall clock depend on what the others are
    # doing -- which is the number being reported
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1")
    outs, failed = {}, []
    t0 = time.time()
    pending, running = list(seeds), []

    while pending or running:
        while pending and len(running) < jobs:
            seed = pending.pop(0)
            out = os.path.join(HERE, f"b4_seed{seed}.json")
            outs[seed] = out
            if os.path.exists(out):
                os.unlink(out)
            log = open(os.path.join(HERE, f"b4_seed{seed}.log"), "w")
            cmd = [sys.executable, os.path.abspath(__file__), "--b4-worker",
                   str(seed), "--b4-out", out, "--epsilon", str(epsilon)]
            if time_limit is not None:
                cmd += ["--time-limit", str(time_limit)]
            running.append((seed, subprocess.Popen(cmd, cwd=HERE, env=env,
                                                   stdout=log, stderr=log), log))
            print(f"[b4] launched seed {seed}", flush=True)
        time.sleep(5)
        for item in list(running):
            seed, proc, log = item
            if proc.poll() is not None:
                log.close()
                running.remove(item)
                ok = proc.returncode == 0 and os.path.exists(outs[seed])
                if not ok:
                    failed.append(seed)
                print(f"[b4] seed {seed} finished rc={proc.returncode} "
                      f"{'' if ok else '(FAILED -- see b4_seed%d.log)' % seed}",
                      flush=True)

    runs = []
    for seed in seeds:
        if seed in failed:
            continue
        with open(outs[seed]) as f:
            runs.append(json.load(f))
    if failed:
        # a missing restart changes what the spread means, so it is recorded
        # rather than quietly reducing the sample
        print(f"[b4] WARNING: {len(failed)} of {len(seeds)} restarts failed: "
              f"{failed}", flush=True)
    if not runs:
        raise RuntimeError("every B4 restart failed; see b4_seed*.log")

    vfs_replica = np.array([r["vf_replica"] for r in runs])
    for r in runs:
        r["vf_herss"] = herss_vf(p, s, np.array(r["M"]))
    vfs = np.array([r["vf_herss"] for r in runs])

    best = max(runs, key=lambda r: r["vf_herss"])
    spread = float(vfs.max() - vfs.min())
    result["B4"] = {
        "description": "coordinate ascent, single-variable moves, multi-start",
        "seeds": list(seeds),
        "seeds_failed": failed,
        "n_restarts": len(runs),
        "all_converged": all(r["converged"] for r in runs),
        "vf_herss": best["vf_herss"],
        "vf_replica": best["vf_replica"],
        "herss_minus_replica": best["vf_herss"] - best["vf_replica"],
        "spread": {
            "min": float(vfs.min()), "max": float(vfs.max()),
            "median": float(np.median(vfs)), "mean": float(vfs.mean()),
            "std": float(vfs.std(ddof=1)), "range_Euro": spread,
            "range_pct_of_best": 100.0 * spread / float(vfs.max()),
            "distribution": [{"seed": r["seed"], "vf_herss": r["vf_herss"],
                              "vf_replica": r["vf_replica"],
                              "converged": r["converged"],
                              "coarse_iterations": r["coarse"]["iterations"],
                              "fine_iterations": r["fine"]["iterations"],
                              "polish_gain": r["polish_gain"],
                              "wall_clock_hours": r["wall_clock_seconds"] / 3600.0,
                              "budget": r["budget"]}
                             for r in sorted(runs, key=lambda x: -x["vf_herss"])],
        },
        "wall_clock_hours_slowest_restart": max(r["wall_clock_seconds"]
                                                for r in runs) / 3600.0,
        "wall_clock_hours_all_parallel": (time.time() - t0) / 3600.0,
        "budget_summed_over_restarts": {
            "n_full_evaluations": sum(r["budget"]["n_full_evaluations"] for r in runs),
            "n_step_cells": sum(r["budget"]["n_step_cells"] for r in runs),
            "seconds": sum(r["budget"]["seconds"] for r in runs)},
        "actions": s.to_dict(np.array(best["M"])),
    }
    print(f"[B4] spread over {len(runs)} restarts: "
          f"min {vfs.min():.2f} max {vfs.max():.2f} "
          f"median {np.median(vfs):.2f} std {vfs.std(ddof=1):.2f}", flush=True)
    print(f"[B4] range {spread:.2f} EUR = "
          f"{100.0 * spread / vfs.max():.4f} % of best", flush=True)
    save(result, path)
    return result


# ------------------------------------------------------------------ B5

def stage_b5(p, s, result, path, time_limit, epsilon, verbose=False):
    M0 = s.to_matrix(result["B4"]["actions"])
    print("[B5] pairwise moves from B4's optimum ...", flush=True)
    t0 = time.time()
    r = BL.b5_from(s, M0, epsilon=epsilon, time_limit=time_limit, verbose=verbose)
    vf_h = herss_vf(p, s, r["M"])
    b4_h = result["B4"]["vf_herss"]
    pairs = BL.upstream_station_pairs(s)
    names = s.sta_names
    result["B5"] = {
        "description": ("coordinate ascent continued from B4's optimum with "
                        "pairwise neighbourhoods (a) same-step, (b) adjacent, "
                        "(c) upstream t with downstream t+1"),
        "started_from": "B4 best restart",
        "vf_replica": float(r["vf"]), "vf_herss": vf_h,
        "herss_minus_replica": vf_h - float(r["vf"]),
        "iterations": r["iterations"], "converged": r["converged"],
        "n_pair_levels": r["n_pair_levels"],
        "budget": r["budget"].as_dict(),
        "wall_clock_hours": (time.time() - t0) / 3600.0,
        "B5_minus_B4_Euro": vf_h - b4_h,
        "B5_minus_B4_pct_of_B4": 100.0 * (vf_h - b4_h) / b4_h,
        "gain_by_kind_replica": r["gain_by_kind"],
        "gain_by_tag_replica": r["gain_by_tag"],
        "cascade_station_pairs": sorted(f"{names[i]}->{names[j]}" for i, j in pairs),
        "note": ("(c) is RESERVOIR MEDIATED at daily resolution, not routing "
                 "delay: the channel impulse response puts 77-96 % of a release "
                 "into the same step"),
        "actions": s.to_dict(r["M"]),
    }
    print(f"[B5] HERSS {vf_h:.4f}  B5 - B4 = {vf_h - b4_h:+.4f} EUR "
          f"({100.0 * (vf_h - b4_h) / b4_h:+.5f} %)", flush=True)
    print(f"[B5] gain by neighbourhood: {r['gain_by_kind']}", flush=True)
    save(result, path)
    return result


# ------------------------------------------------------------------ diagnose

def stage_diagnose(p, s, result, path):
    diag = {}
    for tag in ("B0", "B1", "B2", "B3"):
        if tag in result.get("baselines", {}):
            M = s.to_matrix(result["baselines"][tag]["actions"])
            diag[tag] = DG.summarise(s, tag, M)
    for tag in ("B4", "B5"):
        if tag in result:
            M = s.to_matrix(result[tag]["actions"])
            diag[tag] = DG.summarise(s, tag, M)
            if tag == "B4":
                result["regime_realised"] = DG.realised_regime(s, M)
    result["diagnosis"] = diag

    for tag, d in diag.items():
        tot = sum(v["overflow_Mm3"] for v in d["spill"].values())
        steps = sum(v["overflow_steps"] for v in d["spill"].values())
        print(f"[diag {tag}] spill {tot:.2f} Mm3 over {steps} node-steps, "
              f"terminal share {d['economics']['terminal_share_of_vf']:.3f}",
              flush=True)
    save(result, path)
    return result


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "provenance", "baselines", "b4", "b5",
                             "diagnose"])
    ap.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--time-limit", type=float, default=None,
                    help="seconds per ascent phase; omit for no limit")
    ap.add_argument("--epsilon", type=float, default=0.01)
    ap.add_argument("--out", default=RESULT)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--b4-worker", type=int, default=None)
    ap.add_argument("--b4-out", default=None)
    args = ap.parse_args()

    if args.b4_worker is not None:
        b4_worker(args.b4_worker, args.b4_out, args.time_limit, args.epsilon)
        return 0

    path = os.path.join(HERE, args.out)
    p, plan, s = make_series()
    result = load_result(path)

    stages = (["provenance", "baselines", "b4", "b5", "diagnose"]
              if args.stage == "all" else [args.stage])

    for st in stages:
        if st == "provenance":
            result = stage_provenance(p, s, result, path)
        elif st == "baselines":
            result = stage_baselines(p, s, result, path, args.verbose)
        elif st == "b4":
            result = stage_b4(p, s, result, path, args.seeds, args.time_limit,
                              args.epsilon, args.jobs)
        elif st == "b5":
            result = stage_b5(p, s, result, path, args.time_limit, args.epsilon,
                              args.verbose)
        elif st == "diagnose":
            result = stage_diagnose(p, s, result, path)

    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save(result, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
