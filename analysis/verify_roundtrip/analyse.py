"""
Post-processing + refinement.
1. Component efficiency product from the topology curves (topology.txt:23-34 pump, :260-271 turbine).
2. Check eta_rt == eta_prod(a) * Hn_s/Hn_p on every valid protocol-A cell (decomposition).
3. List eta>1 cells, interior vs edge.
4. Refine around the maximum (a step 0.005, level fractions step 0.01) on fabel_clean, zero inflow.
"""
import csv
import json
import numpy as np
from harness import Model

PUMP_CURVE = [0, 40, 65, 80, 88, 92, 92, 90, 87, 83, 78]
TURB_CURVE = [0.0, 50.0, 75.0, 86.0, 90.0, 92.0, 91.5, 90.0, 88.0, 85.0, 82.0]
MOTOR, GEN = 0.97, 0.96


def interp(curve, qn):
    i = min(int(qn * 10), 9)
    t = qn * 10 - i
    return (curve[i] + t * (curve[i + 1] - curve[i])) / 100.0


def eta_prod(a):
    return interp(TURB_CURVE, a) * GEN * interp(PUMP_CURVE, a) * MOTOR


out = {}
out["eta_prod"] = {f"{a:.2f}": eta_prod(a) for a in np.arange(0.05, 1.0001, 0.05)}

for tag in ("base", "clean_noinflow", "datum221", "base_noinflow", "clean"):
    R = [r for r in csv.DictReader(open(f"results/sweep_{tag}.csv"))]
    VA = [r for r in R if r["valid"] == "1" and r["proto"] == "A"]
    dev = max(abs(float(r["eta_rt"]) - eta_prod(float(r["a"])) * float(r["Hn_s_0"]) / float(r["Hn_p_0"]))
              for r in VA)
    over = [r for r in R if r["valid"] == "1" and float(r["eta_rt"]) > 1.0]
    interior = [r for r in over if 0.0 < float(r["fr_up"]) and float(r["fr_low"]) < 1.0]
    above_prod = sum(float(r["eta_rt"]) > eta_prod(float(r["a"])) for r in R if r["valid"] == "1")
    out[tag] = {
        "decomposition_max_abs_dev_protoA": dev,
        "n_valid": sum(r["valid"] == "1" for r in R),
        "n_eta_gt_1": len(over),
        "n_eta_gt_1_interior": len(interior),
        "n_eta_gt_eta_prod": above_prod,
        "eta_gt_1_cells": [(r["proto"], float(r["a"]), float(r["fr_up"]), float(r["fr_low"]),
                            round(float(r["U0"]), 3), round(float(r["L0"]), 3), float(r["eta_rt"]))
                           for r in sorted(over, key=lambda r: -float(r["eta_rt"]))],
    }

# ---- refinement on clean, zero inflow, protocol A --------------------------------
m = Model("fabel_clean", logname="herss_refine.log")
m.zero_all_other_actions()
m.zero_inflow()
best = None
n_valid = 0
rows = []
for fu in np.round(np.arange(0.0, 0.2001, 0.01), 10):
    for fl in np.round(np.arange(0.80, 1.0001, 0.01), 10):
        m.set_levels(fu, fl)
        for a in np.round(np.arange(0.40, 0.6001, 0.005), 10):
            m.set_loop_actions([a, 0.0], [a, 0.0])
            w = m.run()
            r = m.read()
            ok = (w == 0 and abs(r["pumped_m3s_0"] - r["turb_m3s_0"]) < 1e-9 * r["pumped_m3s_0"]
                  and r["aggr_0"] == 0 and r["U_overflow_0"] == 0 and r["L_overflow_0"] == 0
                  and abs(r["pumped_m3s_0"] - 15 * a) < 1e-9)
            rows.append((float(a), float(fu), float(fl), r["eta_rt"], int(ok)))
            if ok:
                n_valid += 1
                if best is None or r["eta_rt"] > best["eta_rt"]:
                    best = dict(r, a=float(a), fr_up=float(fu), fr_low=float(fl))
with open("results/refine_clean_noinflow_A.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["a", "fr_up", "fr_low", "eta_rt", "valid"])
    w.writerows(rows)
keep = ["a", "fr_up", "fr_low", "U0", "L0", "eta_rt", "E_in", "E_out", "pumped_m3s_0", "turb_m3s_0",
        "Hb_p_0", "Hn_p_0", "Hb_s_0", "Hn_s_0", "U_end_0", "L_end_0"]
out["refine_clean_noinflow_A"] = {"n_cells": len(rows), "n_valid": n_valid,
                                  "n_gt_1": sum(1 for x in rows if x[4] and x[3] > 1),
                                  "best": {k: best[k] for k in keep}}
# best interior refinement cell (strictly inside the box, >= 1 grid step from each level edge)
inner = [x for x in rows if x[4] and 0 < x[1] and x[2] < 1.0]
bi = max(inner, key=lambda x: x[3])
out["refine_clean_noinflow_A"]["best_interior"] = bi
# eta along the a-axis at the best level corner
out["refine_clean_noinflow_A"]["a_profile_at_best_levels"] = [
    (x[0], x[3]) for x in rows if x[1] == best["fr_up"] and x[2] == best["fr_low"] and x[4]]

json.dump(out, open("results/analysis.json", "w"), indent=1)
print(json.dumps({k: (v if k in ("eta_prod",) else {kk: vv for kk, vv in v.items() if kk != "eta_gt_1_cells" and kk != "a_profile_at_best_levels"})
                  for k, v in out.items()}, indent=1))
for tag in ("base", "clean_noinflow"):
    print(tag, out[tag]["eta_gt_1_cells"])
