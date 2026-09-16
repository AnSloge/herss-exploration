"""Part 2 - physics and accounting checks for the HERSS PUMP node.

Instance: inst_min (see its topology.txt header). All curves linear /
analytically invertible so every number below has a closed-form reference.
Run from analysis/pump_audit/:  ../../.venv/bin/python part2_physics.py
"""
import json
from pump_oracle import PumpInstance, VERSION, VERSION_DATE

G = 9.80665          # HERSS GRAVITY (src/herss.h)
PUMP, RES_A, PST, RES_B, CH = 0, 1, 2, 3, 4

out = {"herss_version": VERSION, "herss_version_date": VERSION_DATE}
inst = PumpInstance("inst_min")
inst.diagnose()
T, DT = inst.stps, inst.dt
Mm3 = lambda q: q * DT / 1e6           # m3/s -> Mm3 over one step
m3s = lambda v: v * 1e6 / DT

print(f"HERSS {VERSION} {VERSION_DATE}   stps={T} dt={DT}s restprice={inst.restprice}")
print(f"pump params: {inst.pump_params(PUMP)}")

# ---------------------------------------------------------------- scenario
# Pump hard on for the first 8 hours, off after. Turbine and hatch stay shut,
# so the ONLY thing moving water is the pump.
for t in range(T):
    inst.set_action(PUMP, 0, t, 1.0 if t < 8 else 0.0)
    inst.set_action(PST, 0, t, 0.0)
    inst.set_action(RES_B, 0, t, 0.0)
vf = inst.run()
out["scenario_pump_only_vf"] = vf
print(f"\nVF (pump on t=0..7, everything else shut) = {vf!r}")

# ------------------------------------------------- 2.1 water balance -------
print("\n=== 2.1  per-timestep water balance ===")
print(f"{'t':>2} {'pumped_Mm3':>12} {'|bal_A|':>12} {'|bal_B|':>12} "
      f"{'A_Mm3':>10} {'B_Mm3':>10} {'sys_Mm3':>12} {'|d_sys|':>12}")
A_prev = inst.res_par(RES_A, "reservoir_init_Mm3")
B_prev = inst.res_par(RES_B, "reservoir_init_Mm3")
sys0 = A_prev + B_prev
rows, worst_A, worst_B, worst_sys, worst_transfer = [], 0.0, 0.0, 0.0, 0.0
for t in range(T):
    A, B = inst.res_Mm3(RES_A, t), inst.res_Mm3(RES_B, t)
    pumped = inst.pumped_Mm3(PUMP, t)
    # reservoir mass balance from the model's own tot_inflow / tot_outflow
    bal_A = A_prev + Mm3(inst.tot_inflow(RES_A, t)) - Mm3(inst.tot_outflow(RES_A, t)) - A
    bal_B = B_prev + Mm3(inst.tot_inflow(RES_B, t)) - Mm3(inst.tot_outflow(RES_B, t)) - B
    # what left B must be exactly what arrived in A (no losses are modelled)
    transfer = abs((A - A_prev) - (B_prev - B))
    sys = A + B
    d_sys = abs(sys - sys0)
    rows.append(dict(t=t, pumped_Mm3=pumped, bal_A=bal_A, bal_B=bal_B,
                     A=A, B=B, transfer_mismatch=transfer, sys_drift=d_sys,
                     pump_in_A=inst.pump_in(RES_A, t), pump_out_B=inst.pump_out(RES_B, t)))
    worst_A = max(worst_A, abs(bal_A)); worst_B = max(worst_B, abs(bal_B))
    worst_sys = max(worst_sys, d_sys); worst_transfer = max(worst_transfer, transfer)
    print(f"{t:>2} {pumped:>12.9f} {abs(bal_A):>12.3e} {abs(bal_B):>12.3e} "
          f"{A:>10.6f} {B:>10.6f} {sys:>12.8f} {d_sys:>12.3e}")
    A_prev, B_prev = A, B
out["part2_1"] = dict(rows=rows, worst_abs_balance_A=worst_A, worst_abs_balance_B=worst_B,
                      worst_transfer_mismatch=worst_transfer, worst_system_drift=worst_sys,
                      global_water_balance=inst.global_water_balance())
print(f"\nworst |balance| reservoir_A = {worst_A:.3e} Mm3")
print(f"worst |balance| reservoir_B = {worst_B:.3e} Mm3")
print(f"worst |A_gain - B_loss|     = {worst_transfer:.3e} Mm3   (losses modelled: none)")
print(f"worst |system drift|        = {worst_sys:.3e} Mm3")
print(f"global water balance        = {inst.global_water_balance()}")

# --------------------------------------------- 2.2 energy accounting -------
print("\n=== 2.2  energy accounting ===")
print(f"{'t':>2} {'Q':>6} {'Hbrutto':>10} {'Hnetto':>10} {'eta':>7} {'MWh_model':>11} "
      f"{'MWh_ref':>11} {'cost_model':>11} {'cost_ref':>11} {'d_cost':>10}")
e_rows, worst_MWh, worst_cost = [], 0.0, 0.0
for t in range(T):
    pumped = inst.pumped_Mm3(PUMP, t)
    Q = m3s(pumped)
    Hb, Hn = inst.hbrutto(PUMP, t), inst.hnetto(PUMP, t)
    eta = inst.pump_eff(PUMP, Q)
    eta_m = inst.pump_par(PUMP, "static_motor_efficiency")
    MWh_model = -inst.power(PUMP, t)                 # Power is stored negative
    cost_model = inst.cost(PUMP, t)
    ss = inst.startstop(PUMP, t)
    if Q > 1e-9:
        P_hyd_MW = 1000.0 * G * Hn * Q / 1e6
        MWh_ref = (P_hyd_MW / (eta * eta_m)) * DT / 3600.0
    else:
        MWh_ref = 0.0
    cost_ref = MWh_ref * inst.price(t) + ss
    e_rows.append(dict(t=t, Q=Q, Hbrutto=Hb, Hnetto=Hn, eta=eta,
                       MWh_model=MWh_model, MWh_ref=MWh_ref,
                       cost_model=cost_model, cost_ref=cost_ref,
                       startstop=ss, income=inst.income(PUMP, t),
                       price=inst.price(t)))
    worst_MWh = max(worst_MWh, abs(MWh_model - MWh_ref))
    worst_cost = max(worst_cost, abs(cost_model - cost_ref))
    print(f"{t:>2} {Q:>6.3f} {Hb:>10.6f} {Hn:>10.6f} {eta:>7.4f} {MWh_model:>11.7f} "
          f"{MWh_ref:>11.7f} {cost_model:>11.5f} {cost_ref:>11.5f} "
          f"{abs(cost_model-cost_ref):>10.2e}")
out["part2_2"] = dict(rows=e_rows, worst_abs_MWh_error=worst_MWh,
                      worst_abs_cost_error=worst_cost)
print(f"\nworst |MWh_model - MWh_ref|   = {worst_MWh:.3e} MWh")
print(f"worst |cost_model - cost_ref| = {worst_cost:.3e} EUR")
print(f"pump income at every t        = {set(r['income'] for r in e_rows)}")

# sign test: V must fall when the pump runs at a positive price
for t in range(T):
    inst.set_action(PUMP, 0, t, 0.0)
vf_nopump = inst.run()
out["vf_no_pump"] = vf_nopump
pump_MWh = sum(-e["Power_dummy"] if False else 0 for e in [])   # placeholder
tot_MWh = sum(r["MWh_model"] for r in e_rows)
tot_cost = sum(r["cost_model"] for r in e_rows)
moved = sum(r["pumped_Mm3"] for r in rows)
e_eq = inst.node_par(PST, "local_energy_equivalent")
terminal_gain = moved * 1e6 / 1e3 * e_eq * inst.restprice
print(f"\nVF with pump off = {vf_nopump!r}")
print(f"VF with pump on  = {vf!r}")
print(f"dVF              = {vf - vf_nopump:+.6f} EUR")
print(f"  energy cost charged      = {tot_cost:.6f} EUR  ({tot_MWh:.6f} MWh)")
print(f"  terminal value of moving = {terminal_gain:.6f} EUR  ({moved:.6f} Mm3 x "
      f"{e_eq} kWh/m3 x {inst.restprice} EUR/MWh)")
print(f"  residual (should be ~0)  = {(vf - vf_nopump) - (terminal_gain - tot_cost):+.3e} EUR")
out["vf_decomposition"] = dict(vf_pump=vf, vf_nopump=vf_nopump, dVF=vf - vf_nopump,
                               energy_cost=tot_cost, energy_MWh=tot_MWh,
                               moved_Mm3=moved, e_eq=e_eq,
                               terminal_gain=terminal_gain,
                               residual=(vf - vf_nopump) - (terminal_gain - tot_cost))

with open("part2_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part2_results.json")
