#!/usr/bin/env python
"""
Tuned price-threshold baseline for mini_utahps_daily (report section 11.6,
baseline #1: "produce at the efficiency-optimal point when p_t*e_n exceeds
the opportunity cost of water, store otherwise").

Policy family: a_t = L if day t is among the K highest-price days, else 0.
This is exactly a price threshold (tau = the K-th highest price) with a
single production level L. Both K (0..T) and L (discharge fraction) are
swept exhaustively and evaluated through replica.py -- i.e. through the
same exact transition function validated against real HERSS in validate.py.
No feasibility repair is applied: if a candidate (K, L) asks for more water
than is available on a given day, the aggressive-action penalty fires
exactly as it would in HERSS, and that candidate's VF reflects the penalty.
"""

import numpy as np

import replica as R
import validate as V_


def bangbang_actions(prices, K, L):
    T = len(prices)
    order = sorted(range(T), key=lambda t: -prices[t])
    on_days = set(order[:K])
    return [L if t in on_days else 0.0 for t in range(T)]


def tune_threshold(prices, inflows, restprice, reservoir_init_fr,
                    K_range=None, L_range=None):
    T = len(prices)
    if K_range is None:
        K_range = range(0, T + 1)
    if L_range is None:
        L_range = np.round(np.arange(0.01, 1.0001, 0.01), 2)

    best = None
    results = []
    for K in K_range:
        for L in L_range:
            actions = bangbang_actions(prices, K, L)
            vf, _ = R.simulate_sequence(actions, inflows, prices, reservoir_init_fr, restprice)
            results.append((K, L, vf))
            if best is None or vf > best[2]:
                best = (K, L, vf)

    return best, results


if __name__ == "__main__":
    prices, inflows, restprice, reservoir_init_fr = V_.load_dataset()

    best, results = tune_threshold(prices, inflows, restprice, reservoir_init_fr)
    K, L, vf = best
    print(f"Best threshold policy: K={K} highest-price days on, L={L} discharge fraction")
    print(f"VF (replica) = {vf:.4f}")

    actions = bangbang_actions(prices, K, L)
    print("actions:", actions)

    # Also report the best pure bang-bang (L=1.0) for comparison, since that's
    # the simplest reading of "produce at max when price clears the threshold".
    best_L1 = max((r for r in results if r[1] == 1.0), key=lambda r: r[2])
    print(f"Best pure bang-bang (L=1.0): K={best_L1[0]}, VF={best_L1[2]:.4f}")
