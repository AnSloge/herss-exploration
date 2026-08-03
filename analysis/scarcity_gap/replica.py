#!/usr/bin/env python
"""
Python replica of the HERSS single-step transition for a single-reservoir
system (reservoir node 0, powerstation node 1, outlet channel node 2).

This is a parameterised copy of analysis/mini_utahps_daily_dp/replica.py -- the
instance constants moved into params.InstanceParams so one implementation
covers mini_utahps_daily, hjelle_daily and gresse_daily. NO FORMULA IS CHANGED;
test_regression.py proves that by reproducing the mini_utahps_daily numbers to
relative 1e-6.

Every formula is cited against the C++ source at upstream commit 029a2d5
(HERSS VERSION 3.1.03 / VERSION_DATE 20260611):

  - src/reservoir.cpp     Reservoir::Simulate, CalcOverflow, InitReservoir
  - src/powerstation.cpp  Powerstation::Simulate, GetTunnelFLow
  - src/riversystem.cpp   Riversystem::CalcVF
  - src/arraycurve.cpp    ArrayCurve::x2y (piecewise-linear curve lookup)
  - src/herss.h           GRAVITY, HERSS_AGGRESSIVE_ACTIONS_COST

The channel node is not modelled: it is the most downstream node, earns no
income, and does not enter the terminal term (CalcVF sums local_energy_equivalent
over PSTATION nodes only), so it cannot affect V.

Two branches deliberately absent, both verified against source:
  - POWSTAT_MIN_DISCHARGE is a soft constraint: powerstation.cpp:160-165 only
    logs a warning, and the production-zeroing is commented out (:198, :232).
  - SHARED_PENSTOCK is irrelevant with one generator: powerstation.cpp:173 and
    :205 are identical when generators.size() == 1.

State carried between days is one scalar: `res_Mm3` at the end of the previous
day, BEFORE today's inflow. reservoir.cpp:499 uses the carried-over masl as
`start_of_stp_masl`, not a level recomputed after today's inflow -- replicated
exactly below.
"""

from dataclasses import dataclass

import numpy as np

from params import AGGRESSIVE_ACTIONS_COST, GRAVITY


def masl_from_Mm3(p, res_Mm3):
    # reservoir.cpp:545 ac_res_Mm3_2_masl.x2y(res_Mm3) -- HERSS's bucketed
    # ArrayCurve, ported exactly in arraycurve.py (NOT np.interp; see that
    # module's docstring for why the difference matters over a 365-step horizon).
    return p.curve_Mm3_2_masl.x2y(res_Mm3)


def Mm3_from_masl(p, masl):
    # reservoir.cpp:566 ac_res_masl_2_Mm3.x2y(masl)
    return p.curve_masl_2_Mm3.x2y(masl)


def overflow_m3s_from_masl(p, masl):
    # reservoir.cpp:188-199 CalcOverflow, use_overflow_curve branch
    if masl <= p.overflow_curve_masl[0]:
        return 0.0
    return p.curve_overflow.x2y(masl)


def turbine_efficiency(p, q_m3s):
    # powerstation.cpp:104 calcEfficiency -> generators[g].eff_curve.x2y(q)
    if q_m3s < 1e-6:
        return 0.0
    return p.curve_turbine.x2y(q_m3s) / 100.0


@dataclass
class StepResult:
    res_Mm3_next: float       # carried-over state for next day
    end_of_stp_masl: float    # raw masl at end of day (pre-HRW-clip)
    start_of_stp_masl: float  # HRW-clipped, as used for Hbrutto
    power_MWh: float
    income: float
    cost: float               # startstop + aggressive-action cost
    profit: float
    res_cost_lrw: float       # LRW penalty (reservoir node's own cost)
    aggressive_cost: float
    startstop_cost: float
    overflow_Mm3: float
    tunnel_flow_m3s: float
    Hnetto: float


def step(p, res_Mm3, prev_action, action, inflow_m3s, price):
    """
    One HERSS timestep for reservoir + powerstation.

    res_Mm3      volume carried from the end of the previous step
    prev_action  previous step's action, for the start/stop cost
                 (powerstation.cpp:244-258). At t=0 HERSS hardcodes this to 0.0
                 regardless of the state file (:246) -- caller passes 0.0.
    action       this step's action in [0,1]
    """
    dt = p.dt_seconds

    # --- reservoir.cpp:465-509: today's inflow; no upstream node in a slice ---
    start_of_stp_masl = masl_from_Mm3(p, res_Mm3)
    if start_of_stp_masl > p.HRW:
        start_of_stp_masl = p.HRW

    res_Mm3_after_inflow = res_Mm3 + p.m3s_to_Mm3(inflow_m3s)

    # --- reservoir.cpp:509 only water above LRW is usable for production ---
    up_res_Mm3 = max(0.0, res_Mm3_after_inflow - p.filling_at_lrw_Mm3)

    # --- powerstation.cpp:781-791 GetTunnelFLow ---
    requested_m3s = action * p.generator_max_discharge
    requested_Mm3 = p.m3s_to_Mm3(requested_m3s)

    aggressive_cost = 0.0
    if requested_Mm3 > up_res_Mm3:
        aggressive_cost = (requested_Mm3 - up_res_Mm3) * AGGRESSIVE_ACTIONS_COST
        tunnel_flow_m3s = 0.0
        tunnel_flow_Mm3 = 0.0
    else:
        tunnel_flow_m3s = requested_m3s
        tunnel_flow_Mm3 = requested_Mm3

    res_Mm3_after_tunnel = res_Mm3_after_inflow - tunnel_flow_Mm3
    masl_after_tunnel = masl_from_Mm3(p, res_Mm3_after_tunnel)

    # --- reservoir.cpp:625 overflow, evaluated at masl_after_tunnel ---
    overflow_m3s = overflow_m3s_from_masl(p, masl_after_tunnel)
    overflow_Mm3 = p.m3s_to_Mm3(overflow_m3s)
    max_overflow = res_Mm3_after_tunnel - p.filling_at_hrw_Mm3
    if overflow_Mm3 > max_overflow:
        overflow_Mm3 = max(0.0, max_overflow)

    res_Mm3_next = res_Mm3_after_tunnel - overflow_Mm3
    end_of_stp_masl = masl_from_Mm3(p, res_Mm3_next)

    # --- reservoir.cpp:649-653 LRW penalty, at the raw end-of-step masl.
    # Structurally unreachable in a single-reservoir slice: up_res_Mm3 caps the
    # withdrawal at the active volume, so res_Mm3 >= filling_at_lrw_Mm3 always.
    # Kept anyway so the replica mirrors the source, and so the measurement can
    # report the penalty as observed-zero rather than assumed-zero.
    res_cost_lrw = 0.0
    if end_of_stp_masl < p.LRW:
        res_cost_lrw = (p.RES_PENALTY * dt / 3600.0) * (p.LRW - end_of_stp_masl)

    # --- powerstation.cpp:167 Hbrutto uses avg(start,end), both HRW-clipped ---
    end_of_stp_masl_clipped = min(end_of_stp_masl, p.HRW)
    Hbrutto = (start_of_stp_masl + end_of_stp_masl_clipped) / 2.0 - p.powstat_masl

    Q = tunnel_flow_m3s
    if Q > 0.0:
        headloss = p.headlosscoef * Q * Q
        Hnetto = Hbrutto - headloss
        eta = turbine_efficiency(p, Q)
        P_MW = eta * 1000.0 * GRAVITY * Hnetto * Q / 1_000_000.0 * p.static_generator_efficiency
        power_MWh = P_MW * dt / 3600.0
        income = power_MWh * price
    else:
        Hnetto = Hbrutto
        power_MWh = 0.0
        income = 0.0

    # --- powerstation.cpp:244-258 start/stop cost ---
    startstop_cost = 0.0
    if (prev_action > 0.01) != (action > 0.01):
        startstop_cost = p.powstat_startstop / 2.0

    # riversystem.cpp:466-470 CalcVF sums S->cost[t] over ALL nodes, so the
    # reservoir's own LRW penalty is part of tot_cost_Euro. The original
    # mini_utahps_daily replica omitted it from profit while its dp.py included
    # it; the discrepancy was latent because the LRW branch never fired there.
    # Fixed here so the two agree and so an LRW violation would actually show
    # up in V rather than being silently free.
    cost = startstop_cost + aggressive_cost + res_cost_lrw
    profit = income - cost

    return StepResult(
        res_Mm3_next=res_Mm3_next,
        end_of_stp_masl=end_of_stp_masl,
        start_of_stp_masl=start_of_stp_masl,
        power_MWh=power_MWh,
        income=income,
        cost=cost,
        profit=profit,
        res_cost_lrw=res_cost_lrw,
        aggressive_cost=aggressive_cost,
        startstop_cost=startstop_cost,
        overflow_Mm3=overflow_Mm3,
        tunnel_flow_m3s=tunnel_flow_m3s,
        Hnetto=Hnetto,
    )


def remaining_active_Mm3(p, res_Mm3):
    # reservoir.cpp:664-677 fract_filling, clipped to [0, active_capacity]
    fract = (res_Mm3 - p.filling_at_lrw_Mm3) / p.active_capacity_Mm3
    if fract > 1.0:
        return p.active_capacity_Mm3
    if fract < 0.0:
        return 0.0
    return fract * p.active_capacity_Mm3


def terminal_value_Euro(p, res_Mm3_final, restprice):
    # riversystem.cpp:436,474: e_n * remaining_active_Mm3 * 1000 [MWh] * restprice
    remaining_MWh = p.local_energy_equivalent * remaining_active_Mm3(p, res_Mm3_final) * 1000.0
    return remaining_MWh * restprice


def initial_res_Mm3(p, reservoir_init_fr=None):
    # reservoir.cpp:315 res_Mm3 = filling_at_lrw + fr * (filling_at_hrw - filling_at_lrw)
    fr = p.reservoir_init_fr if reservoir_init_fr is None else reservoir_init_fr
    return p.filling_at_lrw_Mm3 + fr * p.active_capacity_Mm3


def simulate_sequence(p, actions, inflows, prices, restprice, reservoir_init_fr=None):
    """Full-horizon replica simulation; returns (VF, per-step StepResult list)."""
    res_Mm3 = initial_res_Mm3(p, reservoir_init_fr)
    prev_action = 0.0  # powerstation.cpp:246, t=0 always uses previous_action=0.0
    results = []
    total_profit = 0.0
    for a, q, price in zip(actions, inflows, prices):
        r = step(p, res_Mm3, prev_action, a, q, price)
        results.append(r)
        total_profit += r.profit
        res_Mm3 = r.res_Mm3_next
        prev_action = a
    vf = total_profit + terminal_value_Euro(p, res_Mm3, restprice)
    return vf, results
