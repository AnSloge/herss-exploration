"""Part 4 - validate the pump replica against real HERSS, per timestep.

Tolerance: |dVF| < 0.05 EUR (the tolerance used by the existing replica work
in analysis/scarcity_gap and analysis/full_cascade).
"""
import json, random
from pump_oracle import PumpInstance
import params_pump
from replica_pump import simulate, Pump as RPump, Pstation as RPst, Reservoir as RRes

TOL = 0.05
out = {}

def validate(name, builder, seqs):
    p, chan_init = builder()
    inst = PumpInstance(name)
    inst.diagnose()
    T = inst.stps
    assert inst.dt == p.dt, (inst.dt, p.dt)
    pumps = [i for i in p.order if isinstance(p.nodes[i], RPump)]
    stas = [i for i in p.order if isinstance(p.nodes[i], RPst)]
    hatches = [i for i in p.order if isinstance(p.nodes[i], RRes)
               and p.nodes[i].hatch_to is not None]
    prices = [inst.price(t) for t in range(T)]
    inflow = [{i: inst.inflow(i, t) for i in p.order
               if isinstance(p.nodes[i], RRes)} for t in range(T)]
    init_fr = {i: inst.res_par(i, "reservoir_init_fr") for i in p.order
               if isinstance(p.nodes[i], RRes)}

    results = []
    for tag, seq in seqs:
        acts = []
        for t in range(T):
            a = {}
            for i in pumps:   a[i] = seq["pump"][t]
            for i in stas:    a[i] = seq["pst"][t]
            for i in hatches: a[i] = seq["hatch"][t]
            acts.append(a)
        # --- HERSS ---
        for t in range(T):
            for i in pumps:   inst.set_action(i, 0, t, seq["pump"][t])
            for i in stas:    inst.set_action(i, 0, t, seq["pst"][t])
            for i in hatches: inst.set_action(i, 0, t, seq["hatch"][t])
        vf_h = inst.run()
        # --- replica ---
        vf_r, prof_r, term_r, rec, _ = simulate(
            p, init_fr, acts, inflow, prices, inst.restprice, chan_init)

        # per-timestep comparison of the pump's own quantities
        worst = {}
        for i in pumps:
            for f, getter in (("pumped_Mm3", lambda t, i=i: inst.pumped_Mm3(i, t)),
                              ("Power", lambda t, i=i: inst.power(i, t)),
                              ("cost", lambda t, i=i: inst.cost(i, t)),
                              ("Hbrutto", lambda t, i=i: inst.hbrutto(i, t)),
                              ("Hnetto", lambda t, i=i: inst.hnetto(i, t))):
                d = max(abs(rec[(i, f)][t] - getter(t)) for t in range(T))
                worst[f"pump{i}.{f}"] = d
        for i in p.order:
            if isinstance(p.nodes[i], RRes):
                for f, g in (("res_Mm3", inst.res_Mm3), ("res_masl", inst.res_masl),
                             ("overflow_m3s", inst.overflow_m3s),
                             ("tunnelflow_m3s", inst.tunnelflow),
                             ("hatchflow_m3s", inst.hatchflow)):
                    d = max(abs(rec[(i, f)][t] - g(i, t)) for t in range(T))
                    worst[f"res{i}.{f}"] = d
            if isinstance(p.nodes[i], RPst):
                for f, g in (("Power", inst.power), ("income", inst.income),
                             ("Hbrutto", inst.hbrutto), ("Hnetto", inst.hnetto)):
                    d = max(abs(rec[(i, f)][t] - g(i, t)) for t in range(T))
                    worst[f"sta{i}.{f}"] = d

        dvf = vf_r - vf_h
        results.append(dict(tag=tag, vf_herss=vf_h, vf_replica=vf_r, dVF=dvf,
                            worst_per_step=worst))
        flag = "OK " if abs(dvf) < TOL else "FAIL"
        print(f"  [{flag}] {tag:<28} VF_herss={vf_h:>14.6f}  VF_rep={vf_r:>14.6f}  "
              f"dVF={dvf:>+12.3e}  worst_step={max(worst.values()):.3e}")
    return results


def seqs_for(T, rng):
    out = [("all off", dict(pump=[0.0]*T, pst=[0.0]*T, hatch=[0.0]*T)),
           ("pump full, rest off", dict(pump=[1.0]*T, pst=[0.0]*T, hatch=[0.0]*T)),
           ("pump half", dict(pump=[0.5]*T, pst=[0.0]*T, hatch=[0.0]*T)),
           ("alternating pump", dict(pump=[float(t % 2) for t in range(T)],
                                     pst=[0.0]*T, hatch=[0.0]*T)),
           ("pump + generate", dict(pump=[1.0 if t % 4 < 2 else 0.0 for t in range(T)],
                                    pst=[0.0 if t % 4 < 2 else 1.0 for t in range(T)],
                                    hatch=[0.3]*T)),
           ("shipped-style", dict(pump=[1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0] * ((T+7)//8),
                                  pst=[0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0] * ((T+7)//8),
                                  hatch=[0.3]*T))]
    out = [(tag, {k: v[:T] for k, v in d.items()}) for tag, d in out]
    for s in range(6):
        out.append((f"random seed {s}",
                    dict(pump=[round(rng.random(), 3) for _ in range(T)],
                         pst=[round(rng.random(), 3) for _ in range(T)],
                         hatch=[round(rng.random(), 3) for _ in range(T)])))
    return out


print("=== Part 4: replica vs HERSS ===")
rng = random.Random(20260916)
print("\ninst_min (dt=3600 s, 24 steps, flat price):")
out["inst_min"] = validate("inst_min", params_pump.inst_min, seqs_for(24, rng))
rng = random.Random(20260916)
print("\ninst_fixture (dt=86400 s, 8 steps, shipped gtest fixture):")
out["inst_fixture"] = validate("inst_fixture", params_pump.inst_fixture, seqs_for(8, rng))

allr = out["inst_min"] + out["inst_fixture"]
worst_vf = max(abs(r["dVF"]) for r in allr)
worst_step = max(max(r["worst_per_step"].values()) for r in allr)
print(f"\nworst |dVF| over {len(allr)} action sequences = {worst_vf:.3e} EUR "
      f"(tolerance {TOL})")
print(f"worst per-timestep field discrepancy        = {worst_step:.3e}")
print(f"VERDICT: {'PASS' if worst_vf < TOL else 'FAIL'}")
out["summary"] = dict(n_sequences=len(allr), worst_abs_dVF=worst_vf,
                      worst_per_step=worst_step, tolerance=TOL,
                      passed=bool(worst_vf < TOL))
with open("part5_replica_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("wrote part5_replica_results.json")
