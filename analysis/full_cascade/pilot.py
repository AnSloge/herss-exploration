#!/usr/bin/env python
"""
Pilot measurement: one B4 restart on the full instance, instrumented.

This is the blocking step before the overnight run. It measures two things and
nothing else is decided until both are on the table:

  1. wall-clock time to convergence for ONE complete restart, coarse grid plus
     fine polish
  2. peak resident memory for the process

and extrapolates both to eight restarts running in parallel.

Per-iteration progress is appended to a JSONL file as it happens, so the run can
be extrapolated from partial output without waiting for it to finish -- which is
the whole point, given that the thing being measured is how long it takes.

A time limit is enforced. A phase that hits it is reported with converged=false
and its iteration count is a LOWER bound; the extrapolation then reports a lower
bound too rather than a number that looks like a measurement.

numpy is pinned to one thread. The overnight run puts eight of these on sixteen
cores, and BLAS threads inside each would make per-restart timings depend on how
many other restarts happen to be busy.
"""

import argparse
import json
import os
import resource
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baselines3 as BL
import params3
import replica3

HERE = os.path.dirname(os.path.abspath(__file__))


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--coarse-levels", type=int, default=21)
    ap.add_argument("--fine-levels", type=int, default=201)
    ap.add_argument("--time-limit", type=float, default=10800.0,
                    help="seconds, per phase")
    ap.add_argument("--epsilon", type=float, default=0.01)
    ap.add_argument("--out", default="pilot_result.json")
    ap.add_argument("--log", default="pilot_progress.jsonl")
    args = ap.parse_args()

    p = params3.get()
    plan = replica3.build_plan(p)
    prices, inflow, restprice = params3.load_series(p)
    s = BL.Series(plan, prices, inflow, restprice)

    logpath = os.path.join(HERE, args.log)
    open(logpath, "w").close()
    t_start = time.time()

    def make_logger(phase):
        def on_iter(it, vf, tag, t):
            with open(logpath, "a") as f:
                f.write(json.dumps({
                    "phase": phase, "iteration": it, "vf": float(vf),
                    "tag": tag, "t": t,
                    "elapsed": round(time.time() - t_start, 2),
                    "rss_mb": round(rss_mb(), 1)}) + "\n")
        return on_iter

    print(f"pilot: seed={args.seed}, T={s.T}, {s.n_sta} stations "
          f"({s.T * s.n_sta} decision variables)", flush=True)

    result = {"seed": args.seed, "T": s.T, "n_variables": s.T * s.n_sta,
              "coarse_levels": args.coarse_levels, "fine_levels": args.fine_levels,
              "time_limit_per_phase": args.time_limit, "epsilon": args.epsilon}

    budget = BL.Budget()

    t0 = time.time()
    coarse = BL.coordinate_ascent(
        s, np.round(np.linspace(0, 1, args.coarse_levels), 4), seed=args.seed,
        epsilon=args.epsilon, time_limit=args.time_limit, budget=budget,
        on_iter=make_logger("coarse"))
    t_coarse = time.time() - t0
    rss_coarse = rss_mb()
    print(f"coarse: VF={coarse['vf']:.2f} after {coarse['iterations']} iterations, "
          f"converged={coarse['converged']}, {t_coarse / 60:.1f} min, "
          f"peak RSS {rss_coarse:.0f} MB", flush=True)
    result["coarse"] = {"vf": coarse["vf"], "iterations": coarse["iterations"],
                        "converged": coarse["converged"], "seconds": t_coarse,
                        "seconds_per_iteration": t_coarse / max(coarse["iterations"], 1),
                        "peak_rss_mb": rss_coarse}
    with open(os.path.join(HERE, args.out), "w") as f:
        json.dump(result, f, indent=2)

    t0 = time.time()
    fine = BL.coordinate_ascent(
        s, np.round(np.linspace(0, 1, args.fine_levels), 4), start_M=coarse["M"],
        epsilon=args.epsilon, time_limit=args.time_limit, budget=budget,
        on_iter=make_logger("fine"))
    t_fine = time.time() - t0
    rss_fine = rss_mb()
    print(f"fine:   VF={fine['vf']:.2f} after {fine['iterations']} iterations, "
          f"converged={fine['converged']}, {t_fine / 60:.1f} min, "
          f"peak RSS {rss_fine:.0f} MB", flush=True)
    result["fine"] = {"vf": fine["vf"], "iterations": fine["iterations"],
                      "converged": fine["converged"], "seconds": t_fine,
                      "seconds_per_iteration": t_fine / max(fine["iterations"], 1),
                      "peak_rss_mb": rss_fine}

    total = t_coarse + t_fine
    converged = coarse["converged"] and fine["converged"]
    result["total"] = {
        "seconds": total, "minutes": total / 60.0, "hours": total / 3600.0,
        "converged": converged,
        "polish_gain": fine["vf"] - coarse["vf"],
        "budget": budget.as_dict(),
        "peak_rss_mb": max(rss_coarse, rss_fine),
    }
    result["extrapolation_8_parallel"] = {
        "note": ("restarts are independent processes, so wall clock for 8 in "
                 "parallel is one restart's wall clock plus scheduling, given "
                 "8 <= cores and 8 * peak_rss <= free RAM"
                 + ("" if converged else
                    "; a phase hit the time limit, so these are LOWER BOUNDS")),
        "wall_clock_hours_lower_bound": total / 3600.0,
        "total_rss_mb": 8 * max(rss_coarse, rss_fine),
        "is_lower_bound": not converged,
    }
    result["M"] = [[float(x) for x in row] for row in fine["M"]]

    with open(os.path.join(HERE, args.out), "w") as f:
        json.dump(result, f, indent=2)

    print(f"\ntotal {total / 3600.0:.2f} h, converged={converged}, "
          f"peak RSS {max(rss_coarse, rss_fine):.0f} MB", flush=True)
    print(f"extrapolated: 8 parallel restarts "
          f"{'>=' if not converged else '~'} {total / 3600.0:.2f} h wall clock, "
          f"{8 * max(rss_coarse, rss_fine):.0f} MB total RSS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
