#!/usr/bin/env python
"""
Regression guard: the parameterised replica/DP in this directory must reproduce
the mini_utahps_daily numbers from the 2026-07-30 measurement
(analysis/mini_utahps_daily_dp/result.json) to relative 1e-6.

This is the proof that moving the instance constants into params.InstanceParams
changed no formula. It fails hard -- there is no "close enough" judgement call.

Reference values, analysis/mini_utahps_daily_dp/result.json:
    DP-optimal VF (replica)     93826.70808000385
    tuned threshold VF (replica) 93559.03201803775
"""

import sys

import numpy as np

import baselines
import dp
import replica as R
from params import INSTANCES, load_series

REF_DP_VF = 93826.70808000385
REF_THRESHOLD_VF = 93559.03201803775
REF_THRESHOLD_K = 29
REF_THRESHOLD_L = 0.99
RTOL = 1e-6


def check(label, got, ref, rtol=RTOL):
    rel = abs(got - ref) / abs(ref)
    ok = rel <= rtol
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got:.8f} ref {ref:.8f} rel {rel:.3e}")
    return ok


def main():
    p = INSTANCES["mini"]
    prices, inflows, restprice = load_series(p)
    assert len(prices) == 30, f"mini_utahps_daily should have T=30, got {len(prices)}"
    print(f"Regression against mini_utahps_daily (T={len(prices)}, restprice={restprice}, "
          f"init_fr={p.reservoir_init_fr}), rtol={RTOL:g}")

    ok = True

    worst = dp.check_against_replica(p, prices, inflows, restprice)
    print(f"  [{'PASS' if worst < 1e-9 else 'FAIL'}] dp.transition_block vs replica.step: "
          f"max abs diff {worst:.3e}")
    ok &= worst < 1e-9

    # The original run used a fixed grid [0, 25] x 4001. Reproduce it exactly
    # rather than the derived grid, so this compares like with like.
    state_grid = np.linspace(0.0, 25.0, 4001)
    V = dp.backward_induction(p, prices, inflows, restprice, state_grid,
                              np.linspace(0.0, 1.0, 201))
    actions, _ = dp.forward_rollout(p, V, prices, inflows, restprice, state_grid,
                                    np.linspace(0.0, 1.0, 2001))
    vf_dp, _ = R.simulate_sequence(p, actions, inflows, prices, restprice)
    ok &= check("DP-optimal VF", vf_dp, REF_DP_VF)

    (K, L, vf_thr), _ = baselines.b2_threshold_level(p, prices, inflows, restprice)
    ok &= check("tuned threshold VF", vf_thr, REF_THRESHOLD_VF)
    k_ok = (K == REF_THRESHOLD_K and abs(L - REF_THRESHOLD_L) < 1e-9)
    print(f"  [{'PASS' if k_ok else 'FAIL'}] threshold argmax: got K={K}, L={L} "
          f"ref K={REF_THRESHOLD_K}, L={REF_THRESHOLD_L}")
    ok &= k_ok

    print("ALL PASS" if ok else "REGRESSION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
