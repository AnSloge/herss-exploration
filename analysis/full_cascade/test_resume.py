#!/usr/bin/env python
"""
Equivalence test for the resume machinery in baselines3.

resume_batch is the only reason the coordinate ascent is affordable: instead of
replaying 365 steps per candidate it restarts from the perturbed step using the
incumbent's cached state. That is a pure optimisation and must be EXACTLY
equivalent to a full replay -- if it is not, the search is hill-climbing on a
function that is not the simulator, and every number downstream is wrong in a way
no VF comparison against HERSS would reveal, because the winner is always
re-evaluated in full.

Three checks, on the real 365-step instance:

  1. An all-NaN override reproduces the incumbent's own value exactly.
  2. Single-variable overrides at scattered (t, station) reproduce full_vf of the
     correspondingly edited action matrix.
  3. Two-step overrides (the (b) and (c) neighbourhood shape) do the same.

Bit-identity is required, not tolerance: both paths run the same replica3.step on
the same inputs in the same order, so any difference is a bookkeeping error.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import baselines3 as BL
import params3
import replica3


def main():
    p = params3.get()
    plan = replica3.build_plan(p)
    prices, inflow, restprice = params3.load_series(p)
    s = BL.Series(plan, prices, inflow, restprice)

    rng = np.random.default_rng(7)
    M = rng.uniform(0.0, 1.0, (s.T, s.n_sta))
    inc = BL.Incumbent(s, M)

    vf_direct = BL.full_vf(s, M)
    print(f"incumbent: full_vf {vf_direct:.6f}  Incumbent.vf {inc.vf:.6f}  "
          f"diff {inc.vf - vf_direct:+.3e}")
    assert inc.vf == vf_direct, "Incumbent prefix disagrees with a full replay"

    # ---- 1 no-op overrides ------------------------------------------------
    ts = np.array(sorted(rng.choice(s.T, size=40, replace=False)))
    over = np.full((len(ts), 1, s.n_sta), np.nan)
    vals, _ = BL.resume_batch(s, inc, ts, over)
    worst = float(np.abs(vals - vf_direct).max())
    print(f"[1] all-NaN overrides at 40 steps: max |resume - incumbent| = {worst:.3e}")
    assert worst == 0.0, "a no-op override changed the value"

    # ---- 2 single-variable overrides --------------------------------------
    cases = []
    for t in ts[:20]:
        for k in range(s.n_sta):
            cases.append((int(t), k, float(rng.uniform())))
    cases.sort()
    start = np.array([c[0] for c in cases])
    over = np.full((len(cases), 1, s.n_sta), np.nan)
    for i, (t, k, v) in enumerate(cases):
        over[i, 0, k] = v
    vals, _ = BL.resume_batch(s, inc, start, over)

    worst, worst_case = 0.0, None
    for i, (t, k, v) in enumerate(cases):
        M2 = M.copy()
        M2[t, k] = v
        ref = BL.full_vf(s, M2)
        d = abs(float(vals[i]) - ref)
        if d > worst:
            worst, worst_case = d, (t, k, v, float(vals[i]), ref)
    print(f"[2] {len(cases)} single-variable moves: max |resume - full replay| "
          f"= {worst:.3e}")
    assert worst == 0.0, f"single-variable resume mismatch at {worst_case}"

    # ---- 3 two-step overrides ---------------------------------------------
    cases = []
    for t in ts[:15]:
        t = int(min(t, s.T - 2))
        i, j = int(rng.integers(s.n_sta)), int(rng.integers(s.n_sta))
        cases.append((t, i, j, float(rng.uniform()), float(rng.uniform())))
    cases.sort()
    start = np.array([c[0] for c in cases])
    over = np.full((len(cases), 2, s.n_sta), np.nan)
    for n, (t, i, j, a, b) in enumerate(cases):
        over[n, 0, i] = a
        over[n, 1, j] = b
    vals, _ = BL.resume_batch(s, inc, start, over)

    worst, worst_case = 0.0, None
    for n, (t, i, j, a, b) in enumerate(cases):
        M2 = M.copy()
        M2[t, i] = a
        M2[t + 1, j] = b
        ref = BL.full_vf(s, M2)
        d = abs(float(vals[n]) - ref)
        if d > worst:
            worst, worst_case = d, (t, i, j, float(vals[n]), ref)
    print(f"[3] {len(cases)} two-step moves: max |resume - full replay| = {worst:.3e}")
    assert worst == 0.0, f"two-step resume mismatch at {worst_case}"

    print("\nOK: resume_batch is bit-identical to a full replay.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
