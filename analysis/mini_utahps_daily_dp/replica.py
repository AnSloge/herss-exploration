#!/usr/bin/env python
"""
Python replica of the HERSS single-step transition for mini_utahps_daily
(node 0 = HJELLE reservoir, node 1 = SVOLETJONN powerstation, node 2 = channel).

This exists because HERSS only exposes whole-horizon Simulate(); an exact DP
needs a single-step transition function. Every formula here is copied from,
and cited against, the C++ source at upstream commit 029a2d5
(HERSS VERSION 3.1.03 / VERSION_DATE 20260611):

  - src/reservoir.cpp   Reservoir::Simulate, CalcOverflow, InitReservoir
  - src/powerstation.cpp Powerstation::Simulate, GetTunnelFLow
  - src/riversystem.cpp  Riversystem::CalcVF
  - src/arraycurve.cpp   ArrayCurve::x2y (piecewise-linear curve lookup)
  - src/herss.h          constants: GRAVITY, HERSS_AGGRESSIVE_ACTIONS_COST,
                          MACRO_m3s_2_Mm3, MACRO_Mm3_2_m3s

The channel node (id 2) is not modelled: CLAUDE.md/riversystem.cpp confirm its
income and remaining_active_Mm3 are always 0, and it is the most-downstream
node, so it cannot affect V for this single-reservoir/single-station system.

State carried between days is exactly one scalar: `res_Mm3` (reservoir volume
at the end of the previous day / start of the current day, before today's
inflow is added). `res_masl` is always re-derivable from `res_Mm3` via the
reservoir curve. See reservoir.cpp:499 (`start_of_stp_masl` uses the reservoir's
*carried-over* masl from the end of the previous day, not a level recomputed
after today's inflow is added) -- replicated exactly below.
"""

from dataclasses import dataclass

import numpy as np

# ---- topology.txt constants (data/mini_utahps_daily/topology.txt) ----

GRAVITY = 9.80665
AGGRESSIVE_ACTIONS_COST = 1000.0  # herss.h HERSS_AGGRESSIVE_ACTIONS_COST
DT_SECONDS = 86400  # daily resolution, confirmed via pricefile timestamps

# HJELLE reservoir
HRW = 757.0
LRW = 748.0
RES_PENALTY = 300.0
RESERVOIR_CURVE_MASL = np.array([747, 748, 749, 750, 757, 758, 760], dtype=float)
RESERVOIR_CURVE_MM3 = np.array([0.0, 1.0, 2.37, 3.24, 10.0, 15.0, 500.0], dtype=float)
OVERFLOW_CURVE_MASL = np.array([757, 758, 760], dtype=float)
OVERFLOW_CURVE_M3S = np.array([0.0, 10.0, 200.0], dtype=float)

# SVOLETJONN powerstation
GENERATOR_MAX_DISCHARGE = 4.0  # m3/s
STATIC_GENERATOR_EFFICIENCY = 0.96
HEADLOSSCOEF = 0.3
POWSTAT_MASL = 690.0
POWSTAT_STARTSTOP = 2.0
LOCAL_ENERGY_EQUIVALENT = 0.11  # kWh/m3
TURBINE_CURVE_Q = np.array([0.00, 1.00, 1.72, 2.27, 2.79, 3.19, 3.47, 3.67, 3.79, 4.00])
TURBINE_CURVE_PCT = np.array([0, 50, 80, 90, 93, 93, 93, 92, 91, 88], dtype=float)

FILLING_AT_LRW_MM3 = float(np.interp(LRW, RESERVOIR_CURVE_MASL, RESERVOIR_CURVE_MM3))
FILLING_AT_HRW_MM3 = float(np.interp(HRW, RESERVOIR_CURVE_MASL, RESERVOIR_CURVE_MM3))
ACTIVE_CAPACITY_MM3 = FILLING_AT_HRW_MM3 - FILLING_AT_LRW_MM3


def m3s_to_Mm3(q_m3s, dt=DT_SECONDS):
    return q_m3s * dt / 1_000_000.0


def Mm3_to_m3s(q_Mm3, dt=DT_SECONDS):
    return q_Mm3 * 1_000_000.0 / dt


def masl_from_Mm3(res_Mm3):
    # reservoir.cpp:545 ac_res_Mm3_2_masl.x2y(res_Mm3) -- true piecewise-linear
    # interpolation. HERSS's ArrayCurve quantizes onto a 1000-point lookup
    # table (arraycurve.h POINTS_IN_ARRAY=1000); the resulting error against
    # true interpolation is negligible (< 1e-3 of the curve's masl span) and
    # validated empirically in validate.py.
    return float(np.interp(res_Mm3, RESERVOIR_CURVE_MM3, RESERVOIR_CURVE_MASL))


def Mm3_from_masl(masl):
    return float(np.interp(masl, RESERVOIR_CURVE_MASL, RESERVOIR_CURVE_MM3))


def overflow_m3s_from_masl(masl):
    # reservoir.cpp:188-199 CalcOverflow, use_overflow_curve branch (FAST_OVERFLOW FALSE)
    if masl <= OVERFLOW_CURVE_MASL[0]:
        return 0.0
    return float(np.interp(masl, OVERFLOW_CURVE_MASL, OVERFLOW_CURVE_M3S))


def turbine_efficiency(q_m3s):
    # powerstation.cpp calcEfficiency: TURBINE_CURVE branch, ArrayCurve.x2y
    if q_m3s < 1e-6:
        return 0.0
    return float(np.interp(q_m3s, TURBINE_CURVE_Q, TURBINE_CURVE_PCT)) / 100.0


@dataclass
class StepResult:
    res_Mm3_next: float       # carried-over state for next day
    end_of_stp_masl: float    # raw masl at end of day (pre-HRW-clip, informational)
    power_MWh: float
    income: float
    cost: float               # startstop + aggressive-action cost (powerstation)
    profit: float
    res_cost_lrw: float       # LRW penalty (reservoir node's own cost)
    aggressive_cost: float
    startstop_cost: float
    overflow_Mm3: float
    tunnel_flow_m3s: float


def step(res_Mm3, prev_action, action, inflow_m3s, price, dt=DT_SECONDS):
    """
    One HERSS day for HJELLE + SVOLETJONN.

    res_Mm3: reservoir volume carried from the end of the previous day
        (= start_of_stp_masl input state; reservoir.cpp:465-509).
    prev_action: yesterday's action in [0,1] (for start/stop cost;
        powerstation.cpp:244-258). At t=0 HERSS hardcodes this to 0.0
        regardless of the state file (documented code/manual mismatch,
        report section 4.2) -- caller must pass 0.0 for t=0.
    action: today's action in [0,1].
    """
    # --- reservoir.cpp:465-476: add today's inflow (local reservoir has no
    # upstream node, so up_inflow[t] == 0 always for HJELLE) ---
    start_of_stp_masl = masl_from_Mm3(res_Mm3)  # yesterday's end-of-day masl (carried, NOT re-derived post-inflow)
    if start_of_stp_masl > HRW:
        start_of_stp_masl = HRW

    res_Mm3_after_inflow = res_Mm3 + m3s_to_Mm3(inflow_m3s, dt)

    # --- reservoir.cpp:509 up_res_Mm3 = max(0, res_Mm3 - filling_at_lrw) ---
    up_res_Mm3 = max(0.0, res_Mm3_after_inflow - FILLING_AT_LRW_MM3)

    # --- powerstation.cpp GetTunnelFLow: requested flow from the action ---
    requested_m3s = action * GENERATOR_MAX_DISCHARGE
    requested_Mm3 = m3s_to_Mm3(requested_m3s, dt)

    aggressive_cost = 0.0
    if requested_Mm3 > up_res_Mm3:
        aggressive_cost = (requested_Mm3 - up_res_Mm3) * AGGRESSIVE_ACTIONS_COST
        tunnel_flow_m3s = 0.0
        tunnel_flow_Mm3 = 0.0
    else:
        tunnel_flow_m3s = requested_m3s
        tunnel_flow_Mm3 = requested_Mm3

    res_Mm3_after_tunnel = res_Mm3_after_inflow - tunnel_flow_Mm3
    masl_after_tunnel = masl_from_Mm3(res_Mm3_after_tunnel)

    # --- reservoir.cpp:625 overflow, evaluated at masl_after_tunnel ---
    overflow_m3s = overflow_m3s_from_masl(masl_after_tunnel)
    overflow_Mm3 = m3s_to_Mm3(overflow_m3s, dt)
    max_overflow = res_Mm3_after_tunnel - FILLING_AT_HRW_MM3
    if overflow_Mm3 > max_overflow:
        overflow_Mm3 = max(0.0, max_overflow)

    res_Mm3_next = res_Mm3_after_tunnel - overflow_Mm3
    end_of_stp_masl = masl_from_Mm3(res_Mm3_next)

    # --- reservoir.cpp:649-653 LRW penalty, evaluated at raw end-of-day masl ---
    res_cost_lrw = 0.0
    if end_of_stp_masl < LRW:
        res_cost_lrw = (RES_PENALTY * dt / 3600.0) * (LRW - end_of_stp_masl)

    # --- powerstation.cpp:167 Hbrutto uses avg(start,end), both HRW-clipped ---
    end_of_stp_masl_clipped = min(end_of_stp_masl, HRW)
    Hbrutto = (start_of_stp_masl + end_of_stp_masl_clipped) / 2.0 - POWSTAT_MASL

    Q = tunnel_flow_m3s
    if Q > 0.0:
        headloss = HEADLOSSCOEF * Q * Q  # shared_penstock branch; only 1 generator so equivalent either way
        Hnetto = Hbrutto - headloss
        eta = turbine_efficiency(Q)
        P_MW = eta * 1000.0 * GRAVITY * Hnetto * Q / 1_000_000.0 * STATIC_GENERATOR_EFFICIENCY
        power_MWh = P_MW * dt / 3600.0
        income = power_MWh * price
    else:
        power_MWh = 0.0
        income = 0.0

    # --- powerstation.cpp:244-258 start/stop cost ---
    startstop_cost = 0.0
    if (prev_action > 0.01) != (action > 0.01):
        startstop_cost = POWSTAT_STARTSTOP / 2.0

    cost = startstop_cost + aggressive_cost
    profit = income - cost

    return StepResult(
        res_Mm3_next=res_Mm3_next,
        end_of_stp_masl=end_of_stp_masl,
        power_MWh=power_MWh,
        income=income,
        cost=cost,
        profit=profit,
        res_cost_lrw=res_cost_lrw,
        aggressive_cost=aggressive_cost,
        startstop_cost=startstop_cost,
        overflow_Mm3=overflow_Mm3,
        tunnel_flow_m3s=tunnel_flow_m3s,
    )


def remaining_active_Mm3(res_Mm3):
    # reservoir.cpp:664-677 fract_filling, clipped to [0, active_capacity]
    fract_filling = (res_Mm3 - FILLING_AT_LRW_MM3) / ACTIVE_CAPACITY_MM3
    if fract_filling > 1.0:
        return ACTIVE_CAPACITY_MM3
    if fract_filling < 0.0:
        return 0.0
    return fract_filling * ACTIVE_CAPACITY_MM3


def terminal_value_Euro(res_Mm3_final, restprice):
    # riversystem.cpp:436,474: e_n * remaining_active_Mm3 * 1000 [MWh], * restprice
    remaining_MWh = LOCAL_ENERGY_EQUIVALENT * remaining_active_Mm3(res_Mm3_final) * 1000.0
    return remaining_MWh * restprice


def initial_res_Mm3(reservoir_init_fr):
    # reservoir.cpp:315 res_Mm3 = filling_at_lrw + fr * (filling_at_hrw - filling_at_lrw)
    return FILLING_AT_LRW_MM3 + reservoir_init_fr * ACTIVE_CAPACITY_MM3


def simulate_sequence(actions, inflows, prices, reservoir_init_fr, restprice, dt=DT_SECONDS):
    """Full-horizon replica simulation; returns (VF, per-day StepResult list)."""
    res_Mm3 = initial_res_Mm3(reservoir_init_fr)
    prev_action = 0.0  # powerstation.cpp:246: t=0 always uses previous_action=0.0
    results = []
    total_profit = 0.0
    for t, (a, q, p) in enumerate(zip(actions, inflows, prices)):
        r = step(res_Mm3, prev_action, a, q, p, dt)
        results.append(r)
        total_profit += r.profit
        res_Mm3 = r.res_Mm3_next
        prev_action = a
    vf = total_profit + terminal_value_Euro(res_Mm3, restprice)
    return vf, results
