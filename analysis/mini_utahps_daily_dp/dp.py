#!/usr/bin/env python
"""
Exact(-ish) DP for mini_utahps_daily: backward induction over discretized
reservoir storage (single state dimension, since the channel is irrelevant
to V -- see replica.py docstring) and a binary on/off dimension for the
start/stop cost, action discretized over [0,1].

Formulas mirror replica.py exactly (same constants, same branch structure),
vectorized over the storage grid with numpy for speed. replica.py remains
the single source of truth for the scalar per-step transition; this module
is checked against it in main() before trusting the DP result.
"""

import numpy as np

import replica as R

# --- grid design ---
# Storage grid: 0 to 25 Mm3 covers [LRW=1.0, HRW=10.0] with margin on both
# sides (dead storage below LRW, flood storage up to ~masl 758 above HRW);
# validated empirically that no candidate policy pushes the reservoir
# outside this range within the 30-day horizon (see main()'s range check).
S_MIN, S_MAX, N_GRID = 0.0, 25.0, 4001
ACTION_GRID_DP = np.linspace(0.0, 1.0, 201)       # used inside backward induction
ACTION_GRID_FWD = np.linspace(0.0, 1.0, 2001)     # finer, used for forward policy extraction

STATE_GRID = np.linspace(S_MIN, S_MAX, N_GRID)


def vec_masl_from_Mm3(Mm3):
    return np.interp(Mm3, R.RESERVOIR_CURVE_MM3, R.RESERVOIR_CURVE_MASL)


def vec_overflow_m3s_from_masl(masl):
    q = np.interp(masl, R.OVERFLOW_CURVE_MASL, R.OVERFLOW_CURVE_M3S)
    return np.where(masl <= R.OVERFLOW_CURVE_MASL[0], 0.0, q)


def vec_turbine_efficiency(q_m3s):
    eta = np.interp(q_m3s, R.TURBINE_CURVE_Q, R.TURBINE_CURVE_PCT) / 100.0
    return np.where(q_m3s < 1e-6, 0.0, eta)


def vec_remaining_active_Mm3(res_Mm3):
    fract = (res_Mm3 - R.FILLING_AT_LRW_MM3) / R.ACTIVE_CAPACITY_MM3
    fract = np.clip(fract, 0.0, 1.0)
    return fract * R.ACTIVE_CAPACITY_MM3


def vec_terminal_value_Euro(res_Mm3, restprice):
    remaining_MWh = R.LOCAL_ENERGY_EQUIVALENT * vec_remaining_active_Mm3(res_Mm3) * 1000.0
    return remaining_MWh * restprice


def vec_step(S, prev_onoff, action, inflow_m3s, price, dt=R.DT_SECONDS):
    """
    Vectorized version of replica.step() over an array of starting states S
    (shape (N,)), for one scalar action/day. Returns (profit, res_next),
    both shape (N,).
    """
    start_of_stp_masl = np.minimum(vec_masl_from_Mm3(S), R.HRW)

    res_after_inflow = S + R.m3s_to_Mm3(inflow_m3s, dt)
    up_res_Mm3 = np.maximum(0.0, res_after_inflow - R.FILLING_AT_LRW_MM3)

    requested_m3s = action * R.GENERATOR_MAX_DISCHARGE
    requested_Mm3 = R.m3s_to_Mm3(requested_m3s, dt)

    aggressive = requested_Mm3 > up_res_Mm3
    aggressive_cost = np.where(aggressive, (requested_Mm3 - up_res_Mm3) * R.AGGRESSIVE_ACTIONS_COST, 0.0)
    tunnel_flow_m3s = np.where(aggressive, 0.0, requested_m3s)
    tunnel_flow_Mm3 = np.where(aggressive, 0.0, requested_Mm3)

    res_after_tunnel = res_after_inflow - tunnel_flow_Mm3
    masl_after_tunnel = vec_masl_from_Mm3(res_after_tunnel)

    overflow_m3s = vec_overflow_m3s_from_masl(masl_after_tunnel)
    overflow_Mm3 = R.m3s_to_Mm3(overflow_m3s, dt)
    max_overflow = np.maximum(0.0, res_after_tunnel - R.FILLING_AT_HRW_MM3)
    overflow_Mm3 = np.minimum(overflow_Mm3, max_overflow)

    res_next = res_after_tunnel - overflow_Mm3
    end_of_stp_masl = vec_masl_from_Mm3(res_next)

    res_cost_lrw = np.where(end_of_stp_masl < R.LRW,
                             (R.RES_PENALTY * dt / 3600.0) * (R.LRW - end_of_stp_masl), 0.0)

    end_of_stp_masl_clipped = np.minimum(end_of_stp_masl, R.HRW)
    Hbrutto = (start_of_stp_masl + end_of_stp_masl_clipped) / 2.0 - R.POWSTAT_MASL

    Q = tunnel_flow_m3s
    headloss = R.HEADLOSSCOEF * Q * Q
    Hnetto = Hbrutto - headloss
    eta = vec_turbine_efficiency(Q)
    P_MW = eta * 1000.0 * R.GRAVITY * Hnetto * Q / 1_000_000.0 * R.STATIC_GENERATOR_EFFICIENCY
    power_MWh = np.where(Q > 0.0, P_MW * dt / 3600.0, 0.0)
    income = power_MWh * price

    cur_onoff = 1 if action > 0.01 else 0
    startstop_cost = R.POWSTAT_STARTSTOP / 2.0 if (prev_onoff != cur_onoff) else 0.0

    cost = startstop_cost + aggressive_cost + res_cost_lrw
    profit = income - cost

    return profit, res_next


def backward_induction(prices, inflows, restprice, action_grid=ACTION_GRID_DP, verbose=True):
    """Returns V[t] arrays of shape (N_GRID, 2) for t=0..T-1 (value-to-go from
    start of day t, indexed by [state, prev_onoff]), for use in forward rollout."""
    T = len(prices)
    S = STATE_GRID
    V = [None] * T
    V_next = None  # V_next[:, onoff] = value-to-go from start of day t+1

    for t in range(T - 1, -1, -1):
        Vt = np.full((N_GRID, 2), -np.inf)
        for prev_onoff in (0, 1):
            best = np.full(N_GRID, -np.inf)
            for a in action_grid:
                profit, res_next = vec_step(S, prev_onoff, a, inflows[t], prices[t])
                if t == T - 1:
                    continuation = vec_terminal_value_Euro(res_next, restprice)
                else:
                    cur_onoff = 1 if a > 0.01 else 0
                    continuation = np.interp(res_next, S, V_next[:, cur_onoff])
                total = profit + continuation
                best = np.maximum(best, total)
            Vt[:, prev_onoff] = best
        V[t] = Vt
        V_next = Vt
        if verbose:
            print(f"  backward induction: day {t:2d} done, V range [{Vt.min():.1f}, {Vt.max():.1f}]")

    return V


def forward_rollout(V, prices, inflows, restprice, reservoir_init_fr, action_grid=ACTION_GRID_FWD):
    """
    Re-optimize at the exact (continuous, non-grid) forward state each day,
    using the backward-induction V[t+1] as the continuation-value proxy.
    Returns (actions, value_from_rollout).
    """
    T = len(prices)
    S = STATE_GRID
    s = R.initial_res_Mm3(reservoir_init_fr)
    prev_onoff = 0  # powerstation.cpp:246, t=0 hardcoded previous_action=0.0
    actions = []
    total_profit = 0.0

    for t in range(T):
        s_arr = np.full(1, s)
        best_val = -np.inf
        best_a = 0.0
        best_res_next = s
        for a in action_grid:
            profit, res_next = vec_step(s_arr, prev_onoff, a, inflows[t], prices[t])
            if t == T - 1:
                continuation = vec_terminal_value_Euro(res_next, restprice)
            else:
                cur_onoff = 1 if a > 0.01 else 0
                continuation = np.interp(res_next, S, V[t + 1][:, cur_onoff])
            total = profit[0] + continuation[0]
            if total > best_val:
                best_val = total
                best_a = a
                best_res_next = res_next[0]
        actions.append(best_a)
        step_profit, _ = vec_step(np.full(1, s), prev_onoff, best_a, inflows[t], prices[t])
        total_profit += step_profit[0]
        s = best_res_next
        prev_onoff = 1 if best_a > 0.01 else 0

    vf_rollout = total_profit + R.terminal_value_Euro(s, restprice)
    return actions, vf_rollout


if __name__ == "__main__":
    import validate as V_

    prices, inflows, restprice, reservoir_init_fr = V_.load_dataset()

    # sanity: how far can res_Mm3 range under adverse (no-production) / aggressive policies?
    _, steps_off = R.simulate_sequence([0.0] * 30, inflows, prices, reservoir_init_fr, restprice)
    max_off = max(s.res_Mm3_next for s in steps_off)
    print(f"max res_Mm3 under all-off policy: {max_off:.3f} (grid max {S_MAX})")
    assert max_off < S_MAX, "raise S_MAX -- grid does not cover the reachable state range"

    print("Running backward induction...")
    V = backward_induction(prices, inflows, restprice)

    print("Running forward rollout...")
    actions, vf_rollout = forward_rollout(V, prices, inflows, restprice, reservoir_init_fr)

    vf_replica, _ = R.simulate_sequence(actions, inflows, prices, reservoir_init_fr, restprice)

    print()
    print("DP backward-induction value at s0 (grid-interpolated):",
          np.interp(R.initial_res_Mm3(reservoir_init_fr), STATE_GRID, V[0][:, 0]))
    print("Forward rollout self-reported value:", vf_rollout)
    print("Replica re-evaluation of the extracted action sequence:", vf_replica)
    print()
    print("actions:", [round(a, 4) for a in actions])
