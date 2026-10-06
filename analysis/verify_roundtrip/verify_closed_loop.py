"""
Is the measured loop actually closed? Verified from runtime state only, not from topology.txt.

T1  Runtime wiring: the pointers HERSS actually uses after loading (pump source/target,
    SKYFONNA tunnel -> which node, HEIMFOSS downstream -> which node).
T2  Per-reservoir, per-step water balance from HERSS's own arrays; every in/out term listed.
T3  Closure: reservoir volumes at the end of the cycle vs the start (both protocols).
T4  Causal knock-out: none / pump only / station only / both. Volume changes must be
    +V/-V, -V/+V and 0/0, i.e. the pump moves water L->U and the station moves it U->L.
T5  Head provenance: pump Hbrutto and station Hbrutto re-derived from the reservoir level
    arrays of nodes 10 and 14 (to show which water surfaces the heads actually used).
"""
import json
import cppyy
from harness import Model, vr, PUMP, SKYFONNA, HEIMFOSS, TROLLDAMMEN, RESERVOIRS

cppyy.cppdef(r"""
namespace vcl {
int idnr_of(Node* n) { return n == nullptr ? -1 : int(n->idnr); }
int pump_src(Herss* h, int p) { return idnr_of(static_cast<Pump*>(h->rs->nodes[p])->ptr_pump_source); }
int pump_tgt(Herss* h, int p) { return idnr_of(static_cast<Pump*>(h->rs->nodes[p])->ptr_pump_target); }
int tunnel_to(Herss* h, int r)   { return idnr_of(h->rs->nodes[r]->ptr_downstream_node_tunnel); }
int hatch_to(Herss* h, int r)    { return idnr_of(h->rs->nodes[r]->ptr_downstream_node_hatch); }
int overflow_to(Herss* h, int r) { return idnr_of(h->rs->nodes[r]->ptr_downstream_node_overflow); }
int autoq_to(Herss* h, int r)    { return idnr_of(h->rs->nodes[r]->ptr_downstream_node_auto_qmin); }
int down_of(Herss* h, int n)     { return idnr_of(h->rs->nodes[n]->ptr_downstream_node); }
bool tunnel_on(Herss* h, int r)  { return h->rs->nodes[r]->outlet_tunnel_in_use; }
bool hatch_on(Herss* h, int r)   { return h->rs->nodes[r]->outlet_hatch_in_use; }
bool autoq_on(Herss* h, int r)   { return h->rs->nodes[r]->outlet_auto_qmin_in_use; }
int nr_nodes(Herss* h) { return int(h->gc->nr_nodes); }
int node_at(Herss* h, int i) { return int(h->rs->nodes[i]->idnr); }
std::string type_of(Herss* h, int i) { return EnumToString(h->rs->nodes[i]->nodetype); }
double sdt(Herss* h, int n) { return h->rs->nodes[n]->S->dt; }
int gdt(Herss* h, int t) { return h->getDeltaT(t); }
}
""")
v = cppyy.gbl.vcl
M3 = lambda q: q * 3600 / 1e6       # m3/s over one hourly step -> Mm3 (dt = 3600 verified below)

out = {}

# ------------------------------------------------------------------ T1 wiring
m = Model("fabel_clean", logname="herss_closed_loop.log")
h = m.h
# Herss::dt is an unused member (9999999); the step length HERSS uses is getDeltaT / S->dt
m.run()
out["dt_s"] = [int(v.gdt(h, t)) for t in range(m.T)] + [float(v.sdt(h, n)) for n in (PUMP, SKYFONNA, HEIMFOSS, TROLLDAMMEN)]
assert all(x == 3600 for x in out["dt_s"]), out["dt_s"]
wiring = {
    "pump0_source": v.pump_src(h, PUMP), "pump0_target": v.pump_tgt(h, PUMP),
    "SKYFONNA_tunnel_in_use": bool(v.tunnel_on(h, SKYFONNA)), "SKYFONNA_tunnel_to": v.tunnel_to(h, SKYFONNA),
    "HEIMFOSS_downstream": v.down_of(h, HEIMFOSS),
    "nodes_in_sim_order": [(v.node_at(h, i), str(v.type_of(h, i))) for i in range(v.nr_nodes(h))],
    # every node whose runtime outlet points into SKYFONNA or TROLLDAMMEN
    "feeds_SKYFONNA": [], "feeds_TROLLDAMMEN": [],
}
for i in range(v.nr_nodes(h)):
    n = v.node_at(h, i)
    outs = {"down": v.down_of(h, n)}
    if str(v.type_of(h, i)) == "RESERVOIR":
        outs.update(tunnel=v.tunnel_to(h, n) if v.tunnel_on(h, n) else -1,
                    hatch=v.hatch_to(h, n) if v.hatch_on(h, n) else -1,
                    overflow=v.overflow_to(h, n),
                    autoq=v.autoq_to(h, n) if v.autoq_on(h, n) else -1)
    for k, tgt in outs.items():
        if tgt == SKYFONNA: wiring["feeds_SKYFONNA"].append((n, k))
        if tgt == TROLLDAMMEN: wiring["feeds_TROLLDAMMEN"].append((n, k))
out["T1_wiring"] = wiring

# ------------------------------------------------------------------ helpers
def fields(r, t):
    f = lambda n, k: float(vr.sc(h, n, k, t))
    d = {}
    for n, tag in ((SKYFONNA, "U"), (TROLLDAMMEN, "L")):
        d[tag] = {k: f(n, k) for k in ("inflow", "up_inflow", "pump_in_m3s", "pump_out_m3s", "tunnelflow_m3s",
                                        "hatchflow_m3s", "overflow_m3s", "auto_qmin_m3s", "res_Mm3", "res_masl")}
    d["pump_m3s"] = f(PUMP, "tot_outflow")
    d["station_m3s"] = f(HEIMFOSS, "tot_outflow")
    d["station_up_inflow"] = f(HEIMFOSS, "up_inflow")
    return d

def balance(start_Mm3, d):
    """Residual of V_end - V_start - (all inflows - all outflows), Mm3."""
    ins = d["inflow"] + d["up_inflow"] + d["pump_in_m3s"]
    outs = d["pump_out_m3s"] + d["tunnelflow_m3s"] + d["hatchflow_m3s"] + d["overflow_m3s"] + d["auto_qmin_m3s"]
    return d["res_Mm3"] - start_Mm3 - M3(ins - outs), M3(ins), M3(outs)

def run_case(fr_up, fr_low, pump_a, gen_a, zero_inflow=True):
    m.zero_all_other_actions()
    if zero_inflow:
        m.zero_inflow()
    m.set_levels(fr_up, fr_low)
    m.set_loop_actions(pump_a, gen_a)
    w = m.run()
    r = m.read()
    U0, L0 = float(vr.init_Mm3(h, SKYFONNA)), float(vr.init_Mm3(h, TROLLDAMMEN))
    steps = []
    prevU, prevL = U0, L0
    for t in range(m.T):
        d = fields(r, t)
        resU, inU, outU = balance(prevU, d["U"])
        resL, inL, outL = balance(prevL, d["L"])
        # which part of TROLLDAMMEN's up_inflow is NOT the station's discharge
        steps.append({"t": t, "pump_m3s": d["pump_m3s"], "station_m3s": d["station_m3s"],
                      "SKYFONNA_tunnel_m3s": d["U"]["tunnelflow_m3s"], "HEIMFOSS_up_inflow": d["station_up_inflow"],
                      "U": d["U"], "L": d["L"],
                      "U_balance_residual_Mm3": resU, "L_balance_residual_Mm3": resL,
                      "L_up_inflow_minus_station_m3s": d["L"]["up_inflow"] - d["station_m3s"],
                      "U_pump_in_minus_pump_m3s": d["U"]["pump_in_m3s"] - d["pump_m3s"],
                      "L_pump_out_minus_pump_m3s": d["L"]["pump_out_m3s"] - d["pump_m3s"]})
        prevU, prevL = d["U"]["res_Mm3"], d["L"]["res_Mm3"]
    return {"warnings": w, "U_start_Mm3": U0, "L_start_Mm3": L0, "U_end_Mm3": prevU, "L_end_Mm3": prevL,
            "dU_Mm3": prevU - U0, "dL_Mm3": prevL - L0, "E_in": r["E_in"], "E_out": r["E_out"],
            "eta_rt": r["eta_rt"], "steps": steps, "r": r}

# ------------------------------------------------------------------ T2/T3 closure at the reported cells
cells = {"A_max": (0.0, 1.0, [0.5, 0.0], [0.5, 0.0]),
         "B_max": (0.0, 1.0, [0.5, 0.0], [0.0, 0.5]),
         "A_interior": (0.01, 0.99, [0.5, 0.0], [0.5, 0.0])}
out["T2_T3"] = {}
for name, (fu, fl, pa, ga) in cells.items():
    c = run_case(fu, fl, pa, ga)
    c.pop("r")
    out["T2_T3"][name] = c

# ------------------------------------------------------------------ T4 knock-out at the max state
ko = {}
for name, pa, ga in (("none", [0, 0], [0, 0]), ("pump_only", [0.5, 0], [0, 0]),
                     ("station_only", [0, 0], [0.5, 0]), ("both", [0.5, 0], [0.5, 0])):
    c = run_case(0.5, 0.5, pa, ga)   # mid-range levels: no spill, and water above LRW for station-only
    ko[name] = {"dU_Mm3": c["dU_Mm3"], "dL_Mm3": c["dL_Mm3"], "warnings": c["warnings"],
                "pump_m3s": c["steps"][0]["pump_m3s"], "station_m3s": c["steps"][0]["station_m3s"],
                "L_overflow_m3s": c["steps"][0]["L"]["overflow_m3s"]}
out["T4_knockout"] = ko
out["T4_note"] = ("run at fill 0.5/0.5: at the max state (U=LRW) station-only has no water above LRW, "
                  "and L=HRW would spill; mid-range isolates the routing question")

# ------------------------------------------------------------------ T5 head provenance at A_max
c = run_case(0.0, 1.0, [0.5, 0.0], [0.5, 0.0])
r = c["r"]
U_avg = (float(vr.init_masl(h, SKYFONNA)) + r["U_end_0"]) / 2
L_avg = (float(vr.init_masl(h, TROLLDAMMEN)) + r["L_end_0"]) / 2
out["T5_heads"] = {
    "pump_Hbrutto_HERSS": r["Hb_p_0"], "pump_Hbrutto_from_res_arrays(U_avg-L_avg)": U_avg - L_avg,
    "station_Hbrutto_HERSS": r["Hb_s_0"], "station_Hbrutto_from_res_arrays(U_avg-195)": U_avg - float(vr.powstat_masl(h, HEIMFOSS)),
    "station_Hbrutto_if_tailwater_were_L(U_avg-L_avg)": U_avg - L_avg,
    "U_avg": U_avg, "L_avg": L_avg}

json.dump(out, open("results/closed_loop_check.json", "w"), indent=1)

# ------------------------------------------------------------------ print
print("dt", out["dt_s"])
print("T1", {k: v_ for k, v_ in wiring.items() if k != "nodes_in_sim_order"})
print("   sim order", wiring["nodes_in_sim_order"])
for name, c in out["T2_T3"].items():
    print(f"\n{name}: warnings {c['warnings']}  eta {c['eta_rt']:.6f}")
    print(f"  SKYFONNA  start {c['U_start_Mm3']:.12f}  end {c['U_end_Mm3']:.12f}  d {c['dU_Mm3']:+.3e} Mm3")
    print(f"  TROLLDAM  start {c['L_start_Mm3']:.12f}  end {c['L_end_Mm3']:.12f}  d {c['dL_Mm3']:+.3e} Mm3")
    for s in c["steps"]:
        nz = lambda d: {k: x for k, x in d.items() if k not in ("res_Mm3", "res_masl") and x != 0.0}
        print(f"  t{s['t']}: pump {s['pump_m3s']} station {s['station_m3s']} tunnel(U) {s['SKYFONNA_tunnel_m3s']} "
              f"up_inflow(HEIMFOSS) {s['HEIMFOSS_up_inflow']}")
        print(f"      U nonzero flows {nz(s['U'])}   L nonzero flows {nz(s['L'])}")
        print(f"      balance residual U {s['U_balance_residual_Mm3']:+.2e}  L {s['L_balance_residual_Mm3']:+.2e}  "
              f"L.up_inflow-station {s['L_up_inflow_minus_station_m3s']:+.2e}  "
              f"U.pump_in-pump {s['U_pump_in_minus_pump_m3s']:+.2e}  L.pump_out-pump {s['L_pump_out_minus_pump_m3s']:+.2e}")
print("\nT4 knock-out:")
for k, x in ko.items():
    print(f"  {k:13s} dU {x['dU_Mm3']:+.9f}  dL {x['dL_Mm3']:+.9f}  pump {x['pump_m3s']} station {x['station_m3s']} "
          f"L_overflow {x['L_overflow_m3s']:.3e} warn {x['warnings']}")
print("\nT5", json.dumps(out["T5_heads"], indent=1))
