#!/usr/bin/env python
"""
Exact DP for a single-reservoir HERSS instance: backward induction over a
discretized reservoir-storage grid (one state dimension -- the outlet channel
cannot affect V, see replica.py) plus a binary on/off dimension carrying the
start/stop cost, with the action discretized over [0,1].

Parameterised copy of analysis/mini_utahps_daily_dp/dp.py. The transition
formulas mirror replica.py branch for branch; the only change is block
vectorization over (state x action) and the observation that `profit` and
`res_next` do not depend on prev_onoff -- only the start/stop term does -- so
the expensive block is computed once per timestep instead of twice.

replica.py remains the single source of truth for the scalar transition;
check_against_replica() verifies this module against it before any DP result
is trusted.
"""

import numpy as np

import replica as R
from params import AGGRESSIVE_ACTIONS_COST, GRAVITY


def vec_masl_from_Mm3(p, Mm3):
    return p.curve_Mm3_2_masl.x2y(Mm3)


def vec_overflow_m3s_from_masl(p, masl):
    q = p.curve_overflow.x2y(masl)
    return np.where(masl <= p.overflow_curve_masl[0], 0.0, q)


def vec_turbine_efficiency(p, q_m3s):
    eta = p.curve_turbine.x2y(q_m3s) / 100.0
    return np.where(q_m3s < 1e-6, 0.0, eta)


def vec_remaining_active_Mm3(p, res_Mm3):
    fract = (res_Mm3 - p.filling_at_lrw_Mm3) / p.active_capacity_Mm3
    return np.clip(fract, 0.0, 1.0) * p.active_capacity_Mm3


def vec_terminal_value_Euro(p, res_Mm3, restprice):
    remaining_MWh = p.local_energy_equivalent * vec_remaining_active_Mm3(p, res_Mm3) * 1000.0
    return remaining_MWh * restprice


def transition_block(p, S, actions, inflow_m3s, price, frozen_masl=None):
    """
    Vectorized replica.step() over the outer product of states S (shape (N,))
    and actions (shape (A,)), for one timestep.

    Returns (profit_no_startstop, res_next, on), each shape (N, A):
      profit_no_startstop  income - aggressive_cost - res_cost_lrw
      res_next             carried state for the next step
      on                   bool, whether the action counts as "on" (>0.01)

    The start/stop term is added by the caller because it is the only part that
    depends on prev_onoff.

    frozen_masl: if given, Hbrutto is computed from this fixed level instead of
    the trajectory's own levels. Used only by the (b) "level modulation" run of
    the gap decomposition, with an EXOGENOUS level (LRW/HRW midpoint), never a
    level read off the DP optimum.
    """
    dt = p.dt_seconds
    S = S[:, None]
    a = actions[None, :]

    start_masl = np.minimum(vec_masl_from_Mm3(p, S), p.HRW)

    res_after_inflow = S + p.m3s_to_Mm3(inflow_m3s)
    up_res_Mm3 = np.maximum(0.0, res_after_inflow - p.filling_at_lrw_Mm3)

    requested_m3s = a * p.generator_max_discharge
    requested_Mm3 = p.m3s_to_Mm3(requested_m3s)

    aggressive = requested_Mm3 > up_res_Mm3
    aggressive_cost = np.where(aggressive,
                               (requested_Mm3 - up_res_Mm3) * AGGRESSIVE_ACTIONS_COST, 0.0)
    tunnel_flow_m3s = np.where(aggressive, 0.0, requested_m3s)
    tunnel_flow_Mm3 = np.where(aggressive, 0.0, requested_Mm3)

    res_after_tunnel = res_after_inflow - tunnel_flow_Mm3
    masl_after_tunnel = vec_masl_from_Mm3(p, res_after_tunnel)

    overflow_Mm3 = p.m3s_to_Mm3(vec_overflow_m3s_from_masl(p, masl_after_tunnel))
    max_overflow = np.maximum(0.0, res_after_tunnel - p.filling_at_hrw_Mm3)
    overflow_Mm3 = np.minimum(overflow_Mm3, max_overflow)

    res_next = res_after_tunnel - overflow_Mm3
    end_masl = vec_masl_from_Mm3(p, res_next)

    res_cost_lrw = np.where(end_masl < p.LRW,
                            (p.RES_PENALTY * dt / 3600.0) * (p.LRW - end_masl), 0.0)

    if frozen_masl is None:
        Hbrutto = (start_masl + np.minimum(end_masl, p.HRW)) / 2.0 - p.powstat_masl
    else:
        Hbrutto = frozen_masl - p.powstat_masl

    Q = tunnel_flow_m3s
    Hnetto = Hbrutto - p.headlosscoef * Q * Q
    eta = vec_turbine_efficiency(p, Q)
    P_MW = eta * 1000.0 * GRAVITY * Hnetto * Q / 1_000_000.0 * p.static_generator_efficiency
    power_MWh = np.where(Q > 0.0, P_MW * dt / 3600.0, 0.0)
    income = power_MWh * price

    profit = income - aggressive_cost - res_cost_lrw
    on = np.broadcast_to(a > 0.01, profit.shape)

    return profit, res_next, on


def make_state_grid(p, prices, inflows, restprice, n_grid, margin=1.15):
    """
    Storage grid bounds, derived rather than guessed.

    Lower bound: filling_at_lrw_Mm3. The state cannot go below it --
    reservoir.cpp:509 caps the withdrawal at max(0, res - filling_at_lrw), so
    the LRW branch is structurally unreachable in a single-reservoir slice.

    Upper bound: the maximum volume reached under the all-off policy (the
    policy that stores the most), times `margin`.
    """
    _, steps_off = R.simulate_sequence(p, [0.0] * len(prices), inflows, prices, restprice)
    max_off = max(s.res_Mm3_next for s in steps_off)
    s_min = p.filling_at_lrw_Mm3
    s_max = s_min + (max_off - s_min) * margin
    return np.linspace(s_min, s_max, n_grid), max_off


def backward_induction(p, prices, inflows, restprice, state_grid, action_grid,
                       frozen_masl=None, verbose=False, max_block_elems=4_000_000):
    """
    V[t] has shape (N_GRID, 2): value-to-go from the start of step t, indexed by
    [state, prev_onoff].

    The action grid is processed in chunks with a running max, so peak memory is
    bounded by max_block_elems regardless of how fine the storage grid is. The
    result is identical to processing the whole grid at once -- max over a
    partitioned set is the max of the partial maxima.
    """
    T = len(prices)
    S = state_grid
    N = len(S)
    V = [None] * T
    V_next = None
    ss = p.powstat_startstop / 2.0

    chunk = max(1, min(len(action_grid), max_block_elems // max(1, N)))

    for t in range(T - 1, -1, -1):
        Vt = np.full((N, 2), -np.inf)
        for lo in range(0, len(action_grid), chunk):
            acts = action_grid[lo:lo + chunk]
            profit, res_next, on = transition_block(p, S, acts, inflows[t], prices[t],
                                                    frozen_masl=frozen_masl)
            if t == T - 1:
                continuation = vec_terminal_value_Euro(p, res_next, restprice)
            else:
                flat = res_next.ravel()
                cont_off = np.interp(flat, S, V_next[:, 0]).reshape(res_next.shape)
                cont_on = np.interp(flat, S, V_next[:, 1]).reshape(res_next.shape)
                # continuation is indexed by the CURRENT action's on/off state
                continuation = np.where(on, cont_on, cont_off)
            base = profit + continuation
            for prev_onoff in (0, 1):
                switch = np.where(on != bool(prev_onoff), ss, 0.0)
                np.maximum(Vt[:, prev_onoff], (base - switch).max(axis=1),
                           out=Vt[:, prev_onoff])
        V[t] = Vt
        V_next = Vt
        if verbose and t % 50 == 0:
            print(f"    backward induction t={t:3d}  V range [{Vt.min():.1f}, {Vt.max():.1f}]")

    return V


def forward_rollout(p, V, prices, inflows, restprice, state_grid, action_grid,
                    reservoir_init_fr=None, frozen_masl=None):
    """
    Re-optimize at the exact (continuous, off-grid) forward state each step,
    using V[t+1] from backward induction as the continuation value.
    Returns (actions, value_from_rollout).
    """
    T = len(prices)
    S = state_grid
    s = R.initial_res_Mm3(p, reservoir_init_fr)
    prev_onoff = 0  # powerstation.cpp:246: t=0 hardcodes previous_action=0.0
    ss = p.powstat_startstop / 2.0
    actions = []
    total_profit = 0.0

    for t in range(T):
        s_arr = np.array([s])
        profit, res_next, on = transition_block(p, s_arr, action_grid, inflows[t], prices[t],
                                                frozen_masl=frozen_masl)
        profit, res_next, on = profit[0], res_next[0], on[0]
        if t == T - 1:
            continuation = vec_terminal_value_Euro(p, res_next, restprice)
        else:
            continuation = np.where(on,
                                    np.interp(res_next, S, V[t + 1][:, 1]),
                                    np.interp(res_next, S, V[t + 1][:, 0]))
        switch = np.where(on != bool(prev_onoff), ss, 0.0)
        total = profit + continuation - switch
        k = int(np.argmax(total))

        actions.append(float(action_grid[k]))
        total_profit += profit[k] - switch[k]
        s = float(res_next[k])
        prev_onoff = 1 if bool(on[k]) else 0

    vf = total_profit + R.terminal_value_Euro(p, s, restprice)
    return actions, vf


def solve(p, prices, inflows, restprice, n_grid=8001, n_action_bwd=201,
          n_action_fwd=2001, frozen_masl=None, binary_actions=False, verbose=False):
    """Full DP solve. Returns dict with actions, value, grid metadata, eval count."""
    state_grid, max_off = make_state_grid(p, prices, inflows, restprice, n_grid)
    if binary_actions:
        action_bwd = action_fwd = np.array([0.0, 1.0])
    else:
        action_bwd = np.linspace(0.0, 1.0, n_action_bwd)
        action_fwd = np.linspace(0.0, 1.0, n_action_fwd)

    V = backward_induction(p, prices, inflows, restprice, state_grid, action_bwd,
                           frozen_masl=frozen_masl, verbose=verbose)
    actions, vf_rollout = forward_rollout(p, V, prices, inflows, restprice, state_grid,
                                          action_fwd, frozen_masl=frozen_masl)
    vf_replica, _ = R.simulate_sequence(p, actions, inflows, prices, restprice)

    T = len(prices)
    return {
        "actions": actions,
        "vf_rollout": vf_rollout,
        "vf_replica": vf_replica,
        "v0_grid": float(np.interp(R.initial_res_Mm3(p), state_grid, V[0][:, 0])),
        "state_grid": [float(state_grid[0]), float(state_grid[-1]), len(state_grid)],
        "max_res_Mm3_all_off": float(max_off),
        "n_action_bwd": len(action_bwd),
        "n_action_fwd": len(action_fwd),
        "n_transition_evaluations": T * len(state_grid) * len(action_bwd) + T * len(action_fwd),
        "frozen_masl": frozen_masl,
        "binary_actions": binary_actions,
    }


def check_against_replica(p, prices, inflows, restprice, n=5, seed=0, tol=1e-9):
    """transition_block must agree with replica.step() branch for branch."""
    rng = np.random.default_rng(seed)
    lo = p.filling_at_lrw_Mm3
    hi = lo + 3.0 * p.active_capacity_Mm3
    worst = 0.0
    for _ in range(n):
        s = float(rng.uniform(lo, hi))
        t = int(rng.integers(0, len(prices)))
        acts = np.linspace(0.0, 1.0, 37)
        prof, res_next, _ = transition_block(p, np.array([s]), acts, inflows[t], prices[t])
        for k, a in enumerate(acts):
            r = R.step(p, s, 0.0, float(a), inflows[t], prices[t])
            # replica's profit includes the start/stop term; strip it for comparison
            ref_profit = r.profit + r.startstop_cost
            worst = max(worst, abs(ref_profit - prof[0, k]), abs(r.res_Mm3_next - res_next[0, k]))
    assert worst < tol, f"dp.transition_block disagrees with replica.step by {worst}"
    return worst
