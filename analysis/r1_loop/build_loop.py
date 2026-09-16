"""Generate a minimal CLOSED-LOOP pumped-storage instance for HERSS.

Topology (idnr order is forced by Pump::ValidatePumpSettings: the pump's idnr
must be strictly lower than BOTH its source and its target):

    0  PUMP pump_LU      PUMP_SOURCE_IDNR 3 (L)   PUMP_TARGET_IDNR 1 (U)
    1  RESERVOIR U       OUTLET_TUNNEL 2          -> feeds the station
    2  PSTATION sta_UL   DOWNLINK_IDNR 3          -> discharges into L
    3  RESERVOIR L       OUTLET_HATCH 4 (kept shut), overflow -> 4
    4  CHANNEL elv -9

So the SAME water goes L -> U through the pump and U -> L through the turbine:
a closed loop. Nothing in HERSS forbids this wiring.

Everything is linear / flat so each number has a closed form:
  - both reservoir curves are exactly 1.0 Mm3 per metre
  - the PUMP's UNIFORM_NORMALIZED_CURVE is flat (HERSS accepts this; it does
    not go through ArrayCurve)
  - the TURBINE_CURVE cannot be flat (ArrayCurve::initializeArrays hard-errors
    on ydiff < 1e-4), so it is built to hit exactly `eta_turbine` at Q = Qmax
  - HEADLOSSCOEF = 0 on both, so Hnetto == Hbrutto
"""
import os

DT_HOURS = 1
STEPS = 8
Q = 2.0                      # m3/s, same for pump and turbine


def build(name, U_lrw, U_hrw, L_lrw, L_hrw, powstat_masl,
          eta_pump=0.80, eta_motor=1.00, eta_turb=0.80, eta_gen=1.00,
          U_init_fr=0.5, L_init_fr=0.5, price=50.0, restprice=40.0,
          outdir=None):
    d = outdir or name
    os.makedirs(os.path.join(d, "output"), exist_ok=True)

    def res_curve(lrw, hrw):
        # 1.0 Mm3 per metre, with one point below LRW and one above HRW
        pts = [lrw - 1, lrw, hrw, hrw + 1]
        return pts, [10.0 + (p - lrw) for p in pts]

    Um, Uv = res_curve(U_lrw, U_hrw)
    Lm, Lv = res_curve(L_lrw, L_hrw)

    topo = f"""##########################################################################
# TOPOLOGY - {name}   (closed pumped-storage loop, R1 investigation)
#
#   pump_LU(0):  L(3) --> U(1)        head = mean(U surface) - mean(L surface)
#   sta_UL(2) :  U(1) --> L(3)        head = mean(U surface) - POWSTAT_MASL
#
# The same water goes up and comes back down. The two operations reference
# DIFFERENT lower data: the pump uses L's moving water surface, the turbine
# uses the fixed turbine centreline POWSTAT_MASL.
#
# U: LRW {U_lrw} HRW {U_hrw}   L: LRW {L_lrw} HRW {L_hrw}   POWSTAT_MASL {powstat_masl}
##########################################################################

NODE PUMP 0 pump_LU
PUMP_SOURCE_IDNR 3
PUMP_TARGET_IDNR 1
PUMP_INLET_MASL {L_lrw - 1}
MAX_DISCHARGE {Q}
HEADLOSSCOEF 0.0
STATIC_MOTOR_EFFICIENCY {eta_motor}
PUMP_STARTSTOP 0.0
UNIFORM_NORMALIZED_CURVE 11
"""
    for i in range(11):
        topo += f"{i/10.0}\t{eta_pump*100.0}\n"
    topo += f"""ENDNODE

NODE RESERVOIR 1 reservoir_U
HRW {U_hrw}
LRW {U_lrw}
RES_PENALTY 300
FLOODLEVEL_PENALTY 300
RESERVOIR_CURVE 4
"""
    for m, v in zip(Um, Uv):
        topo += f"{m}\t{v}\n"
    topo += f"""OVERFLOW_CURVE 3 4
{U_hrw}\t0.0
{U_hrw + 1}\t10.0
{U_hrw + 2}\t60.0
FAST_OVERFLOW FALSE
OUTLET_HATCH -9999
OUTLET_TUNNEL 2
OUTLET_AUTO_QMIN -9999
ENDNODE

NODE PSTATION 2 sta_UL
DOWNLINK_IDNR 3
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE 3
0.0\t0.1
{Q/2.0}\t{eta_turb*50.0}
{Q}\t{eta_turb*100.0}
GENERATOR_MAX_DISCHARGE {Q}
STATIC_GENERATOR_EFFICIENCY\t{eta_gen}
HEADLOSSCOEF\t0.0
SHARED_PENSTOCK\tTRUE
POWSTAT_MASL {powstat_masl}
POWSTAT_MIN_DISCHARGE\t0.0
POWSTAT_STARTSTOP\t0.0
LOCAL_ENERGY_EQUIVALENT\t0.1000
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE

NODE RESERVOIR 3 reservoir_L
HRW {L_hrw}
LRW {L_lrw}
RES_PENALTY 300
FLOODLEVEL_PENALTY 300
RESERVOIR_CURVE 4
"""
    for m, v in zip(Lm, Lv):
        topo += f"{m}\t{v}\n"
    topo += f"""OVERFLOW_CURVE 3 4
{L_hrw}\t0.0
{L_hrw + 1}\t10.0
{L_hrw + 2}\t60.0
FAST_OVERFLOW FALSE
OUTLET_HATCH 4 0.0 2.0 {L_lrw}
OUTLET_TUNNEL -9999
OUTLET_AUTO_QMIN -9999
ENDNODE

NODE CHANNEL 4 elv -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 1
QMIN -9999
ENDNODE
"""
    open(os.path.join(d, "topology.txt"), "w").write(topo)

    dates = [f"20260101{h:02d}" for h in range(STEPS)]
    with open(os.path.join(d, "pricefile.txt"), "w") as f:
        f.write(f"RESTPRICE\t{restprice}\nDate\tPrice\n")
        for dt in dates:
            f.write(f"{dt}\t{price}\n")
    with open(os.path.join(d, "inflowseries.txt"), "w") as f:
        f.write("Date_NodeID\t1\t3\n")
        for dt in dates:
            f.write(f"{dt}\t0.0\t0.0\n")
    with open(os.path.join(d, "actions.txt"), "w") as f:
        f.write("Date_NodeID\t2_0\t3\t0\n")
        for dt in dates:
            f.write(f"{dt}\t0.0\t0.0\t0.0\n")
    with open(os.path.join(d, "start_state.txt"), "w") as f:
        f.write("NODE PUMP 0 pump_LU 0.0\n")
        f.write(f"NODE RESERVOIR 1 reservoir_U {U_init_fr}\n")
        f.write("NODE PSTATION 2 sta_UL 0.0\n")
        f.write(f"NODE RESERVOIR 3 reservoir_L {L_init_fr}\n")
        f.write("NODE CHANNEL 4 elv 0.0 0.0 0.0\n")
    with open(os.path.join(d, "global.txt"), "w") as f:
        f.write(f"""SYSTEMNAME {name}
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


if __name__ == "__main__":
    p = build("inst_loop", U_lrw=200, U_hrw=220, L_lrw=100, L_hrw=120,
              powstat_masl=100.0)
    print("built", p)
