#!/usr/bin/env python
"""
Build the two single-reservoir scarcity-regime slices of data/utahps_daily:

  analysis/instances/hjelle_daily   HJELLE  + SVOLETJONN   + VANAROSEN
  analysis/instances/gresse_daily   GRESSE  + SVEIGSHYL_II + DALSANA

Everything physical is copied verbatim from data/utahps_daily/topology_utahps.txt.
The only edits are structural, and each one is forced by the simulator:

  1. Node renumbering to 0 (reservoir) / 1 (powerstation) / 2 (channel).
     riversystem.cpp:58,65,71 overwrite `nodes[n]->idnr = n` with the node's
     POSITION in the topology file -- the IDNR written in the file is not the
     key. So OUTLET_TUNNEL / DOWNLINK_IDNR / OVERFLOW_CURVE targets and the
     inflow-file column header must all follow the position, not the original id.
     riversystem.cpp:CalcVF additionally treats nodes[nr_nodes-1] as the most
     downstream node, so the channel must be last.

  2. The channel becomes the system outlet (downstream id -9), as in
     data/mini_utahps_daily.

  3. GRESSE's OVERFLOW_CURVE targets node 4 (channel GRONANI) in the full
     cascade; that node does not exist in the slice, so overflow is retargeted
     to the outlet channel (node 2). This is value-neutral: overflow water
     leaves the system either way, earns no income, and does not enter the
     terminal term (CalcVF sums local_energy_equivalent only over PSTATION
     nodes).

  4. Channel linear-reservoir initial storage is set to the steady state for
     the horizon-mean throughflow rather than the 0.001/0.002/0.003 placeholder
     inherited from mini_utahps_daily. cascadedreservoirs.cpp:106 gives
     S_{t+dt} = S_t*exp(-dt/K) + K*(1-exp(-dt/K))*I, with
     k_res = K_TRAVELTIME_HOURS*3600 / N_CASCADE_LINRES (:41), so the steady
     state under constant inflow Q is S = k_res * Q in every linear reservoir.
     The placeholder would otherwise impose a fill-up transient that differs
     between the two instances (VANAROSEN K=4h vs DALSANA K=6h).

No physical parameter is changed: reservoir curve, overflow curve, turbine
curve, HEADLOSSCOEF, GENERATOR_MAX_DISCHARGE, POWSTAT_MASL, POWSTAT_STARTSTOP,
RES_PENALTY and LOCAL_ENERGY_EQUIVALENT are byte-for-byte from utahps_daily.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "data", "utahps_daily")
OUT = os.path.join(REPO, "analysis", "instances")

DT_SECONDS = 86400


HJELLE_TOPOLOGY = """\
##########################################################################
# TOPOLOGY FILE -- HJELLE single-reservoir slice of uTAHPS
#
# Extracted verbatim from data/utahps_daily/topology_utahps.txt (nodes 0, 1, 2)
# by analysis/scarcity_gap/build_instances.py. No physical parameter changed.
# Structural edits: channel 2 VANAROSEN made the system outlet (-9).
# Node ids already 0/1/2 in the source file, so no renumbering was needed here.
##########################################################################

##########################################################################
# HJELLEVATN RESERVOIR
# NODE NODETYPE(RESERVOIR/PSTATION/CHANNEL) IDNR NAME
NODE RESERVOIR 0 HJELLE
HRW 757.0
LRW 748.0
RES_PENALTY 300
# Reservoir curve points, [masl, Mm3] Curve must go below hatch_masl.
RESERVOIR_CURVE 7
747	0.0
748	1.0
749	2.37
750	3.24
757	10.0
758	15.0
760	100
# Overflow curve, points, downstream idnr   [masl, m3s]
OVERFLOW_CURVE 3 2
757	0.0
758	10.0
760	200.0
# Outlet hatch downstream_nodeid, qmin_hatch, qmax_hatch, hatch_masl
OUTLET_HATCH -9999
OUTLET_TUNNEL 1
OUTLET_AUTO_QMIN -9999
ENDNODE
########################################################################################


#######################################################################################
# SVOLETJONN POWERSTATION HJELLEVATN IS INTAKE
NODE PSTATION 1 SVOLETJONN
DOWNLINK_IDNR 2
# Turbine efficiency curve [M3s, %]
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE 10
0.00	0
1.00	50
1.72	80
2.27	90
2.79	93
3.19	93
3.47	93
3.67	92
3.79	91
4.00	88
GENERATOR_MAX_DISCHARGE 4.0
STATIC_GENERATOR_EFFICIENCY	0.96
HEADLOSSCOEF	0.3
SHARED_PENSTOCK	TRUE
POWSTAT_MASL 690.0
POWSTAT_MIN_DISCHARGE	1.0
POWSTAT_STARTSTOP	2.0
LOCAL_ENERGY_EQUIVALENT	0.11
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE
#######################################################################################

########################################################################################
# System outlet. Downstream id -9 (was 5 = TOPPSY in the full cascade).
NODE CHANNEL 2 VANAROSEN -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 4
QMIN -9999
ENDNODE
########################################################################################
"""


GRESSE_TOPOLOGY = """\
##########################################################################
# TOPOLOGY FILE -- GRESSE single-reservoir slice of uTAHPS
#
# Extracted verbatim from data/utahps_daily/topology_utahps.txt (nodes 3, 7, 8)
# by analysis/scarcity_gap/build_instances.py. No physical parameter changed.
# Structural edits, all forced by riversystem.cpp:58,65,71 (idnr = file position):
#   reservoir   3 GRESSE       -> 0
#   pstation    7 SVEIGSHYL_II -> 1   (OUTLET_TUNNEL 7 -> 1)
#   channel     8 DALSANA      -> 2   (DOWNLINK_IDNR 8 -> 2), outlet (-9)
#   OVERFLOW_CURVE target 4 (GRONANI, not in the slice) -> 2. Value-neutral:
#   overflow leaves the system and never enters income or the terminal term.
##########################################################################

##########################################################################
# GRESSE RESERVOIR
# NODE NODETYPE(RESERVOIR/PSTATION/CHANNEL) IDNR NAME
NODE RESERVOIR 0 GRESSE
HRW 749.0
LRW 740.0
RES_PENALTY 300
# Reservoir curve points, [masl, Mm3] Curve must go below hatch_masl.
RESERVOIR_CURVE 13
725.00	20.70
730.00	46.68
735.00	75.31
740.00	106.60
741.00	113.09
743.00	126.28
745.00	139.81
748.00	160.86
749.00	168.04
750.00	175.34
751.00  180.34
752.00  200.34
755.00  500.0
# Overflow curve, points, downstream idnr   [masl, m3s]
OVERFLOW_CURVE 3 2
749.00	0.0
751.00	10.0
755.00	200.0
# Outlet hatch downstream_nodeid, qmin_hatch, qmax_hatch, hatch_masl
OUTLET_HATCH -9999
OUTLET_TUNNEL 1
OUTLET_AUTO_QMIN -9999
ENDNODE
########################################################################################

#########################################################################################
# SVEIGSHYL_II POWERSTATION GRESSE IS INTAKE
NODE PSTATION 1 SVEIGSHYL_II
DOWNLINK_IDNR 2
# Turbine efficiency curve [M3s, %]
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE 10
0.00	0
0.60	50
0.72	60
1.04	70
1.28	80
1.52	85
2.04	90
2.40	91
5.76	90
6.00	89
GENERATOR_MAX_DISCHARGE 6.0
STATIC_GENERATOR_EFFICIENCY 0.96
HEADLOSSCOEF 0.145
POWSTAT_MASL 581.0
POWSTAT_MIN_DISCHARGE 0.6
POWSTAT_MAX_DISCHARGE 6.0
POWSTAT_STARTSTOP 2.0
LOCAL_ENERGY_EQUIVALENT 0.39
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE
#########################################################################################

########################################################################################
# System outlet. Downstream id -9 (was 9 = KROKNESVATN in the full cascade).
NODE CHANNEL 2 DALSANA -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 6
QMIN -9999
ENDNODE
########################################################################################
"""


TOPPSY_TOPOLOGY = """\
##########################################################################
# TOPOLOGY FILE -- TOPPSY single-reservoir slice of uTAHPS
#
# Extracted verbatim from data/utahps_daily/topology_utahps.txt (nodes 5, 6, 8)
# by analysis/scarcity_gap/build_instances.py. No physical parameter changed.
# Structural edits, all forced by riversystem.cpp:58 (idnr = file position):
#   reservoir   5 TOPPSY       -> 0
#   pstation    6 SVEIGSHYL_I  -> 1   (OUTLET_TUNNEL 6 -> 1)
#   channel     8 DALSANA      -> 2   (DOWNLINK_IDNR 8 -> 2), outlet (-9)
#   OVERFLOW_CURVE target 8 -> 2. Value-neutral: overflow leaves the system and
#   never enters income or the terminal term.
##########################################################################

##########################################################################
# TOPPSY RESERVOIR
NODE RESERVOIR 0 TOPPSY
HRW 650.00
LRW 620.00
RES_PENALTY 300
# Reservoir curve, points, [masl, Mm3]
RESERVOIR_CURVE 10
610.00	0.0
619.00	265.00
620.00	268.53
630.00	308.33
640.00	352.87
650.00	395.17
660.00	467.73
670.00	538.94
680.00	650.00
690.00	1000.0
# Overflow curve, points, downstream idnr [masl, m3s]
OVERFLOW_CURVE 3 2
650.00	0.0
680.00	100.0
690.00	500.0
OUTLET_HATCH -9999
OUTLET_TUNNEL 1
OUTLET_AUTO_QMIN -9999
ENDNODE
########################################################################################

#########################################################################################
# SVEIGSHYL_I POWERSTATION, TOPPSY IS INTAKE
NODE PSTATION 1 SVEIGSHYL_I
DOWNLINK_IDNR 2
# Turbine efficiency curve [M3s, %]
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE 10
0.00	0.0
1.48	50.0
2.54	80.0
3.36	90.0
4.13	93.0
4.72	93.0
5.13	93.0
5.43	92.0
5.61	91.0
5.90	90.0
GENERATOR_MAX_DISCHARGE 5.9
STATIC_GENERATOR_EFFICIENCY 0.96
HEADLOSSCOEF 0.2
POWSTAT_MASL 581.0
POWSTAT_MIN_DISCHARGE 0.0
POWSTAT_MAX_DISCHARGE 5.9
POWSTAT_STARTSTOP 2.0
LOCAL_ENERGY_EQUIVALENT 0.11
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE
#########################################################################################

########################################################################################
# System outlet. Downstream id -9 (was 9 = KROKNESVATN in the full cascade).
NODE CHANNEL 2 DALSANA -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 6
QMIN -9999
ENDNODE
########################################################################################
"""


KROKNESVATN_TOPOLOGY = """\
##########################################################################
# TOPOLOGY FILE -- KROKNESVATN single-reservoir slice of uTAHPS
#
# Extracted verbatim from data/utahps_daily/topology_utahps.txt (nodes 9, 10, 11)
# by analysis/scarcity_gap/build_instances.py. No physical parameter changed.
# Structural edits, all forced by riversystem.cpp:58 (idnr = file position):
#   reservoir   9 KROKNESVATN -> 0
#   pstation   10 EASTER      -> 1   (OUTLET_TUNNEL 10 -> 1)
#   channel    11 HYNNEKLEIV  -> 2   (DOWNLINK_IDNR 11 -> 2), already the outlet
#   OVERFLOW_CURVE target 11 -> 2.
# Note N_CASCADE_LINRES 2 here, not 3 as in the other slices.
##########################################################################

##########################################################################
# KROKNESVATN RESERVOIR
NODE RESERVOIR 0 KROKNESVATN
HRW 433.00
LRW 333.00
RES_PENALTY 300
# Reservoir curve, points, [masl, Mm3]
RESERVOIR_CURVE 14
300.00	0.0
333.00	19.30
343.00	31.08
353.00	44.75
363.00	60.14
373.00	77.21
383.00	96.01
393.00	116.70
403.00	139.28
413.00	163.78
423.00	190.23
433.00	218.57
435.00  300.0
440.00  1000.0
# Overflow curve, points, downstream idnr   [masl, m3s]
OVERFLOW_CURVE 4 2
433.0	0.0
434.0	10.0
435.0	100.0
440.0	2000.0
OUTLET_HATCH -9999
OUTLET_TUNNEL 1
OUTLET_AUTO_QMIN -9999
ENDNODE
#########################################################################################

#########################################################################################
# EASTER POWERSTATION, KROKNESVATN IS INTAKE
NODE PSTATION 1 EASTER
DOWNLINK_IDNR 2
NR_GENERATORS 1
GENERATOR 0
# Turbine efficiency curve [M3s, %]
TURBINE_CURVE 10
0.00	0.00
2.45	50.00
4.21	80.00
5.59	90.00
6.86	93.00
7.84	93.00
8.53	93.00
9.02	92.00
9.31	91.00
9.80	90.00
GENERATOR_MAX_DISCHARGE 9.80
STATIC_GENERATOR_EFFICIENCY 0.96
HEADLOSSCOEF 0.145
POWSTAT_MASL 218.0
POWSTAT_MIN_DISCHARGE 0.0
POWSTAT_MAX_DISCHARGE 9.8
POWSTAT_STARTSTOP 2.0
LOCAL_ENERGY_EQUIVALENT 0.11
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE
#########################################################################################

########################################################################################
# System outlet, unchanged (-9 already in the full cascade).
NODE CHANNEL 2 HYNNEKLEIV -9
N_CASCADE_LINRES 2
K_TRAVELTIME_HOURS 4
QMIN -9999
ENDNODE
########################################################################################
"""


GLOBAL_TEMPLATE = """\
# Global configuration file for the {name} single-reservoir slice of uTAHPS.
# Generated by analysis/scarcity_gap/build_instances.py -- do not hand-edit.

SYSTEMNAME {systemname}

# Input
INPUTDIR ./
ACTIONFILE actions.txt
INFLOWFILE inflowseries.txt
PRICEFILE pricefile.txt
TOPOLOGYFILE topology.txt
STARTSTATEFILE start_state.txt

# Output information
OUTSTATEFILE outstate.txt
WRITE_NODEFILES 1
OUTPUTDIR ./output/

PRINT_GLOBAL_INFO FALSE
PRINT_ECONOMIC_INFO FALSE
"""


START_STATE_TEMPLATE = """\
# STATEFILE -- {name} single-reservoir slice of uTAHPS
# Generated by analysis/scarcity_gap/build_instances.py

# RESERVOIRS.  init_fr copied from data/utahps_daily/start_state_utahps.txt
NODE RESERVOIR 0 {res_name} {init_fr}

# NODE PSTATION IDNR NAME MWh
NODE PSTATION 1 {pst_name} 0.0

# CHANNELS.  Linear-reservoir storage initialised at the steady state for the
# horizon-mean throughflow ({mean_q:.4f} m3/s):  S = k_res * Q  with
# k_res = K_TRAVELTIME_HOURS*3600/N_CASCADE_LINRES = {k_res:.1f} s
# (cascadedreservoirs.cpp:41,106).  {n_linres} linear reservoirs,
# total channel storage = {total:.6f} Mm3.
# NODE CHANNEL IDNR NAME LINRES1_Mm3 ... LINRES{n_linres}_Mm3
NODE CHANNEL 2 {chn_name} {storages}

## END
"""


def read_utahps_columns():
    """Return (dates, {node_id: [inflow_m3s]}) from the utahps_daily inflow file."""
    with open(os.path.join(SRC, "inflowseries_utahps.txt")) as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    header = lines[0].split()
    ids = header[1:]
    dates, cols = [], {i: [] for i in ids}
    for line in lines[1:]:
        parts = line.split()
        dates.append(parts[0])
        for k, i in enumerate(ids):
            cols[i].append(float(parts[k + 1]))
    return dates, cols


def build(slug, systemname, res_name, pst_name, chn_name, topology,
          src_inflow_col, init_fr, k_hours, n_linres):
    d = os.path.join(OUT, slug)
    os.makedirs(os.path.join(d, "output"), exist_ok=True)

    dates, cols = read_utahps_columns()
    inflow = cols[src_inflow_col]
    T = len(inflow)

    with open(os.path.join(d, "topology.txt"), "w") as f:
        f.write(topology)

    with open(os.path.join(d, "global.txt"), "w") as f:
        f.write(GLOBAL_TEMPLATE.format(name=res_name, systemname=systemname))

    # Inflow: single column, renumbered to node id 0.
    with open(os.path.join(d, "inflowseries.txt"), "w") as f:
        f.write("Date_NodeID\t0\n")
        for dt, q in zip(dates, inflow):
            f.write(f"{dt}\t{q:.2f}\n")

    # Price file copied verbatim (RESTPRICE 101, T=365).
    with open(os.path.join(SRC, "pricefile_utahps.txt")) as fin:
        price_text = fin.read()
    with open(os.path.join(d, "pricefile.txt"), "w") as f:
        f.write(price_text)

    # Channel steady-state initial storage.
    mean_q = sum(inflow) / T
    k_res = k_hours * 3600.0 / n_linres
    s_Mm3 = k_res * mean_q / 1e6
    with open(os.path.join(d, "start_state.txt"), "w") as f:
        f.write(START_STATE_TEMPLATE.format(
            name=res_name, res_name=res_name, pst_name=pst_name, chn_name=chn_name,
            init_fr=init_fr, mean_q=mean_q, k_res=k_res, n_linres=n_linres,
            storages=" ".join(f"{s_Mm3:.6f}" for _ in range(n_linres)),
            total=n_linres * s_Mm3))

    # Neutral action file (constant 0.5) -- the shipped uTAHPS action file is
    # for the full cascade and is not meaningful here. Column header is
    # "<node>_<generator>" (dataset.cpp:197 colnames), i.e. "1_0" for the
    # single generator of the renumbered powerstation node 1.
    with open(os.path.join(d, "actions.txt"), "w") as f:
        f.write("Date_NodeID\t1_0\n")
        for dt in dates:
            f.write(f"{dt}\t0.5\n")

    print(f"{slug}: T={T}, mean inflow={mean_q:.4f} m3/s, "
          f"sum={sum(inflow)*DT_SECONDS/1e6:.2f} Mm3, "
          f"channel init {s_Mm3:.6f} Mm3 x{n_linres} = {n_linres*s_Mm3:.6f} Mm3")
    return d


def build_sensitivity_e163():
    """
    HJELLE with LOCAL_ENERGY_EQUIVALENT = 0.163 instead of 0.11.

    SVOLETJONN's shipped 0.11 kWh/m3 is only ~68% of the station's own full-head
    equivalent (757 -> 690 masl at ~89% combined efficiency gives ~0.163), while
    GRESSE's 0.39 is ~96% of its own. Terminal water is therefore underpriced by
    ~32% at HJELLE and ~4% at GRESSE, which confounds a HJELLE-vs-GRESSE
    comparison: the two differ in water value as well as in storage depth.

    This variant DOES change a physical parameter, deliberately and only here.
    The primary HJELLE measurement uses the shipped 0.11 unchanged.

    It must be a real instance on disk rather than a Python-side override of the
    replica: override only the replica and the real simulator optimises a
    different objective, so every cross-check silently compares two different
    value functions. That was observed -- a Python-side override produced a
    replica-minus-HERSS discrepancy of +47846 EUR, against -0.0012 EUR here.
    """
    src = os.path.join(OUT, "hjelle_daily")
    dst = os.path.join(OUT, "hjelle_daily_e163")
    os.makedirs(os.path.join(dst, "output"), exist_ok=True)

    for fn in ["inflowseries.txt", "pricefile.txt", "start_state.txt", "actions.txt"]:
        with open(os.path.join(src, fn)) as f:
            text = f.read()
        with open(os.path.join(dst, fn), "w") as f:
            f.write(text)

    with open(os.path.join(src, "global.txt")) as f:
        g = f.read().replace("SYSTEMNAME HJELLE_daily", "SYSTEMNAME HJELLE_daily_e163")
    with open(os.path.join(dst, "global.txt"), "w") as f:
        f.write(g)

    with open(os.path.join(src, "topology.txt")) as f:
        topo = f.read()
    old = "LOCAL_ENERGY_EQUIVALENT\t0.11"
    if old not in topo:
        raise RuntimeError("could not find LOCAL_ENERGY_EQUIVALENT 0.11 in hjelle topology")
    topo = topo.replace(old, "LOCAL_ENERGY_EQUIVALENT\t0.163")
    with open(os.path.join(dst, "topology.txt"), "w") as f:
        f.write(topo)

    print("hjelle_daily_e163: LOCAL_ENERGY_EQUIVALENT 0.11 -> 0.163 (sensitivity only)")
    return dst


def build_synthetic(rho_target, R_scale):
    """
    SYNTHETIC HJELLE variant for the rho/R separation grid (task C).

    This DOES change physical parameters, deliberately and only here. The
    instances live in their own directories, carry an explicit warning banner in
    every generated file, and must be kept out of any conclusion about uTAHPS.

    Two edits:
      1. The reservoir curve is scaled, V'(masl) = R_scale * V(masl), with LRW
         and HRW left at 748/757 masl. Head as a function of level is unchanged;
         the volume per metre is not. This isolates R AT CONSTANT HEAD SPAN --
         a narrower claim than isolating R, and not physically realisable.
      2. The inflow series is scaled by k so the cell lands exactly on its target
         rho. Without this, scaling the curve would drag rho along with R through
         the initial storage term, which is the confound the grid exists to
         remove. See params.synthetic_inflow_scale for the derivation.

    Everything else -- turbine curve, HEADLOSSCOEF, POWSTAT_MASL, RES_PENALTY,
    LOCAL_ENERGY_EQUIVALENT, the price file, the channel -- is HJELLE's.
    """
    import params as P

    slug = P.synthetic_slug(rho_target, R_scale)
    k = P.synthetic_inflow_scale(rho_target, R_scale)
    if k <= 0:
        raise ValueError(f"{slug}: inflow scale {k:.4f} <= 0, cell is infeasible")

    d = os.path.join(OUT, slug)
    os.makedirs(os.path.join(d, "output"), exist_ok=True)

    banner = (f"##########################################################################\n"
              f"# SYNTHETIC INSTANCE -- NOT a slice of uTAHPS. Do not mix with verbatim\n"
              f"# results. Generated by build_instances.build_synthetic().\n"
              f"#   target rho = {rho_target:g}   R scale = {R_scale:g}\n"
              f"#   reservoir curve scaled by {R_scale:g} (LRW/HRW fixed at 748/757 masl,\n"
              f"#   so head span is UNCHANGED -- this isolates R at constant head span)\n"
              f"#   inflow series scaled by {k:.6f} to hold rho at its target\n"
              f"##########################################################################\n")

    curve = P.HJELLE_DAILY.reservoir_curve_Mm3 * R_scale
    masl = P.HJELLE_DAILY.reservoir_curve_masl
    curve_lines = "\n".join(f"{m:.2f}\t{v:.6f}" for m, v in zip(masl, curve))

    topo = HJELLE_TOPOLOGY
    old_block = "\n".join([
        "RESERVOIR_CURVE 7", "747\t0.0", "748\t1.0", "749\t2.37", "750\t3.24",
        "757\t10.0", "758\t15.0", "760\t100"])
    if old_block not in topo:
        raise RuntimeError("HJELLE reservoir curve block not found; template changed")
    topo = topo.replace(old_block, f"RESERVOIR_CURVE 7\n{curve_lines}")
    topo = topo.replace("NODE RESERVOIR 0 HJELLE", f"NODE RESERVOIR 0 {slug.upper()}")
    with open(os.path.join(d, "topology.txt"), "w") as f:
        f.write(banner + topo)

    with open(os.path.join(d, "global.txt"), "w") as f:
        f.write(banner.replace("#####", "#####") +
                GLOBAL_TEMPLATE.format(name=slug, systemname=slug))

    dates, cols = read_utahps_columns()
    inflow = [q * k for q in cols["0"]]
    T = len(inflow)
    with open(os.path.join(d, "inflowseries.txt"), "w") as f:
        f.write("Date_NodeID\t0\n")
        for dt, q in zip(dates, inflow):
            f.write(f"{dt}\t{q:.6f}\n")

    with open(os.path.join(SRC, "pricefile_utahps.txt")) as fin:
        price_text = fin.read()
    with open(os.path.join(d, "pricefile.txt"), "w") as f:
        f.write(price_text)

    mean_q = sum(inflow) / T
    k_res = 4 * 3600.0 / 3
    s_Mm3 = k_res * mean_q / 1e6
    with open(os.path.join(d, "start_state.txt"), "w") as f:
        f.write(banner + START_STATE_TEMPLATE.format(
            name=slug, res_name=slug.upper(), pst_name="SVOLETJONN",
            chn_name="VANAROSEN", init_fr=P._HJELLE_INIT_FR, mean_q=mean_q,
            k_res=k_res, n_linres=3,
            storages=" ".join(f"{s_Mm3:.6f}" for _ in range(3)),
            total=3 * s_Mm3))

    with open(os.path.join(d, "actions.txt"), "w") as f:
        f.write("Date_NodeID\t1_0\n")
        for dt in dates:
            f.write(f"{dt}\t0.5\n")

    reg = P.regime_numbers(P.INSTANCES[slug])
    print(f"{slug}: inflow x{k:.4f}, curve x{R_scale:g}  ->  "
          f"rho={reg['rho']:.4f} (target {rho_target:g}), R={reg['R']:.4f}")
    return d


if __name__ == "__main__":
    build("hjelle_daily", "HJELLE_daily", "HJELLE", "SVOLETJONN", "VANAROSEN",
          HJELLE_TOPOLOGY, src_inflow_col="0", init_fr="0.7", k_hours=4, n_linres=3)
    build("gresse_daily", "GRESSE_daily", "GRESSE", "SVEIGSHYL_II", "DALSANA",
          GRESSE_TOPOLOGY, src_inflow_col="3", init_fr="0.8", k_hours=6, n_linres=3)
    # Two more cascade nodes, added 2026-08-03 to put five points on the rho/R
    # axis. Same caveat as GRESSE: a slice fed only by its own local inflow is
    # scarcer than the node is inside the full uTAHPS cascade, so rho here is a
    # LOWER bound.
    build("toppsy_daily", "TOPPSY_daily", "TOPPSY", "SVEIGSHYL_I", "DALSANA",
          TOPPSY_TOPOLOGY, src_inflow_col="5", init_fr="0.9", k_hours=6, n_linres=3)
    build("kroknesvatn_daily", "KROKNESVATN_daily", "KROKNESVATN", "EASTER",
          "HYNNEKLEIV", KROKNESVATN_TOPOLOGY, src_inflow_col="9", init_fr="0.66",
          k_hours=4, n_linres=2)
    build_sensitivity_e163()

    if "--synthetic" in sys.argv:
        import params as P
        print("\n--- SYNTHETIC rho/R grid (task C) ---")
        for rho_t, r_s in P.SYNTHETIC_PRIORITY:
            build_synthetic(rho_t, r_s)
