"""Part 5 - is R1 eliminated in data/fabelvassdraget?

Two independent checks against R1_LOOP_REPORT.md:

  (a) STATIC.  Enumerate every closed pump-and-generate loop in the topology
      (pump L->U, plus a station whose intake reservoir is U and whose
      DOWNLINK_IDNR is L) and test the report's safe-placement rule
      POWSTAT_MASL >= HRW(L), plus the energy-creation criterion
      R_L/D > (1 - eta_prod)/eta_prod.

  (b) MEASURED.  Run the report's round-trip protocol on the dataset itself:
      pump a known volume L->U at t=0, generate the identical volume U->L at
      t=1, everything else shut. eta_rt = energy_out / energy_in, both from
      HERSS's own S->Power. Sweeps the operating point and the reservoir
      levels and reports the worst (highest) eta_rt found.

Runs on inst_fabel/, a verbatim copy of data/fabelvassdraget, so nothing under
data/ is touched.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pump_oracle import PumpInstance, VERSION, VERSION_DATE

INST = os.path.join(HERE, "inst_fabel")
SRC_DATASET = "data/fabelvassdraget"


# --------------------------------------------------------------- topology
def parse(path):
    """Minimal topology reader: one dict per node, keyword -> list of tokens."""
    nodes, cur = {}, None
    for raw in open(path):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        tok = line.split()
        if tok[0].upper() == "NODE":
            cur = dict(id=int(tok[2]), type=tok[1].upper(), name=tok[3], kw={})
            nodes[cur["id"]] = cur
        elif tok[0].upper() == "ENDNODE":
            cur = None
        elif cur is not None:
            cur["kw"].setdefault(tok[0].upper(), []).append(tok[1:])
    return nodes


def num(node, key, i=0):
    v = node["kw"].get(key)
    return None if not v else float(v[0][i])


def peak_curve(node, gen_block=None):
    """Highest efficiency on a UNIFORM_NORMALIZED_CURVE, as a fraction."""
    rows = node["kw"].get("UNIFORM_NORMALIZED_CURVE")
    return None if not rows else None


def curve_peak_from_text(path, node_id):
    """Peak of every UNIFORM_NORMALIZED_CURVE inside one NODE block."""
    txt = open(path).read()
    blocks = re.split(r"^NODE ", txt, flags=re.M)[1:]
    for b in blocks:
        if int(b.split()[1]) != node_id:
            continue
        vals = [float(m) for m in re.findall(r"^\s*\d\.\d+\s+(\d+\.?\d*)\s*$", b, flags=re.M)]
        return max(vals) / 100.0 if vals else None
    return None


def find_loops(nodes, topo_path):
    """Every (pump, L, U, station) closed loop, in the R1 sense."""
    # reservoir -> station it feeds, via the RESERVOIR's OUTLET_TUNNEL
    intake_of = {}
    for n in nodes.values():
        if n["type"] == "RESERVOIR":
            t = num(n, "OUTLET_TUNNEL")
            if t is not None and t >= 0:
                intake_of[int(t)] = n["id"]

    loops = []
    for p in nodes.values():
        if p["type"] != "PUMP":
            continue
        L, U = int(num(p, "PUMP_SOURCE_IDNR")), int(num(p, "PUMP_TARGET_IDNR"))
        for s in nodes.values():
            if s["type"] != "PSTATION":
                continue
            if intake_of.get(s["id"]) != U:
                continue
            if int(num(s, "DOWNLINK_IDNR")) != L:
                continue
            loops.append(dict(
                pump=p["id"], pump_name=p["name"],
                sta=s["id"], sta_name=s["name"],
                L=L, L_name=nodes[L]["name"], U=U, U_name=nodes[U]["name"],
                L_lrw=num(nodes[L], "LRW"), L_hrw=num(nodes[L], "HRW"),
                U_lrw=num(nodes[U], "LRW"), U_hrw=num(nodes[U], "HRW"),
                powstat_masl=num(s, "POWSTAT_MASL"),
                eta_pump=curve_peak_from_text(topo_path, p["id"]),
                eta_motor=num(p, "STATIC_MOTOR_EFFICIENCY"),
                eta_turb=curve_peak_from_text(topo_path, s["id"]),
                eta_gen=num(s, "STATIC_GENERATOR_EFFICIENCY"),
                pump_qmax=num(p, "MAX_DISCHARGE"),
                sta_ngen=int(num(s, "NR_GENERATORS")),
                sta_gen_qmax=num(s, "GENERATOR_MAX_DISCHARGE"),
                pump_headloss=num(p, "HEADLOSSCOEF"),
                sta_headloss=num(s, "HEADLOSSCOEF"),
            ))
    return loops


# ------------------------------------------------------------ measurement
# node id -> number of settable action slots (filled in main() from the topology)
ACTION_SLOTS = {}


def action_slots(nodes):
    """Valid (node, gen) action slots: PSTATION generators, PUMP, open hatches."""
    slots = {}
    for n in nodes.values():
        if n["type"] == "PSTATION":
            slots[n["id"]] = int(num(n, "NR_GENERATORS"))
        elif n["type"] == "PUMP":
            slots[n["id"]] = 1
        elif n["type"] == "RESERVOIR":
            h = num(n, "OUTLET_HATCH")
            if h is not None and h >= 0:
                slots[n["id"]] = 1
    return slots


def roundtrip(inst, lp, a_pump, U_fr, L_fr):
    """Pump one step L->U at t=0, release the identical volume at t=1."""
    P, S, U, L = lp["pump"], lp["sta"], lp["U"], lp["L"]

    # Every action in the system to zero. SetAction hard-errors on an
    # out-of-range gen_idnr and on a RESERVOIR without a hatch, so the valid
    # (node, gen) pairs come from the topology rather than from guessing.
    for n, ngen in ACTION_SLOTS.items():
        for t in range(inst.stps):
            for g in range(ngen):
                inst.set_action(n, g, t, 0.0)

    inst.h.SetReservoir_Init_fr(U, U_fr)
    inst.h.SetReservoir_Init_fr(L, L_fr)

    # volume match: a_pump * Qmax_pump  ==  ngen * a_gen * Qmax_gen
    a_gen = a_pump * lp["pump_qmax"] / (lp["sta_ngen"] * lp["sta_gen_qmax"])
    if a_gen > 1.0:
        return None
    inst.set_action(P, 0, 0, a_pump)
    for g in range(lp["sta_ngen"]):
        inst.set_action(S, g, 1, a_gen)

    inst.run()
    up = inst.pumped_Mm3(P, 0)
    dn = inst.tunnelflow(U, 1) * inst.dt / 1e6
    e_in, e_out = -inst.power(P, 0), inst.power(S, 1)
    if e_in <= 0 or up <= 0:
        return None
    return dict(a_pump=a_pump, a_gen=a_gen, U_fr=U_fr, L_fr=L_fr,
                up_Mm3=up, dn_Mm3=dn,
                vol_match=abs(up - dn) / up if up else float("inf"),
                H_pump=inst.hnetto(P, 0), H_turb=inst.hnetto(S, 1),
                e_in_MWh=e_in, e_out_MWh=e_out, eta_rt=e_out / e_in)


def main():
    topo = os.path.join(INST, "topology.txt")
    nodes = parse(topo)
    loops = find_loops(nodes, topo)

    out = {"herss_version": VERSION, "herss_version_date": VERSION_DATE,
           "dataset": SRC_DATASET, "loops": []}

    print(f"HERSS {VERSION} {VERSION_DATE}")
    print(f"dataset: {SRC_DATASET}  (run from a verbatim copy at inst_fabel/)")
    print(f"\n=== (a) STATIC: closed pump-and-generate loops found: {len(loops)} ===")

    for lp in loops:
        R_L = lp["L_hrw"] - lp["L_lrw"]
        D = lp["U_lrw"] - lp["L_hrw"]
        eta_prod = lp["eta_pump"] * lp["eta_motor"] * lp["eta_turb"] * lp["eta_gen"]
        # worst geometric amplifier: U at its lowest, L at its highest
        amp = (lp["U_lrw"] - lp["powstat_masl"]) / (lp["U_lrw"] - lp["L_hrw"])
        lp.update(R_L=R_L, D=D, R_L_over_D=R_L / D, eta_prod=eta_prod,
                  rule_required=lp["L_hrw"], rule_ok=lp["powstat_masl"] >= lp["L_hrw"],
                  amp_worst=amp, eta_rt_predicted=eta_prod * amp,
                  creation_threshold=(1 - eta_prod) / eta_prod)

        print(f"\n  loop: PUMP {lp['pump']} {lp['pump_name']}  "
              f"L={lp['L']} {lp['L_name']} -> U={lp['U']} {lp['U_name']}"
              f"  -> PSTATION {lp['sta']} {lp['sta_name']} -> L")
        print(f"    L  LRW {lp['L_lrw']:.1f}  HRW {lp['L_hrw']:.1f}   R_L = {R_L:.1f} m")
        print(f"    U  LRW {lp['U_lrw']:.1f}  HRW {lp['U_hrw']:.1f}   D   = {D:.1f} m"
              f"   R_L/D = {R_L/D:.4f}")
        print(f"    eta_prod (best operating point) = {eta_prod:.5f}"
              f"    creation threshold R_L/D > {(1-eta_prod)/eta_prod:.5f}")
        print(f"    POWSTAT_MASL = {lp['powstat_masl']:.1f}   rule needs >= HRW(L) ="
              f" {lp['L_hrw']:.1f}   -> {'OK' if lp['rule_ok'] else 'VIOLATED'}")
        print(f"    predicted worst eta_rt = eta_prod * (U-P)/(U-L) = "
              f"{eta_prod:.5f} * {amp:.5f} = {eta_prod*amp:.5f}"
              f"{'   <-- ENERGY CREATION' if eta_prod*amp > 1 else ''}")

    print(f"\n=== (b) MEASURED: round trip on the dataset itself ===")
    ACTION_SLOTS.update(action_slots(nodes))
    inst = PumpInstance(INST, logfile=os.path.join(HERE, "pump_audit.log"))
    inst.diagnose()
    print(f"  loaded: {inst.nr_nodes} nodes, {inst.stps} steps, dt={inst.dt}s")

    for lp in loops:
        print(f"\n  --- PUMP {lp['pump']} {lp['pump_name']} loop "
              f"({lp['L_name']} <-> {lp['U_name']} via {lp['sta_name']}) ---")
        print(f"  {'a_pump':>7} {'a_gen':>7} {'U_fr':>5} {'L_fr':>5} {'up Mm3':>10} "
              f"{'dn Mm3':>10} {'H_pump':>9} {'H_turb':>9} {'MWh in':>9} {'MWh out':>9} "
              f"{'eta_rt':>8}")
        rows, best = [], None
        for a_pump in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8):
            for U_fr in (0.0, 0.1):
                for L_fr in (0.0, 0.5, 1.0):
                    r = roundtrip(inst, lp, a_pump, U_fr, L_fr)
                    if r is None or r["vol_match"] > 1e-6:
                        continue
                    rows.append(r)
                    if best is None or r["eta_rt"] > best["eta_rt"]:
                        best = r
        for r in rows:
            mark = "  <-- max" if r is best else ""
            print(f"  {r['a_pump']:>7.2f} {r['a_gen']:>7.3f} {r['U_fr']:>5.1f} "
                  f"{r['L_fr']:>5.1f} {r['up_Mm3']:>10.6f} {r['dn_Mm3']:>10.6f} "
                  f"{r['H_pump']:>9.3f} {r['H_turb']:>9.3f} {r['e_in_MWh']:>9.4f} "
                  f"{r['e_out_MWh']:>9.4f} {r['eta_rt']:>8.4f}{mark}")
        lp["measured_rows"] = rows
        lp["eta_rt_measured_max"] = best["eta_rt"] if best else None
        print(f"    measured max eta_rt = "
              f"{best['eta_rt']:.4f}" if best else "    no valid rows")

        # focused map around the maximum: how wide is the region, and is the
        # coarse maximum an interior optimum or just the edge of the grid?
        lp["region_map"] = None
        if best:
            b = best["a_pump"]
            a_axis = [round(b + d, 3) for d in (-0.10, -0.05, 0.0, 0.05, 0.10)]
            a_axis = [a for a in a_axis if 0.0 < a <= 1.0]
            l_axis = [0.70, 0.80, 0.85, 0.90, 0.95, 1.00]
            print(f"\n    focused map, U_fr = {best['U_fr']:.1f} "
                  f"({lp['U_name']} at fr {best['U_fr']:.1f})")
            print("      a_pump \\ L_fr" + "".join(f"{f:>9.2f}" for f in l_axis))
            grid, over = [], []
            for a in a_axis:
                line = []
                for lf in l_axis:
                    r = roundtrip(inst, lp, a, best["U_fr"], lf)
                    e = r["eta_rt"] if r and r["vol_match"] <= 1e-6 else float("nan")
                    line.append(e)
                    if e == e and e > 1.0:
                        over.append(dict(a_pump=a, L_fr=lf, eta_rt=e,
                                         e_in_MWh=r["e_in_MWh"],
                                         e_out_MWh=r["e_out_MWh"]))
                grid.append(dict(a_pump=a, eta_rt=line))
                print(f"      {a:>12.2f}" + "".join(f"{e:>9.4f}" for e in line))
            n_cells = sum(len(g["eta_rt"]) for g in grid)
            print(f"      cells with eta_rt > 1: {len(over)} of {n_cells}")
            if over:
                w = max(over, key=lambda x: x["eta_rt"])
                created = w["e_out_MWh"] - w["e_in_MWh"]
                print(f"      worst: a_pump={w['a_pump']} L_fr={w['L_fr']} "
                      f"eta_rt={w['eta_rt']:.4f}  "
                      f"{w['e_in_MWh']:.4f} MWh in -> {w['e_out_MWh']:.4f} MWh out")
                print(f"      net energy created per cycle: {created:.4f} MWh "
                      f"({100*created/w['e_in_MWh']:.2f}% of input)")
            lp["region_map"] = dict(U_fr=best["U_fr"], L_fr_axis=l_axis, grid=grid,
                                    cells_over_one=len(over), cells_total=n_cells,
                                    over=over)
        out["loops"].append(lp)

    with open(os.path.join(HERE, "part5_results.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote part5_results.json")


if __name__ == "__main__":
    main()
