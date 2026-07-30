#!/usr/bin/env python
"""
Validate replica.py against the real HERSS simulator (via oracle.py) on
several action sequences for data/mini_utahps_daily, including sequences
designed to trigger the aggressive-action penalty and the HRW overflow.
"""

import random

import numpy as np

import oracle
import replica

DATASET_DIR = oracle.DATASET_DIR


def load_dataset():
    prices = []
    restprice = None
    with open(DATASET_DIR + "pricefile.txt") as f:
        lines = [l.strip() for l in f if l.strip()]
    restprice = float(lines[0].split()[1])
    for line in lines[2:]:
        prices.append(float(line.split()[1]))

    inflows = []
    with open(DATASET_DIR + "inflowseries.txt") as f:
        lines = [l.strip() for l in f if l.strip()]
    for line in lines[1:]:
        inflows.append(float(line.split()[1]))

    reservoir_init_fr = 0.67  # data/mini_utahps_daily/start_state.txt NODE RESERVOIR 0 HJELLE 0.67

    return prices, inflows, restprice, reservoir_init_fr


def compare(name, actions, prices, inflows, restprice, reservoir_init_fr, verbose=True, init_fr_override=None):
    fr = init_fr_override if init_fr_override is not None else reservoir_init_fr
    vf_replica, steps = replica.simulate_sequence(actions, inflows, prices, fr, restprice)
    trace = oracle.evaluate_full_trace(actions, restprice, init_fr_override)
    vf_real = trace["vf"]

    diffs = {
        "vf": vf_replica - vf_real,
        "res_masl_end": steps[-1].end_of_stp_masl - trace["res_masl"][-1],
        "power_MWh_max_abs_diff": max(
            abs(s.power_MWh - p) for s, p in zip(steps, trace["power_MWh"])
        ),
        "income_max_abs_diff": max(
            abs(s.income - i) for s, i in zip(steps, trace["income"])
        ),
        "cost_max_abs_diff": max(
            abs(s.cost - c) for s, c in zip(steps, trace["cost"])
        ),
        "aggressive_cost_sum_replica": sum(s.aggressive_cost for s in steps),
        "aggressive_cost_sum_real": sum(trace["aggressive_cost"]),
        "startstop_cost_sum_replica": sum(s.startstop_cost for s in steps),
        "startstop_cost_sum_real": sum(trace["startstop_cost"]),
    }

    ok = (
        abs(diffs["vf"]) < 0.05
        and diffs["power_MWh_max_abs_diff"] < 0.01
        and diffs["income_max_abs_diff"] < 0.5
        and diffs["cost_max_abs_diff"] < 0.5
    )

    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: VF replica={vf_replica:.4f} real={vf_real:.4f} diff={diffs['vf']:.5f}")
    if verbose or not ok:
        for k, v in diffs.items():
            print(f"    {k}: {v}")
    return ok


def main():
    prices, inflows, restprice, reservoir_init_fr = load_dataset()
    T = len(prices)
    assert T == 30 and len(inflows) == 30

    all_ok = True

    shipped = oracle.load_shipped_actions()
    all_ok &= compare("shipped actions.txt", shipped, prices, inflows, restprice, reservoir_init_fr)

    all_ok &= compare("all-zero (off)", [0.0] * T, prices, inflows, restprice, reservoir_init_fr)

    all_ok &= compare("all-one (max, should trigger aggressive-action penalty)",
                       [1.0] * T, prices, inflows, restprice, reservoir_init_fr)

    all_ok &= compare("half-load constant 0.5", [0.5] * T, prices, inflows, restprice, reservoir_init_fr)

    rng = random.Random(42)
    rand_actions = [rng.random() for _ in range(T)]
    all_ok &= compare("random uniform[0,1] seed=42", rand_actions, prices, inflows, restprice, reservoir_init_fr)

    # Off for first 20 days (should raise reservoir toward/above HRW, hit overflow), then max.
    overflow_test = [0.0] * 20 + [1.0] * 10
    all_ok &= compare("off-then-max (overflow trigger)", overflow_test, prices, inflows, restprice, reservoir_init_fr)

    # Bang-bang on top-price days at full discharge (repeated draws -> likely hits aggressive-action clip)
    top_k_idx = sorted(range(T), key=lambda t: -prices[t])[:15]
    bangbang = [1.0 if t in top_k_idx else 0.0 for t in range(T)]
    all_ok &= compare("bang-bang top-15-price days", bangbang, prices, inflows, restprice, reservoir_init_fr)

    # Force the aggressive-action branch: start nearly empty, run at max discharge.
    # up_res_Mm3 starts at ~0 (fr=0.02 is barely above LRW), so day 0's full-discharge
    # request should exceed available volume and trigger the penalty + flow=0 clip.
    all_ok &= compare("near-empty start + all-max (forces aggressive-action clip)",
                       [1.0] * T, prices, inflows, restprice, reservoir_init_fr,
                       init_fr_override=0.02)

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
