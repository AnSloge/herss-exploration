"""C5 part 1, Part C follow-up: are the few cells with gross-head ratio > 1
caused by natural inflow into U between the pump step and the turbine step?
Re-run exactly those cells with U's inflow set to 0 at t = 0 and t = 1."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "r1_loop"))
import r1_sweep as S
from pump_oracle import PumpInstance

res = json.load(open(os.path.join(HERE, "r1_sweep_results.json")))
out = {}
for name in ["c5_high", "c5_headkeep"]:
    over = [r for r in res["variants"][name]["rows"]
            if r["status"] == "ok" and r["gross_head_ratio"] > 1]
    inst = PumpInstance(os.path.join(HERE, name), logfile=os.path.join(HERE, "c5_inflow_check.log"))
    inst.diagnose()
    trips = []
    q0 = [inst.inflow(S.U, t) for t in (0, 1)]
    for t in (0, 1):
        inst.h.SetInflowInNode(t, S.U, 0.0)
    rows = []
    for r in over:
        x = S.cell(inst, r["a_pump"], r["U_fr"], r["L_fr"])
        if x["status"] != "ok" and x.get("aggressive_cost", 0) > 0:
            # U at exactly LRW + lift: rounding overdraw ~1e-14 Mm3 trips the
            # aggressive-action branch and zeroes the release. Record, then
            # retry releasing (1 - 1e-9) of the lift (within the 1e-6 match).
            trips.append(dict(a_pump=r["a_pump"], U_fr=r["U_fr"], L_fr=r["L_fr"],
                              overdraw_cost_EUR=x["aggressive_cost"],
                              up_Mm3=x["up_Mm3"], dn_Mm3=x["dn_Mm3"]))
            x = S.cell(inst, r["a_pump"], r["U_fr"], r["L_fr"], gen_shrink=1e-9)
        rows.append(x)
    out[name] = dict(n_cells=len(over), U_inflow_m3s_t0_t1=q0,
                     max_ratio_with_inflow=max(r["gross_head_ratio"] for r in over),
                     max_ratio_inflow_zeroed=max(r["gross_head_ratio"] for r in rows),
                     all_statuses_ok=all(r["status"] == "ok" for r in rows),
                     aggressive_trips=trips)
    print(name, out[name])
json.dump(out, open(os.path.join(HERE, "inflow_check_results.json"), "w"), indent=1)
