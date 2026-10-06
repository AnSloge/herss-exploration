"""Refine the verbatim-input case (fabel_base, dataset inflow) near the L=HRW, U=LRW corner,
and inspect the aggressive-action flags seen at U=LRW with zero inflow."""
import json, numpy as np, cppyy
from harness import Model, vr, HEIMFOSS
cppyy.cppdef(r"""namespace vr2 {
// Re-evaluates, in C++ double arithmetic, the comparison at powerstation.cpp:805 for t=0 at U=LRW:
// up_res = (filling_at_lrw + pumped) - filling_at_lrw  (reservoir.cpp:531, after pump.cpp:239)
double excess(Herss* h, int res_node, double pumped_Mm3, double flow_m3s, double dt) {
    Reservoir& r = h->rs->reservoirs[h->rs->nodes[res_node]->reservoir_idnr];
    double res = r.filling_at_lrw_Mm3; res += pumped_Mm3;
    double up = std::max(0.0, res - r.filling_at_lrw_Mm3);
    double Q_Mm3 = MACRO_m3s_2_Mm3(flow_m3s, dt);
    return Q_Mm3 - up; } }""")
vr2 = cppyy.gbl.vr2
out = {}
m = Model("fabel_base", logname="herss_refine_base.log")
m.zero_all_other_actions()
best = None
for fu in np.round(np.arange(0.0, 0.1001, 0.01), 10):
    for fl in np.round(np.arange(0.90, 1.0001, 0.002), 10):
        m.set_levels(fu, fl)
        for a in np.round(np.arange(0.45, 0.5501, 0.005), 10):
            m.set_loop_actions([a, 0.0], [a, 0.0])
            w = m.run(); r = m.read()
            ok = (w == 0 and r["aggr_0"] == 0 and r["U_overflow_0"] == 0 and r["L_overflow_0"] == 0
                  and r["U_overflow_1"] == 0 and r["L_overflow_1"] == 0
                  and abs(r["pumped_m3s_0"] - r["turb_m3s_0"]) < 1e-9 * r["pumped_m3s_0"])
            if ok and (best is None or r["eta_rt"] > best["eta_rt"]):
                best = dict(r, a=float(a), fr_up=float(fu), fr_low=float(fl))
keep = ["a","fr_up","fr_low","U0","L0","eta_rt","E_in","E_out","Hb_p_0","Hn_p_0","Hb_s_0","Hn_s_0",
        "L_end_0","U_end_0","L_upinflow_0","L_inflow_0","U_inflow_0","U_autoqmin_0"]
out["refine_base_A"] = {k: best[k] for k in keep}

# aggressive-action flags: clean, zero inflow, U at LRW
m2 = Model("fabel_clean", logname="herss_aggr.log")
m2.zero_all_other_actions(); m2.zero_inflow()
cases = []
for a in np.round(np.arange(0.05, 1.0001, 0.05), 10):
    m2.set_levels(0.0, 0.5)
    m2.set_loop_actions([a, 0.0], [a, 0.0])
    m2.run(); r = m2.read()
    q_Mm3 = r["turb_m3s_0"]  # 0 if overridden
    req_Mm3 = 15 * a * 3600 / 1e6
    cases.append({"a": float(a), "aggr_cost": r["aggr_0"], "turb_m3s": r["turb_m3s_0"],
                  "pumped_Mm3": r["pumped_Mm3_0"], "requested_Mm3": req_Mm3,
                  "Q_minus_upres_recomputed": float(vr2.excess(m2.h, 10, r["pumped_Mm3_0"], 15 * a, 3600.0)),
                  "req_minus_pumped": req_Mm3 - r["pumped_Mm3_0"]})
out["aggr_at_LRW"] = cases
json.dump(out, open("results/refine_base.json", "w"), indent=1)
print(json.dumps(out["refine_base_A"], indent=1))
for c in cases: print(c)
