#!/usr/bin/env python
"""
Python replica of the HERSS single-step transition for res_casc_A:

    RES_A (0) --hatch--> RES_B (1) --tunnel--> PSTAT_B (4, two generators)

Every formula is cited against the C++ source at upstream commit 029a2d5
(HERSS VERSION 3.1.03 / VERSION_DATE 20260611):

  src/reservoir.cpp      Reservoir::Simulate (:428-716), CalcOverflow (:206-275),
                         InitReservoir (:295-360)
  src/powerstation.cpp   Powerstation::Simulate (:110-307), GetTunnelFLow (:746-793),
                         calcEfficiency (:70-106)
  src/herss.cpp          Herss::Simulate node loop (:660-677), terminal
                         accumulation (:683-693)
  src/riversystem.cpp    Riversystem::CalcVF (:406-480)
  src/arraycurve.cpp     ArrayCurve::x2y  (ported in scarcity_gap/arraycurve.py)

Structure of a timestep, in the order HERSS executes it. Node order is idnr
order (herss.cpp:667), so RES_A runs before RES_B and its hatch release lands in
RES_B's up_inflow[t] in the SAME timestep (reservoir.cpp:573).

The three channels are not modelled. They earn no income, their only cost is the
QMIN penalty (off in all three), and all sit downstream of PSTAT_B so none enters
its upstream_remaining_active_Mm3. build_res_casc_A.py verifies this empirically:
changing every channel's initial storage moves V by exactly 0.0000.

Branches deliberately absent, each verified in source:
  - POWSTAT_MIN_DISCHARGE is a soft constraint: powerstation.cpp:157-164 only
    logs a warning, the production-zeroing is commented out (:198, :232).
  - OUTLET_AUTO_QMIN and MAX_ADJUST are -9999 (off) in this topology.
  - FLOODLEVEL_PENALTY is read from file but never applied (CLAUDE.md section 9).
  - FAST_OVERFLOW is FALSE, so CalcOverflow takes the overflow-curve branch.

Two details that a "reasonable" reimplementation would get wrong:

  1. The hatch clip goes through a curve ROUND TRIP. reservoir.cpp:565 computes
     current_filling = ac_res_masl_2_Mm3.x2y(res_masl) where res_masl was itself
     produced by ac_res_Mm3_2_masl.x2y(res_Mm3). Because ArrayCurve is a
     1000-bucket lookup and not an exact inverse pair, that round trip is NOT the
     identity. The overflow clip at :659 uses raw res_Mm3 instead. Both are
     replicated as written.

  2. The hatch volume crosses the node boundary as a FLOW: reservoir.cpp:573
     converts Mm3 -> m3/s, and reservoir.cpp:477 converts it back. The round trip
     is reproduced rather than short-circuited.
"""

from dataclasses import dataclass
from typing import Sequence, Tuple

from params2 import AGGRESSIVE_ACTIONS_COST, GRAVITY


# ---------------------------------------------------------------- curve helpers

def masl_from_Mm3(r, Mm3):
    # reservoir.cpp:545,600 ac_res_Mm3_2_masl.x2y(res_Mm3)
    return r.curve_Mm3_2_masl.x2y(Mm3)


def Mm3_from_masl(r, masl):
    # reservoir.cpp:565 ac_res_masl_2_Mm3.x2y(res_masl)
    return r.curve_masl_2_Mm3.x2y(masl)


def calc_overflow_Mm3(p, r, masl, res_Mm3):
    """
    reservoir.cpp:206-274 Reservoir::CalcOverflow, use_overflow_curve branch
    (FAST_OVERFLOW is FALSE for both reservoirs here).

    The structure matters and is easy to get wrong: the HRW clip at :262-264 sits
    INSIDE the `res_masl > masl_start_overflow` guard. Below that level the
    function returns 0.0 at :264 without touching the clip. Hoisting the clip out
    of the guard makes `overflow = res_Mm3 - filling_at_hrw` fire with a negative
    value whenever the reservoir is below HRW, which SUBTRACTS a negative volume
    and pins the reservoir at exactly HRW forever.

    The clip compares against RAW res_Mm3 (:261), not a curve round trip -- unlike
    the hatch clip, which does round trip.

    HERSS treats a negative result as fatal (LOG_ERR at :260). It can only arise
    in the narrow band where the ArrayCurve round trip disagrees about whether the
    reservoir is above HRW. The replica returns it unchanged so the caller can
    detect it rather than silently diverging from the simulator.
    """
    if masl <= r.overflow_masl[0]:
        return 0.0
    overflow_Mm3 = p.m3s_to_Mm3(r.curve_overflow.x2y(masl))
    max_overflow = res_Mm3 - r.filling_at_hrw_Mm3
    if overflow_Mm3 > max_overflow:
        overflow_Mm3 = max_overflow
    return overflow_Mm3


def turbine_efficiency(st, q_m3s):
    # powerstation.cpp:85-87 returns 0 below 1e-6; :104 eff_curve.x2y(q)/100.
    # use_uniform_normalized_curve is false here: it is only set by a
    # UNIFORM_NORMALIZED_CURVE keyword (:473), and this topology uses
    # TURBINE_CURVE.
    if q_m3s < 0.000001:
        return 0.0
    return st.curve_turbine.x2y(q_m3s) / 100.0


def remaining_active_Mm3(r, res_Mm3):
    # reservoir.cpp:664-677 fract_filling, clipped to [0, active_capacity]
    fract = (res_Mm3 - r.filling_at_lrw_Mm3) / r.active_capacity_Mm3
    if fract > 1.0:
        return r.active_capacity_Mm3
    if fract < 0.0:
        return 0.0
    return fract * r.active_capacity_Mm3


# ---------------------------------------------------------------- step

@dataclass
class StepResult:
    res_A_Mm3_next: float
    res_B_Mm3_next: float
    masl_A_end: float
    masl_B_end: float
    start_masl_B: float          # what PSTAT_B sees as start_of_stp_masl
    end_masl_B: float            # HRW-clipped, as used for Hbrutto
    hatchflow_Mm3: float
    overflow_A_Mm3: float
    overflow_B_Mm3: float
    tunnelflow_m3s: float
    total_Q: float
    Q_gen: Tuple[float, ...]
    power_MWh: float
    income: float
    cost: float
    profit: float
    aggressive_cost: float
    startstop_cost: float
    lrw_cost_A: float
    lrw_cost_B: float
    Hbrutto: float
    Hnetto: float


def step(p, res_A_Mm3, res_B_Mm3, prev_actions, a_hatch, a_gen,
         inflow_A_m3s, inflow_B_m3s, price):
    """
    One HERSS timestep.

    res_A_Mm3, res_B_Mm3  volumes carried from the end of the previous step
    prev_actions          previous step's generator actions, for the start/stop
                          cost. At t=0 HERSS hardcodes these to 0.0 regardless of
                          the state file (powerstation.cpp:243-245).
    a_hatch               RES_A hatch action in [0,1]
    a_gen                 sequence of generator actions in [0,1]
    """
    A, B, st = p.upper, p.lower, p.station
    dt = p.dt_seconds

    # ================================================== RES_A (node 0)
    # reservoir.cpp:465-476. res_masl is NOT refreshed after inflow (:483 is
    # commented out), but RES_A has no tunnel, so the first thing that reads it
    # is the post-tunnel refresh at :538-544 below.
    res_A = res_A_Mm3 + p.m3s_to_Mm3(inflow_A_m3s)

    # :536 res_Mm3 -= tunnelflow (zero here), then :538-544 refresh masl
    masl_A = masl_from_Mm3(A, res_A)

    # --- :551-575 OUTLET HATCH -------------------------------------------------
    hatchflow_Mm3 = 0.0
    if masl_A > A.hatch_masl:
        # :564 qmin + action*(qmax-qmin), in m3/s, then converted
        hatch_m3s = A.hatch_qmin + a_hatch * (A.hatch_qmax - A.hatch_qmin)
        hatchflow_Mm3 = p.m3s_to_Mm3(hatch_m3s)
        # :565-567 NOTE the curve round trip -- see module docstring
        current_filling = Mm3_from_masl(A, masl_A)
        max_hatchflow = current_filling - A.filling_at_hatch_Mm3
        if hatchflow_Mm3 > max_hatchflow:
            hatchflow_Mm3 = max_hatchflow
    # :573 the volume crosses the node boundary as a flow, and :477 converts back
    hatch_up_inflow_m3s = p.Mm3_to_m3s(hatchflow_Mm3)
    res_A -= hatchflow_Mm3

    # :576-582 then :595-604 refresh masl (no auto-qmin here)
    masl_A = masl_from_Mm3(A, res_A)

    # --- :625-637 overflow -----------------------------------------------------
    overflow_A_Mm3 = calc_overflow_Mm3(p, A, masl_A, res_A)
    res_A -= overflow_A_Mm3
    masl_A_end = masl_from_Mm3(A, res_A)

    # --- :645-653 LRW penalty --------------------------------------------------
    lrw_cost_A = 0.0
    if masl_A_end < A.LRW:
        lrw_cost_A = (A.RES_PENALTY * dt / 3600.0) * (A.LRW - masl_A_end)

    # ================================================== RES_B (node 1)
    # :499-503 the powerstation's start_of_stp_masl is the STALE masl, i.e. the
    # level at the end of the previous step, before today's inflow.
    start_masl_B = masl_from_Mm3(B, res_B_Mm3)
    if start_masl_B > B.HRW:
        start_masl_B = B.HRW

    # :474-478 local inflow and upstream inflow are added separately
    res_B = res_B_Mm3 + p.m3s_to_Mm3(inflow_B_m3s)
    res_B += p.m3s_to_Mm3(hatch_up_inflow_m3s)

    # :509 only water above LRW is usable for production
    up_res_Mm3 = max(0.0, res_B - B.filling_at_lrw_Mm3)

    # --- powerstation.cpp:746-793 GetTunnelFLow --------------------------------
    total_action = sum(a_gen)
    if total_action < 0.0000001:
        flow = 0.0
    else:
        flow = sum(a * st.max_discharge for a in a_gen)

    aggressive_cost = 0.0
    Q_Mm3 = p.m3s_to_Mm3(flow)
    if Q_Mm3 > up_res_Mm3:
        aggressive_cost = (Q_Mm3 - up_res_Mm3) * AGGRESSIVE_ACTIONS_COST
        flow = 0.0

    tunnelflow_m3s = flow
    tunnelflow_Mm3 = p.m3s_to_Mm3(tunnelflow_m3s)
    res_B -= tunnelflow_Mm3
    masl_B = masl_from_Mm3(B, res_B)

    # --- overflow --------------------------------------------------------------
    overflow_B_Mm3 = calc_overflow_Mm3(p, B, masl_B, res_B)
    res_B -= overflow_B_Mm3
    masl_B_end = masl_from_Mm3(B, res_B)

    lrw_cost_B = 0.0
    if masl_B_end < B.LRW:
        lrw_cost_B = (B.RES_PENALTY * dt / 3600.0) * (B.LRW - masl_B_end)

    # :655-661 the powerstation's end_of_stp_masl, HRW-clipped
    end_masl_B = min(masl_B_end, B.HRW)

    # ================================================== PSTAT_B (node 4)
    # powerstation.cpp:128-140 recompute per-generator flow from the actions
    Q_gen = [a * st.max_discharge for a in a_gen]
    total_Q = sum(Q_gen)

    # :144-153 second aggressive guard: up_inflow[t] is the (possibly zeroed)
    # tunnel flow, so this fires exactly when GetTunnelFLow zeroed the release.
    if total_Q > tunnelflow_m3s * 1.000001:
        total_Q = 0.0
        Q_gen = [0.0] * len(Q_gen)

    # :167 Hbrutto from the average of start and end level
    Hbrutto = (start_masl_B + end_masl_B) / 2.0 - st.powstat_masl

    power_MWh = 0.0
    income = 0.0
    if st.shared_penstock:
        # :173-175 head loss on the COMBINED flow, one Hnetto for all generators
        Hnetto = Hbrutto - st.headlosscoef * total_Q * total_Q
        for q in Q_gen:
            eta = turbine_efficiency(st, q)
            P_MW = eta * 1000.0 * GRAVITY * Hnetto * q / 1_000_000.0
            P_MW *= st.static_gen_efficiency
            mwh = P_MW * dt / 3600.0
            power_MWh += mwh
            income += mwh * price
    else:
        Hnetto = Hbrutto
        for q in Q_gen:
            Hn = Hbrutto - st.headlosscoef * q * q
            eta = turbine_efficiency(st, q)
            P_MW = eta * 1000.0 * GRAVITY * Hn * q / 1_000_000.0
            P_MW *= st.static_gen_efficiency
            mwh = P_MW * dt / 3600.0
            power_MWh += mwh
            income += mwh * price
        Hnetto = Hbrutto - st.headlosscoef * total_Q * total_Q

    # :240-258 start/stop cost, counted PER GENERATOR
    startstop_cost = 0.0
    for prev, cur in zip(prev_actions, a_gen):
        if (prev > 0.01) != (cur > 0.01):
            startstop_cost += st.powstat_startstop / 2.0

    # riversystem.cpp:466-470 CalcVF sums S->cost[t] over ALL nodes, so both
    # reservoirs' LRW penalties are part of tot_cost_Euro alongside the station's
    # start/stop and aggressive-action costs.
    cost = startstop_cost + aggressive_cost + lrw_cost_A + lrw_cost_B
    profit = income - cost

    return StepResult(
        res_A_Mm3_next=res_A, res_B_Mm3_next=res_B,
        masl_A_end=masl_A_end, masl_B_end=masl_B_end,
        start_masl_B=start_masl_B, end_masl_B=end_masl_B,
        hatchflow_Mm3=hatchflow_Mm3,
        overflow_A_Mm3=overflow_A_Mm3, overflow_B_Mm3=overflow_B_Mm3,
        tunnelflow_m3s=tunnelflow_m3s, total_Q=total_Q, Q_gen=tuple(Q_gen),
        power_MWh=power_MWh, income=income, cost=cost, profit=profit,
        aggressive_cost=aggressive_cost, startstop_cost=startstop_cost,
        lrw_cost_A=lrw_cost_A, lrw_cost_B=lrw_cost_B,
        Hbrutto=Hbrutto, Hnetto=Hnetto,
    )


# ---------------------------------------------------------------- horizon

def terminal_value_Euro(p, res_A_Mm3, res_B_Mm3, restprice):
    """
    riversystem.cpp:436,474 -- e_n * upstream_remaining_active_Mm3 * 1000 [MWh],
    summed over PSTATION nodes.

    RES_A is NOT in PSTAT_B's upstream chain: herss.cpp:691 walks
    ptr_downstream_node, and reservoir.cpp:1065-1073 sets that to the OVERFLOW
    target for a reservoir without a tunnel, so RES_A's chain is 0 -> 2 -> 5.
    Its stored water is therefore worth zero. See params2.py for the empirical
    confirmation in the shipped output file.

    p.value_upper_storage=True is the synthetic corrected variant (task A4) and
    must never be mixed with verbatim results.
    """
    active = remaining_active_Mm3(p.lower, res_B_Mm3)
    if p.value_upper_storage:
        active += remaining_active_Mm3(p.upper, res_A_Mm3)
    return p.station.local_energy_equivalent * active * 1000.0 * restprice


def initial_state(p, init_fr=None):
    """(res_A_Mm3, res_B_Mm3) from reservoir.cpp:315."""
    fr = init_fr or {}
    return (p.upper.init_Mm3(fr.get(p.upper.idnr)),
            p.lower.init_Mm3(fr.get(p.lower.idnr)))


def simulate_sequence(p, actions, inflow_A, inflow_B, prices, restprice, init_fr=None):
    """
    Full-horizon replica simulation.

    actions: {"hatch": [...], "g0": [...], "g1": [...]}
    Returns (VF, [StepResult]).
    """
    n_gen = p.station.n_generators
    hatch = actions["hatch"]
    gens = [actions[f"g{g}"] for g in range(n_gen)]

    res_A, res_B = initial_state(p, init_fr)
    prev = (0.0,) * n_gen        # powerstation.cpp:243-245, t=0 uses 0.0
    results = []
    total_profit = 0.0

    for t in range(len(prices)):
        a_gen = tuple(gens[g][t] for g in range(n_gen))
        r = step(p, res_A, res_B, prev, hatch[t], a_gen,
                 inflow_A[t], inflow_B[t], prices[t])
        results.append(r)
        total_profit += r.profit
        res_A, res_B = r.res_A_Mm3_next, r.res_B_Mm3_next
        prev = a_gen

    vf = total_profit + terminal_value_Euro(p, res_A, res_B, restprice)
    return vf, results
