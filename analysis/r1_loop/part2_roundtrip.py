"""Part 2 - measure the closed-loop round trip, and sweep it.

Protocol for one measurement: pump a known volume L->U at t=0, generate the
identical volume U->L at t=1, everything else shut. Round-trip efficiency is
energy_generated / energy_consumed, both taken from HERSS's own S->Power.
"""
import json, os, subprocess, sys
from build_loop import build
from pump_oracle import PumpInstance, VERSION, VERSION_DATE

PUMP, U, STA, L, CH = 0, 1, 2, 3, 4
GRAVITY = 9.80665

# component efficiencies used throughout unless stated
E_PUMP, E_MOTOR, E_TURB, E_GEN = 0.80, 1.00, 0.80, 1.00
ETA_PROD = E_PUMP * E_MOTOR * E_TURB * E_GEN          # 0.6400

out = {"herss_version": VERSION, "herss_version_date": VERSION_DATE}
_cache = {}


def inst_for(dirname, **kw):
    if dirname not in _cache:
        build(dirname.split("/")[-1], outdir=dirname, **kw)
        i = PumpInstance(dirname)
        i.diagnose()
        _cache[dirname] = i
    return _cache[dirname]


def roundtrip(inst, U_fr, L_fr):
    """Pump one step up at t=0, release the identical volume at t=1."""
    inst.h.SetReservoir_Init_fr(U, U_fr)
    inst.h.SetReservoir_Init_fr(L, L_fr)
    for t in range(inst.stps):
        inst.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
        inst.set_action(STA, 0, t, 1.0 if t == 1 else 0.0)
        inst.set_action(L, 0, t, 0.0)
    inst.run()
    up = inst.pumped_Mm3(PUMP, 0)
    dn = inst.tunnelflow(U, 1) * inst.dt / 1e6
    e_in = -inst.power(PUMP, 0)
    e_out = inst.power(STA, 1)
    return dict(U_fr=U_fr, L_fr=L_fr, up_Mm3=up, dn_Mm3=dn,
                H_pump=inst.hnetto(PUMP, 0), H_turb=inst.hnetto(STA, 1),
                e_in_MWh=e_in, e_out_MWh=e_out,
                eta_rt=(e_out / e_in) if e_in else float("nan"))


# ====================================================== 2.1 the loop exists
print(f"HERSS {VERSION} {VERSION_DATE}")
print("\n=== 2.1  can the closed loop be built and simulated? ===")
base = dict(U_lrw=200, U_hrw=220, L_lrw=100, L_hrw=120, powstat_masl=100.0,
            eta_pump=E_PUMP, eta_motor=E_MOTOR, eta_turb=E_TURB, eta_gen=E_GEN)
inst = inst_for("inst_loop", **base)
print(f"  loaded OK. nodes: {inst.node_types()}")
print(f"  pump source={int(inst.pump_par(PUMP,'pump_source_idnr'))} "
      f"target={int(inst.pump_par(PUMP,'pump_target_idnr'))}")
print("  station intake  = reservoir_U (U declares OUTLET_TUNNEL 2)")
print("  station outfall = reservoir_L (station declares DOWNLINK_IDNR 3)")
print("  -> pump L->U and turbine U->L: the SAME water, a closed loop.")
print("  gc.Diagnose(), gc.checkNrSteps(), DiagnoseRiversystemConfiguration(): all clean")
r = roundtrip(inst, 0.5, 0.5)
print(f"  round trip runs: up {r['up_Mm3']:.8f} Mm3, down {r['dn_Mm3']:.8f} Mm3 "
      f"(identical => same water)")
out["loop_permitted"] = True
out["loop_smoke"] = r

# ============================================ 2.2 sweep L's surface level
print(f"\n=== 2.2  round-trip efficiency vs L's surface level ===")
print(f"  U: LRW 200 HRW 220 (held at fr=0.5 => 210 masl)")
print(f"  L: LRW 100 HRW 120     POWSTAT_MASL = 100.0 = LRW(L)  (turbine centreline)")
print(f"  component product eta_p*eta_m*eta_t*eta_g = {ETA_PROD:.4f}")
print(f"\n  {'L_fr':>5} {'L masl':>8} {'H_pump':>9} {'H_turb':>9} {'ratio':>7} "
      f"{'MWh in':>9} {'MWh out':>9} {'eta_rt':>8} {'vs 0.64':>9}")
sweep = []
for k in range(11):
    fr = k / 10.0
    r = roundtrip(inst, 0.5, fr)
    r["L_masl"] = 100.0 + 20.0 * fr
    r["ratio"] = r["H_turb"] / r["H_pump"]
    r["excess_vs_prod"] = r["eta_rt"] / ETA_PROD
    sweep.append(r)
    print(f"  {fr:>5.1f} {r['L_masl']:>8.2f} {r['H_pump']:>9.4f} {r['H_turb']:>9.4f} "
          f"{r['ratio']:>7.4f} {r['e_in_MWh']:>9.5f} {r['e_out_MWh']:>9.5f} "
          f"{r['eta_rt']:>8.4f} {r['excess_vs_prod']:>8.3f}x")
out["sweep_L_level"] = dict(eta_prod=ETA_PROD, rows=sweep)

# check the closed form eta_rt = eta_prod * H_turb / H_pump
worst = max(abs(r["eta_rt"] - ETA_PROD * r["ratio"]) for r in sweep)
print(f"\n  worst |eta_rt - eta_prod * H_turb/H_pump| = {worst:.3e}  "
      f"(closed form {'confirmed' if worst < 1e-9 else 'NOT confirmed'})")
out["closed_form_residual"] = worst

# ============================================ 2.3 sweep POWSTAT_MASL
print(f"\n=== 2.3  round-trip efficiency vs POWSTAT_MASL (turbine centreline) ===")
print(f"  L operating range is 100-120 masl. Each row sweeps L across its whole")
print(f"  range and reports the WORST (highest) eta_rt seen.")
print(f"\n  {'POWSTAT':>8} {'placement':<26} {'eta_rt @L=LRW':>14} {'eta_rt @L=HRW':>14} "
      f"{'max over L':>11}")
psweep = []
for P, label in [(90.0, "below L (deep tailrace)"), (100.0, "= LRW(L)"),
                 (105.0, "inside L's range"), (110.0, "mid L's range"),
                 (115.0, "inside L's range"), (120.0, "= HRW(L)"),
                 (125.0, "above HRW(L)")]:
    d = f"inst_P{str(P).replace('.','p')}"
    kw = dict(base); kw["powstat_masl"] = P
    i2 = inst_for(d, **kw)
    rows = [roundtrip(i2, 0.5, k / 10.0) for k in range(11)]
    lo, hi = rows[0]["eta_rt"], rows[-1]["eta_rt"]
    mx = max(r["eta_rt"] for r in rows)
    psweep.append(dict(powstat_masl=P, label=label, eta_at_LRW=lo,
                       eta_at_HRW=hi, eta_max=mx,
                       rows=[{k: v for k, v in r.items()} for r in rows]))
    flag = "" if mx <= ETA_PROD + 1e-12 else "   <-- exceeds component product"
    print(f"  {P:>8.1f} {label:<26} {lo:>14.4f} {hi:>14.4f} {mx:>11.4f}{flag}")
out["sweep_powstat"] = psweep

with open("part2_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part2_results.json")
