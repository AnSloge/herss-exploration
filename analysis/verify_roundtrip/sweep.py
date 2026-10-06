"""
Round-trip sweep. Usage: python sweep.py <dataset_dir> <tag> [--zero-inflow]

Protocol A: t=0 pump at a, all 3 HEIMFOSS generators at a  (Q_turb == Q_pump, same step);
            t=1 everything off.  Net volume moved by the loop = 0.
Protocol B: t=0 pump at a, station off; t=1 pump off, generators at pumped_m3s[0]/15
            (two-pass: uses HERSS's *actual* pumped volume, not the requested one).
"""
import csv
import json
import sys
import time
import numpy as np
from harness import Model, PUMP, clamp

DS, TAG = sys.argv[1], sys.argv[2]
ZERO_INFLOW = "--zero-inflow" in sys.argv

A_GRID = np.round(np.arange(0.05, 1.0001, 0.05), 10)
FR_UP = np.round(np.linspace(0.0, 0.95, 20), 10)
FR_LOW = np.round(np.linspace(0.0, 1.0, 21), 10)
QMAX_PUMP = 15.0
QMAX_STATION = 15.0   # 3 x 5.0

m = Model(DS, logname=f"herss_{TAG}.log")
m.zero_all_other_actions()
if ZERO_INFLOW:
    m.zero_inflow()


def run_checked():
    w = m.run()
    r = m.read()
    w2 = m.run()
    r2 = m.read()
    r["deterministic"] = int(r == r2 and w == w2)
    r["warnings"] = w
    return r


def flags(r, a, proto):
    T = m.T
    req = a * QMAX_PUMP
    if proto == "A":
        vmatch = abs(r["pumped_m3s_0"] - r["turb_m3s_0"]) / r["pumped_m3s_0"]
    else:
        vmatch = abs(r["pumped_m3s_0"] - r["turb_m3s_1"]) / r["pumped_m3s_0"]
    r["vol_rel_mismatch"] = vmatch
    r["inlet_clip_rel"] = abs(r["pumped_m3s_0"] - req) / req
    r["overflow_any"] = int(any(r[f"{x}_overflow_{t}"] > 0 for x in "UL" for t in range(T)))
    r["aggr_any"] = int(any(r[f"aggr_{t}"] != 0 for t in range(T)))
    r["valid"] = int(vmatch < 1e-9 and r["inlet_clip_rel"] < 1e-9 and not r["overflow_any"]
                     and not r["aggr_any"] and r["warnings"] == 0 and r["deterministic"])
    return r


rows = []
t0 = time.time()
for proto in ("A", "B"):
    for fu in FR_UP:
        for fl in FR_LOW:
            m.set_levels(fu, fl)
            for a in A_GRID:
                if proto == "A":
                    m.set_loop_actions([a, 0.0], [a, 0.0])
                    r = run_checked()
                else:
                    m.set_loop_actions([a, 0.0], [0.0, 0.0])
                    r1 = m.run(); p1 = m.read()
                    g = clamp(p1["pumped_m3s_0"] / QMAX_STATION)
                    m.set_loop_actions([a, 0.0], [0.0, g])
                    r = run_checked()
                    r["gen_action_1"] = g
                r.update(proto=proto, a=float(a), fr_up=float(fu), fr_low=float(fl))
                rows.append(flags(r, float(a), proto))
elapsed = time.time() - t0

keys = sorted({k for r in rows for k in r})
lead = ["proto", "a", "fr_up", "fr_low", "U0", "L0", "eta_rt", "E_in", "E_out", "valid"]
keys = lead + [k for k in keys if k not in lead]
with open(f"results/sweep_{TAG}.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)

summary = {"dataset": DS, "tag": TAG, "zero_inflow": ZERO_INFLOW, "cells": len(rows),
           "elapsed_s": elapsed, "diag": m.diag_rc,
           "grid": {"a": A_GRID.tolist(), "fr_up": FR_UP.tolist(), "fr_low": FR_LOW.tolist()}}
for proto in ("A", "B"):
    P = [r for r in rows if r["proto"] == proto]
    V = [r for r in P if r["valid"]]
    best = max(V, key=lambda r: r["eta_rt"])
    summary[proto] = {
        "cells": len(P), "valid": len(V),
        "invalid_reasons": {
            "overflow": sum(r["overflow_any"] for r in P),
            "aggr": sum(r["aggr_any"] for r in P),
            "warnings": sum(r["warnings"] > 0 for r in P),
            "nondeterministic": sum(1 - r["deterministic"] for r in P),
            "vol_mismatch": sum(r["vol_rel_mismatch"] >= 1e-9 for r in P),
            "inlet_clip": sum(r["inlet_clip_rel"] >= 1e-9 for r in P)},
        "n_eta_gt_1_valid": sum(r["eta_rt"] > 1.0 for r in V),
        "max_vol_rel_mismatch_valid": max(r["vol_rel_mismatch"] for r in V),
        "best": {k: best[k] for k in keys if k in best},
    }
json.dump(summary, open(f"results/summary_{TAG}.json", "w"), indent=1)
for proto in ("A", "B"):
    s = summary[proto]; b = s["best"]
    print(f"[{TAG}] {proto}: valid {s['valid']}/{s['cells']}  eta>1: {s['n_eta_gt_1_valid']}  "
          f"max eta {b['eta_rt']:.6f} at a={b['a']} fr_up={b['fr_up']} fr_low={b['fr_low']} "
          f"U0={b['U0']:.3f} L0={b['L0']:.3f}  Ein={b['E_in']:.6f} Eout={b['E_out']:.6f}  "
          f"reasons={s['invalid_reasons']}")
print(f"elapsed {elapsed:.1f}s")
