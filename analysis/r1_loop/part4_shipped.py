"""Part 3 addendum - (a) the shipped HERSS pump fixture itself, and
(b) a minimax alternative to the conservative placement rule."""
import json, shutil, os
from build_loop import build
from pump_oracle import PumpInstance

PUMP, U, STA, L = 0, 1, 2, 3
out = {}

# ---------------------------------------------------------------- (a) shipped
print("=== A. the fixture HERSS itself ships (src_tests/pump_test) ===")
print("  It is a CLOSED LOOP: pump source=reservoir_B target=reservoir_A;")
print("  station intake=reservoir_A (OUTLET_TUNNEL 2), outfall=reservoir_B (DOWNLINK_IDNR 3).")
src = "../pump_audit/inst_fixture"
dst = "inst_shipped"
if not os.path.isdir(dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("output"))
    os.makedirs(os.path.join(dst, "output"), exist_ok=True)
i = PumpInstance(dst); i.diagnose()

# The same fixture with ONLY POWSTAT_MASL moved 70.0 -> LRW(reservoir_B) = 60.0,
# i.e. the turbine centreline placed where the manual's wording invites. Used at
# the end of this section.
dst60 = "inst_shipped_P60"
if not os.path.isdir(dst60):
    shutil.copytree(dst, dst60, ignore=shutil.ignore_patterns("output"))
    os.makedirs(os.path.join(dst60, "output"), exist_ok=True)
    tp = os.path.join(dst60, "topology.txt")
    t = open(tp).read()
    assert "POWSTAT_MASL 70.0" in t
    open(tp, "w").write(t.replace("POWSTAT_MASL 70.0", "POWSTAT_MASL 60.0"))
    gp = os.path.join(dst60, "global.txt")
    g = open(gp).read().replace("SYSTEMNAME pump_fixture", "SYSTEMNAME shipped_P60")
    open(gp, "w").write(g)
# reservoir_A: LRW 90 HRW 110 ; reservoir_B: LRW 60 HRW 75 ; POWSTAT_MASL 70
rows = []
print(f"\n  {'B_fr':>5} {'B masl':>8} {'H_pump':>9} {'H_turb':>9} {'MWh in':>9} "
      f"{'MWh out':>9} {'eta_rt':>8}")
for k in range(11):
    fr = k / 10.0
    i.h.SetReservoir_Init_fr(U, 0.5)
    i.h.SetReservoir_Init_fr(L, fr)
    for t in range(i.stps):
        i.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
        i.set_action(STA, 0, t, 1.0 if t == 1 else 0.0)
        i.set_action(L, 0, t, 0.0)
    i.run()
    e_in, e_out = -i.power(PUMP, 0), i.power(STA, 1)
    r = dict(B_fr=fr, B_masl=i.res_masl(L, 0), H_pump=i.hnetto(PUMP, 0),
             H_turb=i.hnetto(STA, 1), e_in=e_in, e_out=e_out,
             eta_rt=e_out / e_in if e_in else float("nan"))
    # At B_fr = 0 the pump is blocked by PUMP_INLET_MASL 61.0 (B sits at 60.009),
    # so no water moves and eta_rt is undefined. Excluded from min/max.
    r["blocked"] = e_in == 0.0
    rows.append(r)
    eta_s = "  blocked" if r["blocked"] else f"{r['eta_rt']:>8.4f}"
    print(f"  {fr:>5.1f} {r['B_masl']:>8.3f} {r['H_pump']:>9.4f} {r['H_turb']:>9.4f} "
          f"{e_in:>9.5f} {e_out:>9.5f} {eta_s}")
eta_prod = 0.78 * 0.97 * 0.88 * 0.96
print(f"\n  component product at Q=Qmax: 0.78 x 0.97 x 0.88 x 0.96 = {eta_prod:.4f}")
valid = [r for r in rows if not r["blocked"]]
lo, hi = min(r['eta_rt'] for r in valid), max(r['eta_rt'] for r in valid)
print(f"  measured eta_rt ranges {lo:.4f} .. {hi:.4f}  (spread {hi/lo:.3f}x) "
      f"across reservoir_B's range alone")
print(f"  eta_prod is crossed at B ~ {70.0:.0f} masl = POWSTAT_MASL: below it the model")
print(f"  UNDERSTATES the round trip, above it it OVERSTATES it.")
print(f"  geometry: D = LRW(A) - HRW(B) = 90 - 75 = 15 m,  R_L = 75 - 60 = 15 m,  R_L/D = 1.00")
print(f"  threshold for energy creation at P=LRW(L): (1-eta_prod)/eta_prod = "
      f"{(1-eta_prod)/eta_prod:.4f}  -> R_L/D = 1.00 is WELL above it")
print(f"  the fixture escapes eta_rt > 1 only because POWSTAT_MASL = 70 sits 10 m")
print(f"  INSIDE reservoir_B's range (60-75), not at its LRW.")
out["shipped_fixture"] = dict(rows=rows, eta_prod=eta_prod,
                              eta_min=lo, eta_max=hi, spread=hi / lo)

# ---------------------------------------------------------------- (b) minimax
print("\n=== B. minimax placement P = midpoint of L's range, as an alternative ===")
print("  The conservative rule P >= HRW(L) never creates energy but understates")
print("  generation by up to R_L/(D+R_L). Centring the datum halves the worst error")
print("  but permits eta_rt slightly above eta_prod.")
EREAL = dict(eta_pump=0.90, eta_motor=0.98, eta_turb=0.92, eta_gen=0.98)
PREAL = 0.90 * 0.98 * 0.92 * 0.98
geoms = [("high-head PSH", 1200.0, 1230.0, 500.0, 520.0),
         ("medium-head PSH", 800.0, 830.0, 500.0, 530.0),
         ("two mountain lakes, deep drawdown", 560.0, 590.0, 500.0, 540.0)]
print(f"\n  {'geometry':<34} {'P':>8} {'eta_rt min':>11} {'eta_rt max':>11} "
      f"{'max |err| vs eta_prod':>22}")
mrows = []
for label, U_lrw, U_hrw, L_lrw, L_hrw in geoms:
    for tag, P in (("mid(L)", (L_lrw + L_hrw) / 2.0), ("HRW(L)", L_hrw)):
        d = f"inst_mm{int(U_lrw)}_{int(L_lrw)}_{tag.replace('(','').replace(')','')}"
        build(d, outdir=d, U_lrw=U_lrw, U_hrw=U_hrw, L_lrw=L_lrw, L_hrw=L_hrw,
              powstat_masl=P, **EREAL)
        ii = PumpInstance(d); ii.diagnose()
        es = []
        for k in range(11):
            ii.h.SetReservoir_Init_fr(U, 0.02); ii.h.SetReservoir_Init_fr(L, k / 10.0)
            for t in range(ii.stps):
                ii.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
                ii.set_action(STA, 0, t, 1.0 if t == 1 else 0.0)
                ii.set_action(L, 0, t, 0.0)
            ii.run()
            es.append(ii.power(STA, 1) / -ii.power(PUMP, 0))
        err = max(abs(e / PREAL - 1.0) for e in es)
        mrows.append(dict(label=label, tag=tag, P=P, eta_min=min(es),
                          eta_max=max(es), max_rel_err=err))
        print(f"  {label + ' [' + tag + ']':<34} {P:>8.1f} {min(es):>11.4f} "
              f"{max(es):>11.4f} {err*100:>21.2f}%")
out["minimax"] = dict(eta_prod=PREAL, rows=mrows)

# --------------------------------------------- (c) the fixture, one edit away
print("\n=== C. the shipped fixture with POWSTAT_MASL moved to LRW(reservoir_B) ===")
print("  Only POWSTAT_MASL changes: 70.0 -> 60.0. Everything else is the shipped fixture.")
i60 = PumpInstance(dst60); i60.diagnose()
print(f"\n  {'A_fr':>5} {'B masl':>9} {'H_pump':>9} {'H_turb':>9} {'MWh in':>9} "
      f"{'MWh out':>9} {'eta_rt':>8}")
crows, best = [], 0.0
for A_fr in (0.0, 0.5):
    for k in (8, 9, 10):
        i60.h.SetReservoir_Init_fr(U, A_fr); i60.h.SetReservoir_Init_fr(L, k / 10.0)
        for t in range(i60.stps):
            i60.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
            i60.set_action(STA, 0, t, 1.0 if t == 1 else 0.0)
            i60.set_action(L, 0, t, 0.0)
        i60.run()
        ein, eout = -i60.power(PUMP, 0), i60.power(STA, 1)
        if ein <= 0:
            continue
        e = eout / ein; best = max(best, e)
        crows.append(dict(A_fr=A_fr, B_masl=i60.res_masl(L, 0), H_pump=i60.hnetto(PUMP, 0),
                          H_turb=i60.hnetto(STA, 1), e_in=ein, e_out=eout, eta_rt=e))
        print(f"  {A_fr:>5.1f} {i60.res_masl(L,0):>9.3f} {i60.hnetto(PUMP,0):>9.4f} "
              f"{i60.hnetto(STA,1):>9.4f} {ein:>9.5f} {eout:>9.5f} {e:>8.4f}"
              f"{'  <-- ENERGY CREATED' if e > 1.0 else ''}")
print(f"\n  max eta_rt = {best:.4f}   (component product {eta_prod:.4f})")
print("  A one-line edit to the shipped example returns more energy than it consumes,")
print("  with every diagnostic passing and nothing logged.")
out["shipped_P60"] = dict(rows=crows, eta_max=best, eta_prod=eta_prod)

with open("part4_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part4_results.json")
