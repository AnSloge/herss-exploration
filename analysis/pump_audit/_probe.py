"""Subprocess probe: used for cases expected to terminate the process.
usage: _probe.py <instance> <json-actions> [B_init_fr] [A_init_fr]"""
import sys, json
from pump_oracle import PumpInstance
PUMP, RES_A, PST, RES_B = 0, 1, 2, 3
inst = PumpInstance(sys.argv[1])
# MANDATORY: Channel::casc_reservoirs is allocated only inside
# Channel::ValidateChannelSettings(), which is reached only via
# Riversystem::DiagnoseRiversystemConfiguration(). Skip this and Simulate()
# dereferences a null pointer in Channel::SetStartState(). Undocumented.
inst.diagnose()
acts = json.loads(sys.argv[2])
if len(sys.argv) > 3 and sys.argv[3] != "-":
    inst.h.SetReservoir_Init_fr(RES_B, float(sys.argv[3]))
if len(sys.argv) > 4 and sys.argv[4] != "-":
    inst.h.SetReservoir_Init_fr(RES_A, float(sys.argv[4]))
for t in range(inst.stps):
    inst.set_action(PUMP, 0, t, acts["pump"][t] if t < len(acts["pump"]) else 0.0)
    inst.set_action(PST, 0, t, acts.get("pst", [0.0] * inst.stps)[t] if t < len(acts.get("pst", [])) else 0.0)
    inst.set_action(RES_B, 0, t, 0.0)
vf = inst.run()
rep = dict(vf=vf, rows=[dict(
    t=t, action=inst.get_action(PUMP, 0, t), pumped=inst.pumped_Mm3(PUMP, t),
    cost=inst.cost(PUMP, t), ss=inst.startstop(PUMP, t), MWh=-inst.power(PUMP, t),
    A=inst.res_Mm3(RES_A, t), B=inst.res_Mm3(RES_B, t),
    A_masl=inst.res_masl(RES_A, t), B_masl=inst.res_masl(RES_B, t),
    A_overflow=inst.overflow_m3s(RES_A, t)) for t in range(inst.stps)])
print("RESULT " + json.dumps(rep))
