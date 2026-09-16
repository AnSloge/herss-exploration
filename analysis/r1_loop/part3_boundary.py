"""Part 3 - is R1 intrinsic to the closed loop, or removable by a placement rule?

Part 2 established, to 1.1e-16, that HERSS's closed loop obeys

    eta_rt = eta_prod * H_turb / H_pump = eta_prod * (U - P) / (U - L)

with U, L the two surfaces and P = POWSTAT_MASL (the turbine centreline).
Everything here follows from that, and every prediction is checked against HERSS.

Worst case over an instance's whole operating envelope is L at HRW(L) and U at
LRW(U), so with D = LRW(U) - HRW(L) the elevation gap and R_L = HRW(L) - LRW(L)
the lower reservoir's regulated range:

    eta_rt_max = eta_prod * (D + R_L + (LRW(L) - P)) / D

and for the physically sensible centreline P = LRW(L):

    eta_rt_max = eta_prod * (1 + R_L/D)   >  1   iff   R_L/D > (1 - eta_prod)/eta_prod
"""
import json
from build_loop import build
from pump_oracle import PumpInstance

PUMP, U, STA, L, CH = 0, 1, 2, 3, 4
out = {}
_cache = {}


def inst_for(dirname, **kw):
    if dirname not in _cache:
        build(dirname, outdir=dirname, **kw)
        i = PumpInstance(dirname); i.diagnose()
        _cache[dirname] = i
    return _cache[dirname]


def roundtrip(inst, U_fr, L_fr):
    inst.h.SetReservoir_Init_fr(U, U_fr)
    inst.h.SetReservoir_Init_fr(L, L_fr)
    for t in range(inst.stps):
        inst.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
        inst.set_action(STA, 0, t, 1.0 if t == 1 else 0.0)
        inst.set_action(L, 0, t, 0.0)
    inst.run()
    e_in = -inst.power(PUMP, 0); e_out = inst.power(STA, 1)
    return dict(H_pump=inst.hnetto(PUMP, 0), H_turb=inst.hnetto(STA, 1),
                e_in_MWh=e_in, e_out_MWh=e_out,
                agg_cost=inst.sc(STA, "cost_aggressive_actions", 1),
                up_Mm3=inst.pumped_Mm3(PUMP, 0),
                dn_Mm3=inst.tunnelflow(U, 1) * inst.dt / 1e6,
                eta_rt=(e_out / e_in) if e_in else float("nan"))


def worst_case(dirname, U_lrw, U_hrw, L_lrw, L_hrw, P, effs, U_fr=0.02):
    """L at HRW (worst), U near its LRW (worst)."""
    i = inst_for(dirname, U_lrw=U_lrw, U_hrw=U_hrw, L_lrw=L_lrw, L_hrw=L_hrw,
                 powstat_masl=P, **effs)
    r = roundtrip(i, U_fr, 1.0)
    r.update(U_lrw=U_lrw, U_hrw=U_hrw, L_lrw=L_lrw, L_hrw=L_hrw, P=P)
    return r


# ------------------------------------------------------------------ 3.1
E64 = dict(eta_pump=0.80, eta_motor=1.00, eta_turb=0.80, eta_gen=1.00)
P64 = 0.64
EREAL = dict(eta_pump=0.90, eta_motor=0.98, eta_turb=0.92, eta_gen=0.98)
PREAL = 0.90 * 0.98 * 0.92 * 0.98

print("=== 3.1  where does eta_rt cross 1.0, with the centreline at LRW(L)? ===")
print(f"  component product eta_prod = {PREAL:.5f} "
      f"(pump .90 x motor .98 x turbine .92 x gen .98 - a realistic PSH machine)")
thr = (1 - PREAL) / PREAL
print(f"  predicted threshold  R_L/D > (1-eta_prod)/eta_prod = {thr:.5f}\n")
print(f"  {'R_L':>5} {'D':>5} {'R_L/D':>7} {'H_pump':>9} {'H_turb':>9} "
      f"{'MWh in':>9} {'MWh out':>9} {'eta_rt':>8}  {'':<6}")
rows = []
R_L = 30.0                       # lower reservoir regulated range, held fixed
for D in (200.0, 150.0, 120.0, 117.0, 116.0, 115.0, 110.0, 90.0, 60.0, 30.0):
    L_lrw, L_hrw = 100.0, 100.0 + R_L
    U_lrw = L_hrw + D
    r = worst_case(f"inst_D{int(D)}", U_lrw, U_lrw + 20.0, L_lrw, L_hrw,
                   P=L_lrw, effs=EREAL)
    r["R_L"], r["D"], r["ratio_RD"] = R_L, D, R_L / D
    rows.append(r)
    mark = "<-- eta_rt > 1: ENERGY CREATED" if r["eta_rt"] > 1.0 else ""
    print(f"  {R_L:>5.0f} {D:>5.0f} {R_L/D:>7.4f} {r['H_pump']:>9.3f} "
          f"{r['H_turb']:>9.3f} {r['e_in_MWh']:>9.5f} {r['e_out_MWh']:>9.5f} "
          f"{r['eta_rt']:>8.4f}  {mark}")
cross = [r for r in rows if r["eta_rt"] > 1.0]
print(f"\n  measured crossing lies between R_L/D = "
      f"{max(r['ratio_RD'] for r in rows if r['eta_rt'] <= 1.0):.4f} and "
      f"{min(r['ratio_RD'] for r in cross):.4f}; predicted {thr:.4f}")
out["crossing"] = dict(eta_prod=PREAL, predicted_threshold=thr, rows=rows)

# ------------------------------------------------------------------ 3.2
print("\n=== 3.2  realistic geometries ===")
geoms = [
    ("high-head PSH (Norwegian fjord type)", 1200.0, 1230.0, 500.0, 520.0),
    ("medium-head PSH",                       800.0,  830.0, 500.0, 530.0),
    ("two mountain lakes, deep drawdown",     560.0,  590.0, 500.0, 540.0),
    ("two mountain lakes, small gap",         545.0,  575.0, 500.0, 540.0),
]
print(f"  centreline P = LRW(L) in every row (a real turbine sits at or below it)")
print(f"\n  {'geometry':<38} {'D':>6} {'R_L':>5} {'R_L/D':>7} {'eta_rt worst':>13}")
grows = []
for label, U_lrw, U_hrw, L_lrw, L_hrw in geoms:
    D = U_lrw - L_hrw; R = L_hrw - L_lrw
    r = worst_case(f"inst_g{int(U_lrw)}_{int(L_lrw)}_{int(L_hrw)}",
                   U_lrw, U_hrw, L_lrw, L_hrw, P=L_lrw, effs=EREAL)
    r.update(label=label, D=D, R_L=R, ratio_RD=R / D)
    grows.append(r)
    mark = "  <-- > 1" if r["eta_rt"] > 1.0 else ""
    print(f"  {label:<38} {D:>6.0f} {R:>5.0f} {R/D:>7.4f} {r['eta_rt']:>13.4f}{mark}")
out["geometries"] = grows

# ------------------------------------------------------------------ 3.3
print("\n=== 3.3  does the placement rule POWSTAT_MASL >= HRW(L) fix it? ===")
print(f"  same geometries, centreline moved to HRW(L); worst eta_rt over L's whole range")
print(f"\n  {'geometry':<38} {'P=LRW(L)':>10} {'P=HRW(L)':>10} {'eta_prod':>9} {'residual':>10}")
frows = []
for label, U_lrw, U_hrw, L_lrw, L_hrw in geoms:
    d = f"inst_fix{int(U_lrw)}_{int(L_lrw)}_{int(L_hrw)}"
    i = inst_for(d, U_lrw=U_lrw, U_hrw=U_hrw, L_lrw=L_lrw, L_hrw=L_hrw,
                 powstat_masl=L_hrw, **EREAL)
    # sweep L across its whole range, U near LRW (worst for the ratio)
    best = max(roundtrip(i, 0.02, k / 10.0)["eta_rt"] for k in range(11))
    worstlow = min(roundtrip(i, 0.02, k / 10.0)["eta_rt"] for k in range(11))
    old = next(r["eta_rt"] for r in grows if r["label"] == label)
    frows.append(dict(label=label, eta_P_at_LRW=old, eta_max_P_at_HRW=best,
                      eta_min_P_at_HRW=worstlow, eta_prod=PREAL,
                      residual_rel=best / PREAL - 1.0,
                      understatement_rel=1.0 - worstlow / PREAL))
    print(f"  {label:<38} {old:>10.4f} {best:>10.4f} {PREAL:>9.4f} "
          f"{best/PREAL - 1.0:>+10.2e}")
print("\n  'residual' = (worst eta_rt under the rule)/eta_prod - 1; <= 0 means the")
print("  rule never lets the loop exceed the product of its component efficiencies.")
for r in frows:
    print(f"  {r['label']:<38} understates by up to "
          f"{r['understatement_rel']*100:>5.1f}% when L sits at its LRW")
out["placement_rule"] = frows

with open("part3_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part3_results.json")
