"""C5 part 1, Part B (validate) + the back-computed instance numbers for Part A/D.

For each variant:
  B1  in-process init with the three diagnostics (Diagnose once, checkNrSteps,
      DiagnoseRiversystemConfiguration) -- any LOG_ERR would exit the process
  B2  global water balance |balance| < 1e-6 under 13 action sequences,
      including heavy pumping
  B3  determinism (same sequence twice) and A -> B -> A reset, bit for bit
  B4  replica (analysis/pump_audit/replica_pump.py) vs HERSS, |dVF| < 0.05 EUR
  B5  terminal term: which reservoirs HERSS counts upstream of the station
  A   D, R_L, R_L/D, eta_prod, threshold, rho, R -- read back from disk / HERSS

The CLI half of B1 (herss.exe on each instance, log grepped) is run by
run_all.sh and its result is folded in here from the log files.
"""
import glob, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "analysis", "pump_audit"))
sys.path.insert(1, os.path.join(REPO, "analysis", "r1_loop"))
import build_c5 as B
from pump_oracle import PumpInstance, VERSION, VERSION_DATE
from replica_pump import simulate

PUMP, U, STA, L, CH = 0, 1, 2, 3, 4
TOL_VF = 0.05
TOL_BAL = 1e-6
BASE_COMMIT = "0e98d837ed046e0089c6c7a0a641bc314cd627a4"


# ------------------------------------------------------------ on-disk reads
def parse_topology(path):
    nodes, cur = {}, None
    lines = [l.split("#")[0].strip() for l in open(path)]
    lines = [l for l in lines if l]
    i = 0
    while i < len(lines):
        tok = lines[i].split()
        if tok[0] == "NODE":
            cur = dict(type=tok[1], id=int(tok[2]), kw={})
            nodes[cur["id"]] = cur
        elif tok[0] == "ENDNODE":
            cur = None
        elif cur is not None:
            key = tok[0]
            if key in ("RESERVOIR_CURVE", "TURBINE_CURVE", "UNIFORM_NORMALIZED_CURVE",
                       "OVERFLOW_CURVE"):
                n = int(tok[1])
                pts = [tuple(map(float, lines[i + 1 + k].split())) for k in range(n)]
                cur["kw"][key] = pts
                i += n
            else:
                cur["kw"][key] = tok[1:]
        i += 1
    return nodes


def f(node, key):
    return float(node["kw"][key][0])


def instance_numbers(d, inst):
    """Every Part-A number, read back from the files on disk and from HERSS."""
    topo = parse_topology(os.path.join(d, "topology.txt"))
    Un, Ln, Sn, Pn = topo[U], topo[L], topo[STA], topo[PUMP]
    U_lrw, U_hrw, L_lrw, L_hrw = f(Un, "LRW"), f(Un, "HRW"), f(Ln, "LRW"), f(Ln, "HRW")
    P = f(Sn, "POWSTAT_MASL")
    D, R_L = U_lrw - L_hrw, L_hrw - L_lrw
    eta_pump = max(e for _, e in Pn["kw"]["UNIFORM_NORMALIZED_CURVE"]) / 100
    eta_turb = max(e for _, e in Sn["kw"]["TURBINE_CURVE"]) / 100
    eta_motor, eta_gen = f(Pn, "STATIC_MOTOR_EFFICIENCY"), f(Sn, "STATIC_GENERATOR_EFFICIENCY")
    eta_prod = eta_pump * eta_motor * eta_turb * eta_gen
    qmax = f(Sn, "GENERATOR_MAX_DISCHARGE")

    # inflow at float64 from the text file, exactly as params.load_series does
    rows = [l.split() for l in open(os.path.join(d, "inflowseries.txt")) if l.strip()][1:]
    T = len(rows)
    inflow_U = sum(float(r[1]) for r in rows) * 86400 / 1e6
    inflow_L = sum(float(r[2]) for r in rows) * 86400 / 1e6
    init_U = float(next(l.split()[-1] for l in open(os.path.join(d, "start_state.txt"))
                        if l.startswith("NODE RESERVOIR 1")))
    init_L = float(next(l.split()[-1] for l in open(os.path.join(d, "start_state.txt"))
                        if l.startswith("NODE RESERVOIR 3")))
    # active capacity through HERSS's own ArrayCurve, as params.py does
    act_U = inst.res_par(U, "filling_at_hrw_Mm3") - inst.res_par(U, "filling_at_lrw_Mm3")
    act_L = inst.res_par(L, "filling_at_hrw_Mm3") - inst.res_par(L, "filling_at_lrw_Mm3")
    inlet = f(Pn, "PUMP_INLET_MASL")
    # water in L the pump can reach at t=0 (above PUMP_INLET_MASL)
    L0_Mm3 = inst.res_par(L, "filling_at_lrw_Mm3") + init_L * act_L
    pumpable_L0 = max(0.0, L0_Mm3 - inst.masl_to_Mm3(L, inlet))
    cap = qmax * 86400 * T / 1e6
    rho = (init_U * act_U + inflow_U) / cap
    return dict(
        U_LRW=U_lrw, U_HRW=U_hrw, L_LRW=L_lrw, L_HRW=L_hrw, POWSTAT_MASL=P,
        PUMP_INLET_MASL=inlet,
        D=D, R_L=R_L, R_L_over_D=R_L / D,
        eta_pump_peak=eta_pump, eta_motor=eta_motor, eta_turb_peak=eta_turb,
        eta_gen=eta_gen, eta_prod=eta_prod,
        threshold=(1 - eta_prod) / eta_prod,
        datum_rule_ok=P >= L_hrw, head_order_ok=L_hrw < U_lrw,
        understatement_bound=R_L / (D + R_L),
        T=T, qmax=qmax, turbine_capacity_Mm3=cap,
        active_U_Mm3=act_U, active_L_Mm3=act_L,
        init_fr_U=init_U, init_fr_L=init_L,
        inflow_U_Mm3=inflow_U, inflow_L_Mm3=inflow_L, pumpable_L0_Mm3=pumpable_L0,
        R=act_U / cap, rho=rho,
        rho_system=(init_U * act_U + inflow_U + inflow_L + pumpable_L0) / cap,
        # head-dependence strength: regulated range over gross mid head
        head_span_ratio=(U_hrw - U_lrw) / (0.5 * (U_lrw + U_hrw) - P),
        gross_head_mid=0.5 * (U_lrw + U_hrw) - P,
    )


# ------------------------------------------------------------ sequences
def seqs(T, rng):
    out = [("all off", dict(pump=[0.0]*T, pst=[0.0]*T, hatch=[0.0]*T)),
           ("shipped actions", dict(pump=[0.0]*T, pst=[0.5]*T, hatch=[0.0]*T)),
           ("generate full", dict(pump=[0.0]*T, pst=[1.0]*T, hatch=[0.0]*T)),
           ("pump full", dict(pump=[1.0]*T, pst=[0.0]*T, hatch=[0.0]*T)),
           ("gen then pump 2/2", dict(pump=[1.0 if t % 4 >= 2 else 0.0 for t in range(T)],
                                      pst=[1.0 if t % 4 < 2 else 0.0 for t in range(T)],
                                      hatch=[0.0]*T)),
           ("simultaneous gen+pump", dict(pump=[0.7]*T, pst=[0.8]*T, hatch=[0.1]*T)),
           ("hatch drain", dict(pump=[0.0]*T, pst=[0.6]*T, hatch=[1.0]*T))]
    for s in range(6):
        out.append((f"random seed {s}",
                    dict(pump=[round(rng.random(), 3) for _ in range(T)],
                         pst=[round(rng.random(), 3) for _ in range(T)],
                         hatch=[round(rng.random(), 3) for _ in range(T)])))
    return out


def apply(inst, seq):
    for t in range(inst.stps):
        # clamp every action to [0,1] before SetAction (hard rule)
        inst.set_action(PUMP, 0, t, min(1.0, max(0.0, seq["pump"][t])))
        inst.set_action(STA, 0, t, min(1.0, max(0.0, seq["pst"][t])))
        inst.set_action(L, 0, t, min(1.0, max(0.0, seq["hatch"][t])))


def cli_check(d):
    logs = glob.glob(os.path.join(d, "herss_*.log"))
    txt = "".join(open(p).read() for p in logs)
    bad = [l for l in txt.splitlines() if "ERR" in l.upper() or "WARN" in l.upper()]
    ok_end = "ended normally" in txt
    rs = open(glob.glob(os.path.join(d, "output", "riversystem_*_output.txt"))[0]).read()
    bal_line = next(l for l in rs.splitlines() if l.startswith("waterbalance"))
    return dict(logs=[os.path.basename(p) for p in logs], err_warn_lines=bad,
                ended_normally=ok_end, file_waterbalance=bal_line.strip())


def validate(name):
    d = os.path.join(HERE, name)
    s = B.VARIANTS[name]
    res = dict(variant=name, role=s["role"], cli=cli_check(d))
    inst = PumpInstance(d, logfile=os.path.join(HERE, "c5_inprocess.log"))
    inst.diagnose()                  # would LOG_ERR -> exit on failure
    res["diagnostics"] = "gc.Diagnose(), gc.checkNrSteps(), DiagnoseRiversystemConfiguration(): passed"
    T = inst.stps
    res["numbers"] = instance_numbers(d, inst)

    p, chan_init = B.replica_params(s)
    prices = [inst.price(t) for t in range(T)]
    inflow = [{U: inst.inflow(U, t), L: inst.inflow(L, t)} for t in range(T)]
    init_fr = {U: inst.res_par(U, "reservoir_init_fr"), L: inst.res_par(L, "reservoir_init_fr")}

    rng = random.Random(20260921)
    rows, vfs = [], {}
    for tag, seq in seqs(T, rng):
        apply(inst, seq)
        vf_h = inst.run()
        wb = inst.global_water_balance()
        pumped = sum(inst.pumped_Mm3(PUMP, t) for t in range(T))
        spill_L = sum(inst.overflow_m3s(L, t) for t in range(T)) * 86400 / 1e6
        acts = [{PUMP: seq["pump"][t], STA: seq["pst"][t], L: seq["hatch"][t]}
                for t in range(T)]
        vf_r = simulate(p, init_fr, acts, inflow, prices, inst.restprice, chan_init)[0]
        vfs[tag] = vf_h
        rows.append(dict(tag=tag, vf_herss=vf_h, vf_replica=vf_r, dVF=vf_r - vf_h,
                         waterbalance=wb["balance"], pumped_Mm3=pumped,
                         spill_L_Mm3=spill_L))
    res["sequences"] = rows
    res["worst_abs_balance"] = max(abs(r["waterbalance"]) for r in rows)
    res["worst_abs_dVF"] = max(abs(r["dVF"]) for r in rows)
    res["balance_pass"] = res["worst_abs_balance"] < TOL_BAL
    res["replica_pass"] = res["worst_abs_dVF"] < TOL_VF

    # B3 determinism and A -> B -> A
    sq = dict(seqs(T, random.Random(7)))
    A, Bs = sq["random seed 0"], sq["random seed 1"]
    apply(inst, A); a1 = inst.run()
    apply(inst, A); a2 = inst.run()
    apply(inst, Bs); inst.run()
    apply(inst, A); a3 = inst.run()
    res["determinism"] = dict(A1=a1, A2=a2, A_after_B=a3,
                              bit_identical=(a1 == a2 == a3))

    # B5 terminal term: upstream active volume HERSS credits to the station,
    # with U and L both part-full and nothing running
    inst.h.SetReservoir_Init_fr(U, 0.5)
    inst.h.SetReservoir_Init_fr(L, 0.5)
    apply(inst, dict(pump=[0.0]*T, pst=[0.0]*T, hatch=[0.0]*T))
    inst.run()
    res["terminal"] = dict(
        station_upstream_active_Mm3=inst.node_par(STA, "upstream_remaining_active_Mm3"),
        U_remaining_active_Mm3=inst.node_par(U, "remaining_active_Mm3"),
        L_remaining_active_Mm3=inst.node_par(L, "remaining_active_Mm3"))
    inst.h.SetReservoir_Init_fr(U, init_fr[U])
    inst.h.SetReservoir_Init_fr(L, init_fr[L])
    return res


if __name__ == "__main__":
    names = sys.argv[1:] or ["c5_high", "c5_headkeep"]
    out = dict(herss_version=VERSION, herss_version_date=VERSION_DATE,
               base_commit=BASE_COMMIT, variants={})
    for n in names:
        r = validate(n)
        out["variants"][n] = r
        nb = r["numbers"]
        print(f"\n=== {n}  ({r['role']}) ===")
        print(f"  CLI: ended normally={r['cli']['ended_normally']}  ERR/WARN lines="
              f"{len(r['cli']['err_warn_lines'])}  file: {r['cli']['file_waterbalance']}")
        print(f"  {r['diagnostics']}")
        print(f"  D={nb['D']:.1f} m  R_L={nb['R_L']:.1f} m  R_L/D={nb['R_L_over_D']:.5f}  "
              f"eta_prod={nb['eta_prod']:.6f}  threshold={nb['threshold']:.5f}  "
              f"POWSTAT>=HRW(L): {nb['datum_rule_ok']}  HRW(L)<LRW(U): {nb['head_order_ok']}")
        print(f"  rho={nb['rho']:.6f}  rho_system={nb['rho_system']:.6f}  R={nb['R']:.6f}  "
              f"active_U={nb['active_U_Mm3']:.4f}  cap={nb['turbine_capacity_Mm3']:.4f}  "
              f"head_span_ratio={nb['head_span_ratio']:.4f}")
        for x in r["sequences"]:
            print(f"    {x['tag']:<24} VF={x['vf_herss']:>14.4f}  dVF={x['dVF']:>+10.3e}  "
                  f"bal={x['waterbalance']:>+9.2e}  pumped={x['pumped_Mm3']:>8.3f}  "
                  f"spill_L={x['spill_L_Mm3']:>7.3f}")
        print(f"  worst |balance| = {r['worst_abs_balance']:.3e}  "
              f"({'PASS' if r['balance_pass'] else 'FAIL'})")
        print(f"  worst |dVF|     = {r['worst_abs_dVF']:.3e} EUR "
              f"({'PASS' if r['replica_pass'] else 'FAIL'} vs {TOL_VF})")
        print(f"  determinism / A->B->A bit-identical: {r['determinism']['bit_identical']}")
        print(f"  terminal: station upstream active {r['terminal']['station_upstream_active_Mm3']:.4f}"
              f"  U {r['terminal']['U_remaining_active_Mm3']:.4f}"
              f"  L {r['terminal']['L_remaining_active_Mm3']:.4f}")
    json.dump(out, open(os.path.join(HERE, "validation_results.json"), "w"), indent=1)
    print("\nwrote validation_results.json")
