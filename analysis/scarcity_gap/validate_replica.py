#!/usr/bin/env python
"""
Validate replica.py against the real HERSS simulator on the two scarcity-regime
instances. This is a fresh validation, not a reuse of the mini_utahps_daily
one: the operating regime is different and the LRW / aggressive-action branches
are actually reached here.

Nine action sequences per instance -- the eight used on mini_utahps_daily plus
one that drives the reservoir down onto LRW and holds it there.

Also checks baselines._forward_batch (the vectorized B4 candidate sweep)
against the scalar replica, since B4's honesty depends on that batching being
an implementation detail and not a different algorithm.
"""

import json
import sys

import numpy as np

import baselines
import oracle
import replica as R
from params import INSTANCES, load_series

VF_TOL = 0.05


def build_sequences(p, prices, inflows, restprice):
    T = len(prices)
    rng = np.random.default_rng(42)

    # 9: drain onto LRW and stay there. Ask for full discharge every step; once
    # the active volume is gone the aggressive-action branch clips flow to zero,
    # so the reservoir sits pinned at filling_at_lrw_Mm3 for long stretches.
    drain = []
    s = R.initial_res_Mm3(p)
    prev = 0.0
    for t in range(T):
        avail = max(0.0, s + p.m3s_to_Mm3(inflows[t]) - p.filling_at_lrw_Mm3)
        a = min(1.0, p.Mm3_to_m3s(avail) / p.generator_max_discharge)
        a = float(np.floor(a * 1000) / 1000)  # stay just inside the clip
        drain.append(a)
        s = R.step(p, s, prev, a, inflows[t], prices[t]).res_Mm3_next
        prev = a

    top = sorted(range(T), key=lambda t: -prices[t])[:int(T * 0.41)]
    off_days = int(T * 0.55)

    return [
        ("constant 0.5 (shipped actions.txt)", [0.5] * T, None),
        ("all-zero (off)", [0.0] * T, None),
        ("all-one (max, triggers aggressive-action)", [1.0] * T, None),
        ("half-load constant 0.5", [0.5] * T, None),
        ("random uniform[0,1] seed=42", list(rng.uniform(0, 1, T)), None),
        (f"off {off_days} steps then max (overflow trigger)",
         [0.0] * off_days + [1.0] * (T - off_days), None),
        (f"bang-bang top-{len(top)}-price steps",
         [1.0 if t in top else 0.0 for t in range(T)], None),
        ("near-empty start (init_fr=0.02) + all-max", [1.0] * T, 0.02),
        ("drain onto LRW and hold", drain, None),
    ]


def compare(key, p, name, actions, prices, inflows, restprice, init_fr):
    fr = init_fr if init_fr is not None else p.reservoir_init_fr
    vf_replica, steps = R.simulate_sequence(p, actions, inflows, prices, restprice, fr)
    trace = oracle.evaluate_full_trace(key, [float(a) for a in actions], restprice, init_fr)
    vf_real = trace["vf"]

    d = {
        "vf_replica": vf_replica,
        "vf_real": vf_real,
        "vf_diff": vf_replica - vf_real,
        "res_masl_end_diff": steps[-1].end_of_stp_masl - trace["res_masl"][-1],
        "power_MWh_max_abs_diff": max(abs(s.power_MWh - v)
                                      for s, v in zip(steps, trace["power_MWh"])),
        "income_max_abs_diff": max(abs(s.income - v)
                                   for s, v in zip(steps, trace["income"])),
        "cost_max_abs_diff": max(abs(s.cost - s.res_cost_lrw - v)
                                 for s, v in zip(steps, trace["cost"])),
        "aggressive_sum_replica": sum(s.aggressive_cost for s in steps),
        "aggressive_sum_real": sum(trace["aggressive_cost"]),
        "startstop_sum_replica": sum(s.startstop_cost for s in steps),
        "startstop_sum_real": sum(trace["startstop_cost"]),
        "lrw_sum_replica": sum(s.res_cost_lrw for s in steps),
        "lrw_sum_real": sum(trace["res_cost_lrw"]),
        "overflow_sum_replica_Mm3": sum(s.overflow_Mm3 for s in steps),
        "min_res_Mm3": min(s.res_Mm3_next for s in steps),
    }
    ok = (abs(d["vf_diff"]) < VF_TOL
          and d["power_MWh_max_abs_diff"] < 0.01
          and d["income_max_abs_diff"] < 0.5
          and d["cost_max_abs_diff"] < 0.5)
    d["pass"] = bool(ok)
    d["name"] = name
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"        VF replica={vf_replica:.4f} real={vf_real:.4f} diff={d['vf_diff']:+.6f}")
    print(f"        max|dPower|={d['power_MWh_max_abs_diff']:.2e} "
          f"max|dIncome|={d['income_max_abs_diff']:.2e} "
          f"max|dCost|={d['cost_max_abs_diff']:.2e}")
    print(f"        aggressive {d['aggressive_sum_replica']:.2f}/{d['aggressive_sum_real']:.2f}  "
          f"startstop {d['startstop_sum_replica']:.2f}/{d['startstop_sum_real']:.2f}  "
          f"lrw {d['lrw_sum_replica']:.2f}/{d['lrw_sum_real']:.2f}  "
          f"overflow {d['overflow_sum_replica_Mm3']:.3f} Mm3")
    return d


def check_forward_batch(p, prices, inflows, restprice, seed=7):
    """baselines._forward_batch must equal the scalar path exactly."""
    rng = np.random.default_rng(seed)
    T = len(prices)
    base = list(rng.uniform(0, 1, T))
    level = 0.63
    fast = baselines._forward_batch(p, base, inflows, prices, restprice, level)
    worst = 0.0
    for t in rng.choice(T, size=12, replace=False):
        alt = list(base)
        alt[int(t)] = level
        ref = R.simulate_sequence(p, alt, inflows, prices, restprice)[0]
        worst = max(worst, abs(ref - fast[int(t)]))
    return worst


def main():
    keys = sys.argv[1:] or ["hjelle", "gresse"]
    version, version_date = oracle.version_info()
    print(f"HERSS VERSION {version} / VERSION_DATE {version_date}\n")

    all_ok = True
    report = {}
    for key in keys:
        p = INSTANCES[key]
        prices, inflows, restprice = load_series(p)
        print(f"=== {p.name}  T={len(prices)}  restprice={restprice}  "
              f"init_fr={p.reservoir_init_fr} ===")

        wb = check_forward_batch(p, prices, inflows, restprice)
        print(f"  [{'PASS' if wb < 1e-9 else 'FAIL'}] _forward_batch vs scalar replica: "
              f"max abs diff {wb:.3e}")
        all_ok &= wb < 1e-9

        rows = []
        for name, actions, init_fr in build_sequences(p, prices, inflows, restprice):
            d = compare(key, p, name, actions, prices, inflows, restprice, init_fr)
            rows.append(d)
            all_ok &= d["pass"]
        report[key] = {"forward_batch_max_diff": float(wb), "sequences": rows}
        print()

    with open("validation_replica.json", "w") as f:
        json.dump(report, f, indent=2)
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
