"""Part 3 - determinism, state reset, action responsiveness, diagnostics.

An oracle that is not bit-reproducible or that leaks state between runs is
unusable regardless of whether the physics is right. Everything here compares
exact IEEE-754 bit patterns, not tolerances.
"""
import json, struct, hashlib
from pump_oracle import PumpInstance, VERSION, VERSION_DATE

PUMP, RES_A, PST, RES_B, CH = 0, 1, 2, 3, 4
out = {"herss_version": VERSION, "herss_version_date": VERSION_DATE}
bits = lambda x: struct.pack("<d", x).hex()

FIELDS = ["cost", "income", "profit", "Power", "startStopCost", "Hbrutto",
          "Hnetto", "res_Mm3", "res_masl", "res_fr", "tot_inflow",
          "tot_outflow", "pump_in_m3s", "pump_out_m3s", "overflow_m3s",
          "tunnelflow_m3s", "hatchflow_m3s"]

def fingerprint(inst):
    """SHA-256 over the raw bits of every per-timestep output of every node."""
    h = hashlib.sha256()
    for n in range(inst.nr_nodes):
        for f in FIELDS:
            for t in range(inst.stps):
                h.update(struct.pack("<d", inst.sc(n, f, t)))
        if n in inst.pump_idnrs():
            for t in range(inst.stps):
                h.update(struct.pack("<d", inst.pumped_Mm3(n, t)))
                h.update(struct.pack("<d", inst.pump_cost(n, t)))
                h.update(struct.pack("<d", inst.pump_power_MW(n, t)))
    return h.hexdigest()

def set_seq(inst, pump_seq, pst_seq=None):
    for t in range(inst.stps):
        inst.set_action(PUMP, 0, t, pump_seq[t])
        inst.set_action(PST, 0, t, 0.0 if pst_seq is None else pst_seq[t])
        inst.set_action(RES_B, 0, t, 0.0)

# ======================================================= 3.1 determinism ===
print("=== 3.1  determinism: 8 identical runs of the same instance ===")
inst = PumpInstance("inst_fixture")
inst.diagnose()
T = inst.stps
seq = [1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0][:T]
runs = []
for i in range(8):
    set_seq(inst, seq, pst_seq=[0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0][:T])
    for t in range(T):
        inst.set_action(RES_B, 0, t, 0.3)
    vf = inst.run()
    runs.append((vf, bits(vf), fingerprint(inst)))
    print(f"  run {i}: VF = {vf!r}  bits={bits(vf)}  fp={runs[-1][2][:16]}")
det_vf = len({r[1] for r in runs}) == 1
det_fp = len({r[2] for r in runs}) == 1
print(f"\n  VF bit-identical across 8 runs        : {det_vf}")
print(f"  full output fingerprint identical     : {det_fp}")
out["determinism"] = dict(n_runs=8, vf=runs[0][0], vf_bits=runs[0][1],
                          fingerprint=runs[0][2], vf_bit_identical=det_vf,
                          all_outputs_identical=det_fp,
                          distinct_vf_bitpatterns=sorted({r[1] for r in runs}))

# ============================================== 3.2 state reset A-B-A =====
print("\n=== 3.2  state reset: A -> B -> A in one process ===")
instA = inst                       # inst_fixture, already loaded
instB = PumpInstance("inst_min")
instB.diagnose()

def runA():
    set_seq(instA, seq, pst_seq=[0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0][:T])
    for t in range(T):
        instA.set_action(RES_B, 0, t, 0.3)
    return instA.run(), fingerprint(instA)

def runB():
    set_seq(instB, [1.0] * 8 + [0.0] * (instB.stps - 8),
            pst_seq=[0.0] * 12 + [1.0] * (instB.stps - 12))
    return instB.run(), fingerprint(instB)

vfA1, fpA1 = runA(); print(f"  A (1st) VF = {vfA1!r}  bits={bits(vfA1)}")
vfB1, fpB1 = runB(); print(f"  B       VF = {vfB1!r}  bits={bits(vfB1)}")
vfA2, fpA2 = runA(); print(f"  A (2nd) VF = {vfA2!r}  bits={bits(vfA2)}")
vfB2, fpB2 = runB(); print(f"  B (2nd) VF = {vfB2!r}  bits={bits(vfB2)}")
vfA3, fpA3 = runA(); print(f"  A (3rd) VF = {vfA3!r}  bits={bits(vfA3)}")
okA = bits(vfA1) == bits(vfA2) == bits(vfA3) and fpA1 == fpA2 == fpA3
okB = bits(vfB1) == bits(vfB2) and fpB1 == fpB2
print(f"\n  A reproduced exactly after B : {okA}")
print(f"  B reproduced exactly         : {okB}")
out["state_reset"] = dict(vfA1=vfA1, vfA2=vfA2, vfA3=vfA3, vfB1=vfB1, vfB2=vfB2,
                          A_bits=[bits(v) for v in (vfA1, vfA2, vfA3)],
                          B_bits=[bits(vfB1), bits(vfB2)],
                          A_exact=okA, B_exact=okB,
                          A_fp=[fpA1, fpA2, fpA3], B_fp=[fpB1, fpB2])

# -- the pump-specific reset hazard: pump_in/pump_out accumulate with += -----
print("\n  pump_in/pump_out accumulation check (they are written with '+=')")
set_seq(instB, [1.0] * 8 + [0.0] * (instB.stps - 8))
acc = []
for i in range(4):
    instB.run()
    acc.append([instB.pump_in(RES_A, t) for t in range(8)])
same = all(a == acc[0] for a in acc)
print(f"    pump_in_m3s[0..7] over 4 consecutive runs identical: {same}")
print(f"    values run 0: {acc[0]}")
print(f"    values run 3: {acc[-1]}")
out["pump_accumulator_reset"] = dict(identical=same, run0=acc[0], run3=acc[-1])

# ========================================== 3.3 action responsiveness ======
print("\n=== 3.3  action responsiveness ===")
instC = PumpInstance("inst_min")
instC.diagnose()
base = [0.0] * instC.stps
set_seq(instC, base)
vf0 = instC.run()
print(f"  baseline (pump idle everywhere)  VF0 = {vf0!r}")

e_eq = instC.node_par(PST, "local_energy_equivalent")
resp = []
for t_probe in (0, 5, 11, 23):
    for a in (0.25, 0.5, 0.75, 1.0):
        s = list(base); s[t_probe] = a
        set_seq(instC, s)
        vf = instC.run()
        moved = instC.pumped_Mm3(PUMP, t_probe)
        cost = instC.cost(PUMP, t_probe)
        term = moved * 1e6 / 1e3 * e_eq * instC.restprice
        pred = term - cost
        resp.append(dict(t=t_probe, action=a, vf=vf, dVF=vf - vf0,
                         moved_Mm3=moved, cost=cost, terminal_gain=term,
                         predicted_dVF=pred, residual=(vf - vf0) - pred))
        print(f"  t={t_probe:>2} a={a:<5} moved={moved:.6f} Mm3  cost={cost:>8.4f}  "
              f"dVF={vf-vf0:>+10.5f}  predicted={pred:>+10.5f}  "
              f"resid={(vf-vf0)-pred:>+.3e}")
# restore and confirm exact return
set_seq(instC, base)
vf_back = instC.run()
print(f"\n  restored baseline VF = {vf_back!r}  bits={bits(vf_back)}")
print(f"  identical to VF0     : {bits(vf_back) == bits(vf0)}")
out["responsiveness"] = dict(vf0=vf0, vf0_bits=bits(vf0), probes=resp,
                             vf_restored=vf_back,
                             restored_exact=bits(vf_back) == bits(vf0))

# monotonicity in the action
mono = []
set_seq(instC, base)
for a in [i / 20.0 for i in range(21)]:
    s = list(base); s[5] = a
    set_seq(instC, s)
    mono.append((a, instC.run()))
strictly_dec = all(mono[i + 1][1] <= mono[i][1] + 1e-12 for i in range(len(mono) - 1))
print(f"  VF non-increasing in pump action at t=5 (price 50 > 0): {strictly_dec}")
out["monotonicity"] = dict(points=mono, non_increasing=strictly_dec)

# ==================================================== 3.4 diagnostics =====
print("\n=== 3.4  diagnostics ===")
diag = {}
for name in ("inst_fixture", "inst_min", "inst_energygen"):
    d = PumpInstance(name)          # __init__ runs gc.Diagnose() + gc.checkNrSteps()
    d.diagnose()                    # rs.DiagnoseRiversystemConfiguration()
    d.run()
    gwb = d.global_water_balance()
    diag[name] = dict(ok=True, nodes=d.node_types(), stps=d.stps,
                      global_water_balance=gwb)
    print(f"  {name:<16} Diagnose + checkNrSteps + DiagnoseRiversystemConfiguration OK, "
          f"|global balance| = {abs(gwb['balance']):.3e} Mm3")
out["diagnostics"] = diag

with open("part3_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part3_results.json")
