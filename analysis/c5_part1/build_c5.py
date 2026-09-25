"""C5 part 1 -- build a closed pump-and-generate loop that is R1-safe by geometry
and sized for the Fase C hard corner.

One spec dict per variant drives BOTH the HERSS input files and the Python
replica's Params, so the two cannot drift apart.

Topology (idnr order forced by Pump::ValidatePumpSettings: the pump's idnr must
be lower than both its source and its target):

    0  PUMP      pump_LU   source 3 (L) -> target 1 (U)
    1  RESERVOIR U         = syn_rho1_R1's reservoir, verbatim curve 748/757
                           OUTLET_TUNNEL 2, overflow -> 3 (spill runs down into L)
    2  PSTATION  sta_UL    = syn_rho1_R1's station, DOWNLINK_IDNR 3 (L)
    3  RESERVOIR L         hatch -> 4, overflow -> 4
    4  CHANNEL   elv -> -9 (system outlet)

Two knob sets, kept physically separate:
  * VOLUME / THROUGHPUT (rho, R): taken unchanged from the Fase C cell
    syn_rho1_R1 -- reservoir curve, Qmax 4.0 m3/s, dt 86400, T 365, init_fr 0.7,
    inflow series (already rescaled by Fase C to hold rho = 1 exactly), prices.
  * ELEVATION (R1-safety): where L sits, and POWSTAT_MASL = HRW(L).

rho stays U's rho because the pump cannot inject new water: L starts empty
(init_fr 0) and PUMP_INLET_MASL = LRW(L), so the only pumpable water is water
the turbine (or U's spillway) already released into L. L has no natural inflow.

Nothing under src/ or data/ is read or written except the Fase C instance,
which is read only.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BASE = os.path.join(REPO, "analysis", "instances", "syn_rho1_R1")

# ---------------------------------------------------------------- the machine
# Turbine: syn_rho1_R1 / HJELLE verbatim. Peak 93 %, generator 0.96.
TURB_Q = [0.00, 1.00, 1.72, 2.27, 2.79, 3.19, 3.47, 3.67, 3.79, 4.00]
TURB_PCT = [0, 50, 80, 90, 93, 93, 93, 92, 91, 88]
# Pump: realistic reversible-unit shape, peak 90 %, motor 0.97. No zero point
# (pump.cpp:286 hard-errors on eff <= 0 with flow > 0).
PUMP_CURVE = [30, 50, 65, 75, 82, 86, 89, 90, 90, 89, 87]
PUMP_MOTOR = 0.97
GEN_EFF = 0.96
ETA_PROD = (max(PUMP_CURVE) / 100) * PUMP_MOTOR * (max(TURB_PCT) / 100) * GEN_EFF

QMAX = 4.0
HEADLOSS = 0.3
U_LRW, U_HRW = 748.0, 757.0
U_CURVE = [(747, 0.0), (748, 1.0), (749, 2.37), (750, 3.24),
           (757, 10.0), (758, 15.0), (760, 100.0)]
U_OVFL = [(757, 0.0), (758, 10.0), (760, 200.0)]
LEE_BASE = 0.11                      # syn_rho1_R1 LOCAL_ENERGY_EQUIVALENT
P_BASE = 690.0                       # syn_rho1_R1 POWSTAT_MASL
U_MID = 0.5 * (U_LRW + U_HRW)


def spec(name, L_lrw, L_hrw, powstat, L_active=9.0, role=""):
    """L is linear, L_active Mm3 over its regulated range, same shape as U
    above HRW (5 Mm3 in the first metre, then steep)."""
    R_L = L_hrw - L_lrw
    L_curve = [(L_lrw - 1, 0.5), (L_lrw, 1.0), (L_hrw, 1.0 + L_active),
               (L_hrw + 1, 6.0 + L_active), (L_hrw + 3, 91.0 + L_active)]
    # Terminal conversion scaled with gross mid-head so the terminal/in-horizon
    # bias ratio is the same as in syn_rho1_R1 (0.11 at 62.5 m). Irrelevant to
    # every part-1 number (rho, R, eta_rt); provisional for part 2.
    lee = round(LEE_BASE * (U_MID - powstat) / (U_MID - P_BASE), 4)
    return dict(name=name, role=role, L_lrw=L_lrw, L_hrw=L_hrw, R_L=R_L,
                powstat=powstat, L_curve=L_curve,
                L_ovfl=[(L_hrw, 0.0), (L_hrw + 1, 10.0), (L_hrw + 3, 200.0)],
                hatch_qmax=8.0, lee=lee)


VARIANTS = {
    # primary: Norwegian high head, D = 748 - 400 = 348 m
    "c5_high": spec("c5_high", 380.0, 400.0, 400.0,
                    role="primary: high head, POWSTAT_MASL = HRW(L)"),
    # head-preserving: POWSTAT 690 as in syn_rho1_R1, so the turbine side is
    # IDENTICAL to the Fase C cell; D = 748 - 690 = 58 m
    "c5_headkeep": spec("c5_headkeep", 685.0, 690.0, 690.0,
                        role="secondary: Fase C head preserved, POWSTAT_MASL = HRW(L)"),
    # positive control for the sweep ONLY: same as c5_high but the unsafe
    # datum POWSTAT_MASL = LRW(L). Geometry predicts eta_rt may exceed eta_prod
    # (by at most R_L/D) but stay < 1 since R_L/D is below the threshold.
    "c5_high_ctrl": spec("c5_high_ctrl", 380.0, 400.0, 380.0,
                         role="control: unsafe datum POWSTAT_MASL = LRW(L), sweep only"),
}


# ------------------------------------------------------------- file writing
def _read_base_series():
    with open(os.path.join(BASE, "inflowseries.txt")) as f:
        rows = [l.split() for l in f if l.strip()][1:]
    dates = [r[0] for r in rows]
    inflow_U = [r[1] for r in rows]           # kept as text: no re-rounding
    with open(os.path.join(BASE, "pricefile.txt")) as f:
        price_txt = f.read()
    return dates, inflow_U, price_txt


def write_instance(s, outroot=HERE):
    d = os.path.join(outroot, s["name"])
    os.makedirs(os.path.join(d, "output"), exist_ok=True)
    dates, inflow_U, price_txt = _read_base_series()
    D = U_LRW - s["L_hrw"]

    t = f"""##########################################################################
# C5 PART 1 -- {s['name']}   ({s['role']})
# SYNTHETIC. Closed pump-and-generate loop. Generated by
# analysis/c5_part1/build_c5.py -- do not hand-edit.
#
# U  = syn_rho1_R1 reservoir verbatim (LRW {U_LRW} HRW {U_HRW})
# L  = LRW {s['L_lrw']} HRW {s['L_hrw']}   R_L = {s['R_L']} m   D = LRW(U)-HRW(L) = {D} m
# POWSTAT_MASL = {s['powstat']}   PUMP_INLET_MASL = LRW(L) = {s['L_lrw']}
##########################################################################

NODE PUMP 0 pump_LU
PUMP_SOURCE_IDNR 3
PUMP_TARGET_IDNR 1
PUMP_INLET_MASL {s['L_lrw']}
MAX_DISCHARGE {QMAX}
HEADLOSSCOEF {HEADLOSS}
STATIC_MOTOR_EFFICIENCY {PUMP_MOTOR}
PUMP_STARTSTOP 2.0
UNIFORM_NORMALIZED_CURVE 11
"""
    for i, e in enumerate(PUMP_CURVE):
        t += f"{i/10:.1f}\t{e}\n"
    t += f"""ENDNODE

NODE RESERVOIR 1 U_SYN_RHO1_R1
HRW {U_HRW}
LRW {U_LRW}
RES_PENALTY 300
RESERVOIR_CURVE {len(U_CURVE)}
"""
    for m, v in U_CURVE:
        t += f"{m:.2f}\t{v:.6f}\n"
    t += f"OVERFLOW_CURVE {len(U_OVFL)} 3\n"
    for m, q in U_OVFL:
        t += f"{m}\t{q}\n"
    t += f"""OUTLET_HATCH -9999
OUTLET_TUNNEL 2
OUTLET_AUTO_QMIN -9999
ENDNODE

NODE PSTATION 2 sta_UL
DOWNLINK_IDNR 3
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE {len(TURB_Q)}
"""
    for q, e in zip(TURB_Q, TURB_PCT):
        t += f"{q:.2f}\t{e}\n"
    t += f"""GENERATOR_MAX_DISCHARGE {QMAX}
STATIC_GENERATOR_EFFICIENCY\t{GEN_EFF}
HEADLOSSCOEF\t{HEADLOSS}
SHARED_PENSTOCK\tTRUE
POWSTAT_MASL {s['powstat']}
POWSTAT_MIN_DISCHARGE\t1.0
POWSTAT_STARTSTOP\t2.0
LOCAL_ENERGY_EQUIVALENT\t{s['lee']}
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE

NODE RESERVOIR 3 L_LOWER
HRW {s['L_hrw']}
LRW {s['L_lrw']}
RES_PENALTY 300
RESERVOIR_CURVE {len(s['L_curve'])}
"""
    for m, v in s["L_curve"]:
        t += f"{m:.2f}\t{v:.6f}\n"
    t += f"OVERFLOW_CURVE {len(s['L_ovfl'])} 4\n"
    for m, q in s["L_ovfl"]:
        t += f"{m}\t{q}\n"
    t += f"""OUTLET_HATCH 4 0.0 {s['hatch_qmax']} {s['L_lrw']}
OUTLET_TUNNEL -9999
OUTLET_AUTO_QMIN -9999
ENDNODE

NODE CHANNEL 4 elv -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 4
QMIN -9999
ENDNODE
"""
    open(os.path.join(d, "topology.txt"), "w").write(t)
    open(os.path.join(d, "pricefile.txt"), "w").write(price_txt)
    with open(os.path.join(d, "inflowseries.txt"), "w") as f:
        f.write("Date_NodeID\t1\t3\n")
        for dt, q in zip(dates, inflow_U):
            f.write(f"{dt}\t{q}\t0.0\n")
    # actions: station 0.5 as in syn_rho1_R1, hatch shut, pump off
    with open(os.path.join(d, "actions.txt"), "w") as f:
        f.write("Date_NodeID\t2_0\t3\t0\n")
        for dt in dates:
            f.write(f"{dt}\t0.5\t0.0\t0.0\n")
    with open(os.path.join(d, "start_state.txt"), "w") as f:
        f.write("NODE PUMP 0 pump_LU 0.0\n")
        f.write("NODE RESERVOIR 1 U_SYN_RHO1_R1 0.7\n")
        f.write("NODE PSTATION 2 sta_UL 0.0\n")
        f.write("NODE RESERVOIR 3 L_LOWER 0.0\n")
        f.write("NODE CHANNEL 4 elv 0.0 0.0 0.0\n")
    with open(os.path.join(d, "global.txt"), "w") as f:
        f.write(f"""SYSTEMNAME {s['name']}
INPUTDIR ./
ACTIONFILE actions.txt
INFLOWFILE inflowseries.txt
PRICEFILE pricefile.txt
TOPOLOGYFILE topology.txt
STARTSTATEFILE start_state.txt
OUTSTATEFILE outstate.txt
WRITE_NODEFILES 0
OUTPUTDIR ./output/
PRINT_GLOBAL_INFO FALSE
PRINT_ECONOMIC_INFO FALSE
""")
    return d


# ------------------------------------------------------------ replica params
def replica_params(s):
    sys.path.insert(0, os.path.join(REPO, "analysis", "pump_audit"))
    from replica_pump import Params, Reservoir, Pstation, Pump, Channel
    nodes = {
        0: Pump(0, "pump_LU", source=3, target=1, inlet_masl=s["L_lrw"],
                max_discharge=QMAX, headlosscoef=HEADLOSS, motor_eff=PUMP_MOTOR,
                startstop=2.0, uniform_curve=[float(e) for e in PUMP_CURVE]),
        1: Reservoir(1, "U_SYN_RHO1_R1", HRW=U_HRW, LRW=U_LRW, res_penalty=300,
                     curve_masl=[m for m, _ in U_CURVE], curve_Mm3=[v for _, v in U_CURVE],
                     ovfl_masl=[m for m, _ in U_OVFL], ovfl_m3s=[q for _, q in U_OVFL],
                     ovfl_to=3, tunnel_to=2),
        2: Pstation(2, "sta_UL", downlink_to=3, curve_Q=TURB_Q,
                    curve_psnt=[float(e) for e in TURB_PCT], max_discharge=QMAX,
                    gen_eff=GEN_EFF, headlosscoef=HEADLOSS, powstat_masl=s["powstat"],
                    startstop=2.0, e_eq=s["lee"]),
        3: Reservoir(3, "L_LOWER", HRW=s["L_hrw"], LRW=s["L_lrw"], res_penalty=300,
                     curve_masl=[m for m, _ in s["L_curve"]],
                     curve_Mm3=[v for _, v in s["L_curve"]],
                     ovfl_masl=[m for m, _ in s["L_ovfl"]],
                     ovfl_m3s=[q for _, q in s["L_ovfl"]], ovfl_to=4,
                     tunnel_to=None, hatch_to=4, hatch_minQ=0.0,
                     hatch_maxQ=s["hatch_qmax"], hatch_masl=s["L_lrw"]),
        4: Channel(4, "elv", downstream_to=-9, n_linres=3, k_hours=4),
    }
    return Params(dt=86400, nodes=nodes, restprice=101.0), {4: [0.0, 0.0, 0.0]}


if __name__ == "__main__":
    for s in VARIANTS.values():
        print("built", write_instance(s), f"  POWSTAT_MASL {s['powstat']}  LEE {s['lee']}")
    print(f"eta_prod = {ETA_PROD:.6f}   threshold (1-eta)/eta = {(1-ETA_PROD)/ETA_PROD:.6f}")
