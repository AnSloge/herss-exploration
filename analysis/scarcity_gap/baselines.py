#!/usr/bin/env python
"""
The four baselines the DP is measured against.

All four are tuned/run through replica.py -- the transition function validated
against real HERSS in validate_replica.py -- and the winner of each is
re-evaluated on the real simulator in run_measurement.py. Every function
reports the number of full-horizon evaluations it spent.

B1  price threshold, full production        a_t = 1 if p_t > tau else 0
B2  price threshold with tuned level        a_t = L on the K highest-price steps
B3  myopic                                  no lookahead at all
B4  multi-start coordinate ascent           Matheussen, Granmo & Sharma (2019)

No feasibility repair anywhere: if a candidate asks for more water than is
available, the aggressive-action penalty fires exactly as it would in HERSS and
the candidate's VF carries it.
"""

import numpy as np

import replica as R
from params import AGGRESSIVE_ACTIONS_COST, GRAVITY


def _vf(p, actions, inflows, prices, restprice):
    return R.simulate_sequence(p, actions, inflows, prices, restprice)[0]


# --------------------------------------------------------------------- B1

def b1_threshold_full(p, prices, inflows, restprice):
    """Sweep tau over every distinct price plus one above the maximum."""
    taus = sorted(set(prices))
    taus = [-1.0] + taus                     # -1 => always on
    best, n = None, 0
    for tau in taus:
        actions = [1.0 if pr > tau else 0.0 for pr in prices]
        v = _vf(p, actions, inflows, prices, restprice)
        n += 1
        if best is None or v > best[1]:
            best = (tau, v)
    return best, n


# --------------------------------------------------------------------- B2

def bangbang_actions(prices, K, L):
    order = sorted(range(len(prices)), key=lambda t: -prices[t])
    on = set(order[:K])
    return [L if t in on else 0.0 for t in range(len(prices))]


def b2_threshold_level(p, prices, inflows, restprice, K_range=None, L_range=None):
    """The family used in the 2026-07-30 measurement, kept for continuity."""
    T = len(prices)
    if K_range is None:
        K_range = range(0, T + 1)
    if L_range is None:
        L_range = np.round(np.arange(0.01, 1.0001, 0.01), 2)

    best, n = None, 0
    for K in K_range:
        for L in L_range:
            v = _vf(p, bangbang_actions(prices, K, L), inflows, prices, restprice)
            n += 1
            if best is None or v > best[2]:
                best = (K, float(L), v)
    return best, n


# --------------------------------------------------------------------- B3

def b3_myopic(p, prices, inflows, restprice, n_actions=2001):
    """
    Greedy, no lookahead: at each step pick the action maximising immediate
    income minus the marginal value of the water it consumes, where that
    marginal value comes straight from RESTPRICE and the topology constant:

        w = restprice * local_energy_equivalent * 1000   [EUR/Mm3]

    which is exactly d(terminal term)/d(active Mm3) in riversystem.cpp:436,474.
    Only the terminal term is used -- the policy never looks at a future price.
    """
    grid = np.linspace(0.0, 1.0, n_actions)
    w = restprice * p.local_energy_equivalent * 1000.0   # EUR per Mm3

    s = R.initial_res_Mm3(p)
    prev = np.zeros(n_actions)
    actions = []
    n = 0
    for t in range(len(prices)):
        S = np.full(n_actions, s)
        profit, res_next, on = _vec_step_1d(p, S, prev, grid, inflows[t], prices[t])
        water_used_Mm3 = (S + p.m3s_to_Mm3(inflows[t])) - res_next  # net drawdown incl. overflow
        score = profit - w * water_used_Mm3
        n += n_actions
        k = int(np.argmax(score))
        best_a = float(grid[k])
        actions.append(best_a)
        s = float(res_next[k])
        prev = np.full(n_actions, best_a)
    # n counts single-step candidate evaluations, not full-horizon runs
    return actions, _vf(p, actions, inflows, prices, restprice), n


# --------------------------------------------------------------------- B4

def _forward_batch(p, base_actions, inflows, prices, restprice, level):
    """
    For every t, the value of the incumbent with a_t replaced by `level`.

    All T perturbed trajectories are advanced together: entry i of the batch is
    the trajectory that follows the incumbent up to step i-1, plays `level` at
    step i, then follows the incumbent again. Vectorizing over t changes only
    the runtime, never the search trajectory -- each entry is still one
    full-horizon evaluation and is counted as such.

    Returns an array of length T of resulting VFs.
    """
    T = len(prices)
    dt = p.dt_seconds
    A = np.asarray(base_actions, dtype=float)

    # state of the incumbent at the START of each step, and its profit-so-far
    inc_state = np.empty(T + 1)
    inc_prefix_profit = np.empty(T + 1)
    s = R.initial_res_Mm3(p)
    acc = 0.0
    prev = 0.0
    inc_state[0], inc_prefix_profit[0] = s, 0.0
    for t in range(T):
        r = R.step(p, s, prev, A[t], inflows[t], prices[t])
        acc += r.profit
        s = r.res_Mm3_next
        prev = A[t]
        inc_state[t + 1], inc_prefix_profit[t + 1] = s, acc

    # batch: entry i starts at step i from the incumbent's state there
    state = inc_state[:T].copy()
    profit = inc_prefix_profit[:T].copy()
    prev_act = np.empty(T)
    prev_act[0] = 0.0
    prev_act[1:] = A[:T - 1]
    alive = np.arange(T)          # index i -> which batch entries are still running

    for t in range(T):
        idx = alive[alive <= t]
        if len(idx) == 0:
            break
        act = np.where(idx == t, level, A[t])
        st = state[idx]
        pr = prev_act[idx]

        pf, res_next, on = _vec_step_1d(p, st, pr, act, inflows[t], prices[t])
        profit[idx] += pf
        state[idx] = res_next
        prev_act[idx] = act

    return profit + _terminal_vec(p, state, restprice)


def _forward_batch_levels(p, base_actions, inflows, prices, restprice, levels):
    """
    Same as _forward_batch, but sweeps ALL candidate levels in one pass.

    Returns an (n_levels, T) array: entry [l, i] is the VF of the incumbent with
    a_i replaced by levels[l]. Identical values to calling _forward_batch once
    per level -- only the numpy call count differs (365 vectorized steps instead
    of n_levels*365), which is what makes running B4 to convergence affordable.
    The search trajectory, the move set and the evaluation count are unchanged.
    """
    T = len(prices)
    L = len(levels)
    A = np.asarray(base_actions, dtype=float)
    lv = np.asarray(levels, dtype=float)

    # incumbent trajectory: state at the start of each step, profit so far
    inc_state = np.empty(T)
    inc_prefix = np.empty(T)
    s = R.initial_res_Mm3(p)
    acc = 0.0
    prev = 0.0
    for t in range(T):
        inc_state[t], inc_prefix[t] = s, acc
        r = R.step(p, s, prev, A[t], inflows[t], prices[t])
        acc += r.profit
        s = r.res_Mm3_next
        prev = A[t]

    # flattened batch, entry j = l*T + i
    i_of = np.tile(np.arange(T), L)
    l_of = np.repeat(np.arange(L), T)
    state = np.tile(inc_state, L)
    profit = np.tile(inc_prefix, L)
    prev_act = np.empty(T)
    prev_act[0] = 0.0
    prev_act[1:] = A[:T - 1]
    prev_act = np.tile(prev_act, L)

    for t in range(T):
        m = i_of <= t                       # entries that have started
        act = np.where(i_of[m] == t, lv[l_of[m]], A[t])
        pf, res_next, _ = _vec_step_1d(p, state[m], prev_act[m], act, inflows[t], prices[t])
        profit[m] += pf
        state[m] = res_next
        prev_act[m] = act

    return (profit + _terminal_vec(p, state, restprice)).reshape(L, T)


def _terminal_vec(p, res_Mm3, restprice):
    fract = np.clip((res_Mm3 - p.filling_at_lrw_Mm3) / p.active_capacity_Mm3, 0.0, 1.0)
    return fract * p.active_capacity_Mm3 * p.local_energy_equivalent * 1000.0 * restprice


def _vec_step_1d(p, S, prev_action, action, inflow_m3s, price):
    """Element-wise replica.step over paired (state, prev_action, action) arrays."""
    dt = p.dt_seconds
    start_masl = np.minimum(p.curve_Mm3_2_masl.x2y(S), p.HRW)

    res_after_inflow = S + p.m3s_to_Mm3(inflow_m3s)
    up_res = np.maximum(0.0, res_after_inflow - p.filling_at_lrw_Mm3)

    req_m3s = action * p.generator_max_discharge
    req_Mm3 = p.m3s_to_Mm3(req_m3s)

    aggressive = req_Mm3 > up_res
    agg_cost = np.where(aggressive, (req_Mm3 - up_res) * AGGRESSIVE_ACTIONS_COST, 0.0)
    flow_m3s = np.where(aggressive, 0.0, req_m3s)
    flow_Mm3 = np.where(aggressive, 0.0, req_Mm3)

    res_after_tunnel = res_after_inflow - flow_Mm3
    masl_after = p.curve_Mm3_2_masl.x2y(res_after_tunnel)

    ov = np.where(masl_after <= p.overflow_curve_masl[0], 0.0, p.curve_overflow.x2y(masl_after))
    ov_Mm3 = np.minimum(p.m3s_to_Mm3(ov),
                        np.maximum(0.0, res_after_tunnel - p.filling_at_hrw_Mm3))

    res_next = res_after_tunnel - ov_Mm3
    end_masl = p.curve_Mm3_2_masl.x2y(res_next)

    lrw_cost = np.where(end_masl < p.LRW,
                        (p.RES_PENALTY * dt / 3600.0) * (p.LRW - end_masl), 0.0)

    Hbrutto = (start_masl + np.minimum(end_masl, p.HRW)) / 2.0 - p.powstat_masl
    Q = flow_m3s
    Hnetto = Hbrutto - p.headlosscoef * Q * Q
    eta = np.where(Q < 1e-6, 0.0, p.curve_turbine.x2y(Q) / 100.0)
    P_MW = eta * 1000.0 * GRAVITY * Hnetto * Q / 1e6 * p.static_generator_efficiency
    power = np.where(Q > 0.0, P_MW * dt / 3600.0, 0.0)
    income = power * price

    on = action > 0.01
    prev_on = prev_action > 0.01
    ss = np.where(on != prev_on, p.powstat_startstop / 2.0, 0.0)

    return income - agg_cost - lrw_cost - ss, res_next, on


def b4_coordinate_ascent(p, prices, inflows, restprice, levels, seed,
                         start_actions=None, epsilon=0.01, max_iters=100000,
                         verbose=False):
    """
    Best-improvement coordinate ascent (Matheussen, Granmo & Sharma 2019):
    change one variable in one time step at a time, measure the change in V,
    reset, test the next; accept the single time step with the largest
    improvement; repeat until no move improves V by more than `epsilon`.

    Returns (actions, vf, n_evaluations, n_iterations, converged).
    """
    rng = np.random.default_rng(seed)
    T = len(prices)
    actions = (list(rng.uniform(0.0, 1.0, T)) if start_actions is None
               else list(start_actions))

    vf = _vf(p, actions, inflows, prices, restprice)
    n_eval = 1
    iters = 0
    converged = False

    while iters < max_iters:
        vals = _forward_batch_levels(p, actions, inflows, prices, restprice, levels)
        n_eval += vals.size
        l, t_star = np.unravel_index(int(np.argmax(vals)), vals.shape)
        best_gain = float(vals[l, t_star]) - vf
        best_t, best_level = int(t_star), float(levels[l])

        if best_gain <= epsilon:
            converged = True
            break

        actions[best_t] = best_level
        vf = _vf(p, actions, inflows, prices, restprice)
        n_eval += 1
        iters += 1
        if verbose and iters % 25 == 0:
            print(f"      B4 seed={seed} iter {iters}: VF={vf:.2f} "
                  f"(last move t={best_t} -> {best_level})")

    return actions, vf, n_eval, iters, converged


def b4_multistart(p, prices, inflows, restprice, seeds=(1, 2),
                  coarse_levels=None, fine_levels=None, epsilon=0.01,
                  max_iters=6000, verbose=False):
    """
    Two random restarts, each run to convergence on a coarse 21-point candidate
    grid and then polished to convergence on a 201-point grid.

    The polish matters: without it B4 could not reach the DP optimum by
    construction (the DP rollout uses 2001 levels), and the gap against a
    published method would be inflated by pure discretization. Both the coarse
    and the polished value are reported.
    """
    if coarse_levels is None:
        coarse_levels = np.round(np.linspace(0.0, 1.0, 21), 4)
    if fine_levels is None:
        fine_levels = np.round(np.linspace(0.0, 1.0, 201), 4)

    runs = []
    for seed in seeds:
        a_c, vf_c, ev_c, it_c, cv_c = b4_coordinate_ascent(
            p, prices, inflows, restprice, coarse_levels, seed,
            epsilon=epsilon, max_iters=max_iters, verbose=verbose)
        a_f, vf_f, ev_f, it_f, cv_f = b4_coordinate_ascent(
            p, prices, inflows, restprice, fine_levels, seed,
            start_actions=a_c, epsilon=epsilon, max_iters=max_iters, verbose=verbose)
        runs.append({
            "seed": seed,
            "coarse": {"vf": vf_c, "evaluations": ev_c, "iterations": it_c,
                       "converged": cv_c, "n_levels": len(coarse_levels)},
            "fine": {"vf": vf_f, "evaluations": ev_f, "iterations": it_f,
                     "converged": cv_f, "n_levels": len(fine_levels)},
            "actions": [float(x) for x in a_f],
        })
        if verbose:
            print(f"    B4 seed={seed}: coarse {vf_c:.2f} ({it_c} it, {ev_c} ev, "
                  f"conv={cv_c}) -> fine {vf_f:.2f} ({it_f} it, {ev_f} ev, conv={cv_f})")

    best = max(runs, key=lambda r: r["fine"]["vf"])
    return best, runs
