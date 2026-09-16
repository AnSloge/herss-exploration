"""Part 2.3 - head convention and round-trip energy for the HERSS PUMP node.

PUMP head   = mean(target level)  - mean(source level)          [level -> level]
TURBINE head= mean(upstream level) - POWSTAT_MASL               [level -> fixed datum]

Those are different conventions. This script measures what that costs.
"""
import json
from pump_oracle import PumpInstance

PUMP, RES_A, PST, RES_B, CH = 0, 1, 2, 3, 4
out = {}

def roundtrip(inst, B_fr, label):
    """Pump one full step up at t=0, release the same volume at t=1."""
    inst.h.SetReservoir_Init_fr(RES_A, 0.5)
    inst.h.SetReservoir_Init_fr(RES_B, B_fr)
    for t in range(inst.stps):
        inst.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
        inst.set_action(PST, 0, t, 1.0 if t == 1 else 0.0)
        inst.set_action(RES_B, 0, t, 0.0)
    inst.run()
    up_Mm3 = inst.pumped_Mm3(PUMP, 0)
    dn_Mm3 = inst.tunnelflow(RES_A, 1) * inst.dt / 1e6
    e_in = -inst.power(PUMP, 0)          # MWh consumed
    e_out = inst.power(PST, 1)           # MWh generated
    r = dict(label=label, B_init_fr=B_fr,
             B_masl_start=inst.res_par(RES_B, "reservoir_init_Mm3"),
             powstat_masl=55.0,
             up_Mm3=up_Mm3, dn_Mm3=dn_Mm3,
             pump_Hbrutto=inst.hbrutto(PUMP, 0), pump_Hnetto=inst.hnetto(PUMP, 0),
             turb_Hbrutto=inst.hbrutto(PST, 1), turb_Hnetto=inst.hnetto(PST, 1),
             e_in_MWh=e_in, e_out_MWh=e_out,
             roundtrip_eff=(e_out / e_in) if e_in else float("nan"))
    r["head_ratio"] = r["turb_Hnetto"] / r["pump_Hnetto"]
    return r

# --------------------------------------------------------------------------
print("=== 2.3a  inst_min: source reservoir at / above the turbine's datum ===")
inst = PumpInstance("inst_min")
inst.diagnose()
print("component efficiencies: pump 0.80 x motor 1.00 x turbine 0.80 x gen 1.00 "
      "= 0.640 expected round-trip if the two heads agreed\n")
print(f"{'case':<26} {'B_masl':>8} {'H_pump':>9} {'H_turb':>9} {'ratio':>7} "
      f"{'MWh_in':>9} {'MWh_out':>9} {'eta_rt':>8}")
res = []
for fr, lab in [(0.5, "B at 55.0 = datum"), (0.7, "B at 57.0 (+2 m)"),
                (0.9, "B at 59.0 (+4 m)"), (0.3, "B at 53.0 (-2 m)"),
                (0.1, "B at 51.0 (-4 m)")]:
    r = roundtrip(inst, fr, lab)
    B_masl = 50.0 + 10.0 * fr
    r["B_masl_start"] = B_masl
    res.append(r)
    print(f"{lab:<26} {B_masl:>8.2f} {r['pump_Hnetto']:>9.4f} {r['turb_Hnetto']:>9.4f} "
          f"{r['head_ratio']:>7.4f} {r['e_in_MWh']:>9.5f} {r['e_out_MWh']:>9.5f} "
          f"{r['roundtrip_eff']:>8.4f}")
out["inst_min_roundtrip"] = res
print(f"\nvolume up at t=0  = {res[0]['up_Mm3']:.8f} Mm3")
print(f"volume down at t=1= {res[0]['dn_Mm3']:.8f} Mm3   (identical => same water)")

print("\n=== 2.3b  intra-timestep ordering: pump and turbine in the SAME step ===")
# Pump (idnr 0) runs BEFORE pstation (idnr 2) and before reservoir_B (idnr 3),
# so within one step the pump can only see the volume B had at the END of t-1.
inst.h.SetReservoir_Init_fr(RES_A, 0.5)
inst.h.SetReservoir_Init_fr(RES_B, 0.5)
for t in range(inst.stps):
    inst.set_action(PUMP, 0, t, 0.0); inst.set_action(PST, 0, t, 0.0)
    inst.set_action(RES_B, 0, t, 0.0)
inst.set_action(PUMP, 0, 3, 1.0)
inst.set_action(PST, 0, 3, 1.0)     # same timestep
inst.run()
same = dict(B_before=inst.res_Mm3(RES_B, 2), B_after=inst.res_Mm3(RES_B, 3),
            pumped=inst.pumped_Mm3(PUMP, 3),
            turb_out_Mm3=inst.tunnelflow(RES_A, 3) * inst.dt / 1e6,
            pump_src_start_masl=inst.pump_par(PUMP, "src_start_masl"),
            pump_src_end_masl=inst.pump_par(PUMP, "src_end_masl"),
            pump_tgt_start_masl=inst.pump_par(PUMP, "tgt_start_masl"),
            pump_tgt_end_masl=inst.pump_par(PUMP, "tgt_end_masl"),
            pump_Hbrutto=inst.hbrutto(PUMP, 3))
print(json.dumps(same, indent=1))
out["same_step_ordering"] = same

# --------------------------------------------------------------------------
print("\n=== 2.3c  can the inconsistency create net energy? ===")
print("Constructed case: source reservoir sits far ABOVE the powerstation's")
print("declared tailwater datum, which HERSS does not validate.")
inst2 = PumpInstance("inst_energygen")
inst2.diagnose()
for t in range(inst2.stps):
    inst2.set_action(PUMP, 0, t, 1.0 if t == 0 else 0.0)
    inst2.set_action(PST, 0, t, 1.0 if t == 1 else 0.0)
    inst2.set_action(RES_B, 0, t, 0.0)
inst2.run()
e_in = -inst2.power(PUMP, 0)
e_out = inst2.power(PST, 1)
gen = dict(pump_Hnetto=inst2.hnetto(PUMP, 0), turb_Hnetto=inst2.hnetto(PST, 1),
           up_Mm3=inst2.pumped_Mm3(PUMP, 0),
           dn_Mm3=inst2.tunnelflow(RES_A, 1) * inst2.dt / 1e6,
           e_in_MWh=e_in, e_out_MWh=e_out,
           roundtrip_eff=e_out / e_in if e_in else float("nan"))
print(json.dumps(gen, indent=1))
print(f"\nround-trip efficiency = {gen['roundtrip_eff']:.4f}  "
      f"({'ENERGY CREATED' if gen['roundtrip_eff'] > 1.0 else 'no energy created'})")
out["energy_creation_case"] = gen

with open("part2_head_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part2_head_results.json")
