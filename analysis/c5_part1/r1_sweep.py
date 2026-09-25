"""C5 part 1, Part C -- the R1-safety measurement.

Round-trip protocol from analysis/r1_loop (parts 2 and 5): pump a volume L->U
at t=0, generate the IDENTICAL volume U->L at t=1, everything else shut.
eta_rt = energy_out / energy_in, both from HERSS's own S->Power (same dt, so
the MW ratio is the MWh ratio).

Sweep, per variant:
  L_fr    0.00 .. 1.00 step 0.05   (lower reservoir across its whole range)
  a_pump  0.05 .. 1.00 step 0.05   (pump action across (0,1])
  U_fr    0.00, 0.25, 0.50, 0.75, 0.95

Volume matching uses the pump's ACTUAL lifted volume (first run, pump only),
so cells where L is nearly empty and the pump is starved are still exact
round trips rather than being filtered out. A cell is only kept if
|up - down|/up < 1e-6, U did not spill, and no aggressive-action cost was
charged. Cells with L_fr = 0 lift nothing (PUMP_INLET_MASL = LRW(L)) and are
reported as 'no round trip', not as passes.

Pass criterion per cell: eta_rt <= eta_prod (peak component product).
Also recorded: the gross-head ratio H_turb/H_pump (the geometric factor the
datum rule is supposed to cap at 1).

The instance's own inflow series is left in place (this is the instance
under test, not an idealised fixture).
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "analysis", "r1_loop"))
import build_c5 as B
from pump_oracle import PumpInstance, VERSION, VERSION_DATE

PUMP, U, STA, L = 0, 1, 2, 3
ETA_PROD = B.ETA_PROD
L_AXIS = [round(0.05 * k, 2) for k in range(21)]
A_AXIS = [round(0.05 * k, 2) for k in range(1, 21)]
U_AXIS = [0.0, 0.25, 0.5, 0.75, 0.95]
clamp = lambda x: min(1.0, max(0.0, x))


def zero(inst):
    for t in range(inst.stps):
        inst.set_action(PUMP, 0, t, 0.0)
        inst.set_action(STA, 0, t, 0.0)
        inst.set_action(L, 0, t, 0.0)


def cell(inst, a_pump, U_fr, L_fr, gen_shrink=0.0):
    """gen_shrink > 0 releases (1 - gen_shrink) of the lifted volume; used only by
    inflow_check.py, where U sits at exactly LRW + lift and float rounding would
    otherwise trip the aggressive-action branch (flow = 0). Default 0 = exact."""
    inst.h.SetReservoir_Init_fr(U, U_fr)
    inst.h.SetReservoir_Init_fr(L, L_fr)
    zero(inst)
    inst.set_action(PUMP, 0, 0, clamp(a_pump))
    inst.run()
    up = inst.pumped_Mm3(PUMP, 0)
    if up <= 1e-12:
        return dict(a_pump=a_pump, U_fr=U_fr, L_fr=L_fr, status="no_lift")
    a_gen = up * 1e6 / inst.dt / B.QMAX * (1.0 - gen_shrink)
    inst.set_action(STA, 0, 1, clamp(a_gen))
    inst.run()
    up2 = inst.pumped_Mm3(PUMP, 0)
    dn = inst.tunnelflow(U, 1) * inst.dt / 1e6
    spill_U = inst.overflow_m3s(U, 0) + inst.overflow_m3s(U, 1)
    aggr = inst.sc(STA, "cost_aggressive_actions", 1)
    e_in, e_out = -inst.power(PUMP, 0), inst.power(STA, 1)
    r = dict(a_pump=a_pump, U_fr=U_fr, L_fr=L_fr, a_gen=a_gen,
             up_Mm3=up2, dn_Mm3=dn, vol_match=abs(up2 - dn) / up2,
             spill_U_m3s=spill_U, aggressive_cost=aggr,
             Hb_pump=inst.hbrutto(PUMP, 0), Hn_pump=inst.hnetto(PUMP, 0),
             Hb_turb=inst.hbrutto(STA, 1), Hn_turb=inst.hnetto(STA, 1),
             P_in_MW=e_in, P_out_MW=e_out)
    if r["vol_match"] > 1e-6 or spill_U > 0 or aggr > 0 or e_in <= 0:
        r["status"] = "invalid"
        return r
    r["eta_rt"] = e_out / e_in
    r["gross_head_ratio"] = r["Hb_turb"] / r["Hb_pump"]
    r["pass"] = r["eta_rt"] <= ETA_PROD
    r["status"] = "ok"
    return r


def sweep(name):
    inst = PumpInstance(os.path.join(HERE, name),
                        logfile=os.path.join(HERE, "c5_sweep.log"))
    inst.diagnose()
    s = B.VARIANTS[name]
    D, R_L = B.U_LRW - s["L_hrw"], s["R_L"]
    rows = [cell(inst, a, u, l) for u in U_AXIS for l in L_AXIS for a in A_AXIS]
    ok = [r for r in rows if r["status"] == "ok"]
    worst = max(ok, key=lambda r: r["eta_rt"])
    fails = [r for r in ok if not r["pass"]]
    over1 = [r for r in ok if r["eta_rt"] > 1.0]
    summ = dict(
        variant=name, role=s["role"], POWSTAT_MASL=s["powstat"], D=D, R_L=R_L,
        R_L_over_D=R_L / D, eta_prod=ETA_PROD,
        threshold=(1 - ETA_PROD) / ETA_PROD,
        # frictionless closed-form cap for this datum (r1_loop report):
        # eta_prod * max over levels of (U-P)/(U-L)
        closed_form_cap=ETA_PROD * max(1.0, (B.U_LRW - s["powstat"]) / (B.U_LRW - s["L_hrw"])),
        n_cells=len(rows), n_ok=len(ok),
        n_no_lift=sum(r["status"] == "no_lift" for r in rows),
        n_invalid=sum(r["status"] == "invalid" for r in rows),
        n_fail=len(fails), n_over_one=len(over1),
        max_eta_rt=worst["eta_rt"], argmax=dict((k, worst[k]) for k in
                                                ("a_pump", "U_fr", "L_fr", "a_gen",
                                                 "Hb_pump", "Hb_turb", "gross_head_ratio")),
        min_eta_rt=min(r["eta_rt"] for r in ok),
        max_gross_head_ratio=max(r["gross_head_ratio"] for r in ok),
        margin_to_eta_prod=ETA_PROD - worst["eta_rt"],
        worst_fail=(max(fails, key=lambda r: r["eta_rt"]) if fails else None),
    )
    return summ, rows


def fmt_map(rows, U_fr):
    """eta_rt table at one U level, a subset of axes for the report."""
    sel_a = [0.25, 0.5, 0.75, 0.9, 1.0]
    sel_l = [0.05, 0.25, 0.5, 0.75, 1.0]
    idx = {(r["a_pump"], r["L_fr"]): r for r in rows if r["U_fr"] == U_fr}
    out = ["| a_pump \\ L_fr | " + " | ".join(f"{l:.2f}" for l in sel_l) + " |",
           "|---|" + "---|" * len(sel_l)]
    for a in sel_a:
        cells = []
        for l in sel_l:
            r = idx.get((a, l))
            cells.append(f"{r['eta_rt']:.4f}" if r and r["status"] == "ok" else "—")
        out.append(f"| {a:.2f} | " + " | ".join(cells) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    out = dict(herss_version=VERSION, herss_version_date=VERSION_DATE,
               axes=dict(L_fr=L_AXIS, a_pump=A_AXIS, U_fr=U_AXIS), variants={})
    maps = {}
    for name in ["c5_high", "c5_headkeep", "c5_high_ctrl"]:
        summ, rows = sweep(name)
        out["variants"][name] = dict(summary=summ, rows=rows)
        maps[name] = fmt_map(rows, summ["argmax"]["U_fr"])
        print(f"\n=== {name}  ({summ['role']}) ===")
        print(f"  POWSTAT_MASL {summ['POWSTAT_MASL']}  D {summ['D']}  R_L {summ['R_L']}  "
              f"R_L/D {summ['R_L_over_D']:.5f}")
        print(f"  cells: {summ['n_cells']}  ok {summ['n_ok']}  no-lift {summ['n_no_lift']}  "
              f"invalid {summ['n_invalid']}")
        print(f"  max eta_rt = {summ['max_eta_rt']:.6f} at {summ['argmax']}")
        print(f"  min eta_rt = {summ['min_eta_rt']:.6f}   max gross-head ratio = "
              f"{summ['max_gross_head_ratio']:.6f}")
        print(f"  eta_prod   = {ETA_PROD:.6f}   margin = {summ['margin_to_eta_prod']:+.6f}   "
              f"closed-form cap = {summ['closed_form_cap']:.6f}")
        print(f"  cells with eta_rt > eta_prod: {summ['n_fail']}   with eta_rt > 1: "
              f"{summ['n_over_one']}")
        print(f"  map at U_fr = {summ['argmax']['U_fr']}:\n" + maps[name])
    out["maps"] = maps
    json.dump(out, open(os.path.join(HERE, "r1_sweep_results.json"), "w"), indent=1)
    print("\nwrote r1_sweep_results.json")
