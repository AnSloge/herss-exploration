#!/usr/bin/env python
"""
Exact DP for res_casc_A: backward induction over a two-dimensional storage grid
(RES_A x RES_B) with a third, discrete dimension carrying the start/stop cost,
and a three-dimensional action space (hatch x generator 0 x generator 1).

This is the first instance in the series where the decision variables are
coupled, so the state can no longer be one scalar. replica2.py remains the single
source of truth for the transition; check_against_replica() verifies this module
against it branch for branch before any DP result is trusted.

Two exact reductions keep the problem affordable. Neither is an approximation.

1. Generator relabelling. Both generators have the same TURBINE_CURVE and the
   same GENERATOR_MAX_DISCHARGE, so swapping them is a symmetry of the entire
   model. The action grid is therefore restricted to a_g0 >= a_g1, and the
   start/stop state collapses from "which generators were on" (4 values) to "how
   many were on" (3 values), with

       start/stop cost = |n_on - n_on_prev| * POWSTAT_STARTSTOP/2

   because a free relabelling always lets the new on-set overlap the old one as
   much as possible. emit_labelled_actions() turns an (n_on, levels) plan back
   into a concrete per-generator assignment that realises exactly that many
   transitions. The argument is checked, not assumed: run_cascade.py replays the
   DP policy through real HERSS and requires the value to match.

2. Grouping the action grid by n_on. The continuation value has to be looked up
   in V[t+1][:, :, n_on], and n_on is a property of the action alone, so
   processing actions in n_on-order means one bilinear interpolation per chunk
   instead of a per-column table selection.

Memory is bounded by max_block_elems regardless of grid size: the action grid is
processed in chunks with a running max, which is exact (the max over a partition
is the max of the partial maxima).
"""

import numpy as np

import replica2 as R2
from params2 import AGGRESSIVE_ACTIONS_COST, GRAVITY


# ---------------------------------------------------------------- vectorized step

def _vec_overflow_Mm3(p, r, masl, res_Mm3):
    """Vectorized replica2.calc_overflow_Mm3 -- same guard structure."""
    ov = p.m3s_to_Mm3(r.curve_overflow.x2y(masl))
    ov = np.minimum(ov, res_Mm3 - r.filling_at_hrw_Mm3)
    return np.where(masl <= r.overflow_masl[0], 0.0, ov)


def _vec_efficiency(st, q):
    eta = st.curve_turbine.x2y(q) / 100.0
    return np.where(q < 0.000001, 0.0, eta)


def transition_block(p, SA, SB, a_hatch, a_g0, a_g1, inflow_A, inflow_B, price):
    """
    Vectorized replica2.step over the outer product of states (SA, SB), both
    shape (N,), and actions (a_hatch, a_g0, a_g1), all shape (M,).

    Returns (profit_no_startstop, resA_next, resB_next), each shape (N, M).
    The start/stop term is added by the caller: it is the only part that depends
    on n_on_prev.
    """
    A, B, st = p.upper, p.lower, p.station
    dt = p.dt_seconds

    SA = SA[:, None]
    SB = SB[:, None]
    ah = a_hatch[None, :]
    g0 = a_g0[None, :]
    g1 = a_g1[None, :]

    # ---------------- RES_A: inflow, hatch, overflow (replica2.step RES_A block)
    resA = SA + p.m3s_to_Mm3(inflow_A)                       # (N,1)
    maslA = A.curve_Mm3_2_masl.x2y(resA)                     # (N,1)

    hatch_req = p.m3s_to_Mm3(A.hatch_qmin + ah * (A.hatch_qmax - A.hatch_qmin))
    # reservoir.cpp:565 -- curve ROUND TRIP, unlike the overflow clip
    max_hatch = A.curve_masl_2_Mm3.x2y(maslA) - A.filling_at_hatch_Mm3
    hatch = np.minimum(hatch_req, max_hatch)                 # (N,M)
    hatch = np.where(maslA > A.hatch_masl, hatch, 0.0)

    # reservoir.cpp:573 / :477 -- the volume crosses as a flow and back
    hatch_up_m3s = p.Mm3_to_m3s(hatch)
    resA = resA - hatch

    maslA = A.curve_Mm3_2_masl.x2y(resA)
    ovA = _vec_overflow_Mm3(p, A, maslA, resA)
    resA = resA - ovA
    maslA_end = A.curve_Mm3_2_masl.x2y(resA)
    lrw_A = np.where(maslA_end < A.LRW,
                     (A.RES_PENALTY * dt / 3600.0) * (A.LRW - maslA_end), 0.0)

    # ---------------- RES_B: inflow + hatch, tunnel, overflow
    start_masl_B = np.minimum(B.curve_Mm3_2_masl.x2y(SB), B.HRW)   # stale masl
    resB = SB + p.m3s_to_Mm3(inflow_B) + p.m3s_to_Mm3(hatch_up_m3s)
    up_res = np.maximum(0.0, resB - B.filling_at_lrw_Mm3)

    total_action = g0 + g1
    flow = np.where(total_action < 0.0000001, 0.0,
                    (g0 + g1) * st.max_discharge)              # (1,M)
    Q_Mm3 = p.m3s_to_Mm3(flow)

    aggressive = Q_Mm3 > up_res
    agg_cost = np.where(aggressive, (Q_Mm3 - up_res) * AGGRESSIVE_ACTIONS_COST, 0.0)
    tunnel_m3s = np.where(aggressive, 0.0, flow)

    resB = resB - p.m3s_to_Mm3(tunnel_m3s)
    maslB = B.curve_Mm3_2_masl.x2y(resB)
    ovB = _vec_overflow_Mm3(p, B, maslB, resB)
    resB = resB - ovB
    maslB_end = B.curve_Mm3_2_masl.x2y(resB)
    lrw_B = np.where(maslB_end < B.LRW,
                     (B.RES_PENALTY * dt / 3600.0) * (B.LRW - maslB_end), 0.0)
    end_masl_B = np.minimum(maslB_end, B.HRW)

    # ---------------- PSTAT_B
    Q0 = g0 * st.max_discharge
    Q1 = g1 * st.max_discharge
    total_Q = Q0 + Q1
    # powerstation.cpp:144-153 -- fires exactly when GetTunnelFLow zeroed the release
    zeroed = total_Q > tunnel_m3s * 1.000001
    Q0 = np.where(zeroed, 0.0, Q0)
    Q1 = np.where(zeroed, 0.0, Q1)
    total_Q = np.where(zeroed, 0.0, total_Q)

    Hbrutto = (start_masl_B + end_masl_B) / 2.0 - st.powstat_masl
    # SHARED_PENSTOCK: one head loss on the combined flow, one Hnetto for both
    Hnetto = Hbrutto - st.headlosscoef * total_Q * total_Q
    eff_flow = _vec_efficiency(st, Q0) * Q0 + _vec_efficiency(st, Q1) * Q1
    power = (eff_flow * 1000.0 * GRAVITY * Hnetto / 1_000_000.0
             * st.static_gen_efficiency * dt / 3600.0)
    income = power * price

    profit = income - agg_cost - lrw_A - lrw_B
    return profit, resA, resB


def n_on_of(a_g0, a_g1):
    """powerstation.cpp:254 counts a generator as running when action > 0.01."""
    return (np.asarray(a_g0) > 0.01).astype(np.int64) + \
           (np.asarray(a_g1) > 0.01).astype(np.int64)


# ---------------------------------------------------------------- action grid

def make_action_grid(n_hatch, n_gen):
    """
    Cartesian product of hatch levels and symmetry-reduced generator pairs
    (a_g0 >= a_g1), returned grouped by n_on so each group needs only one
    continuation table.

    Returns [(n_on, a_hatch, a_g0, a_g1), ...], one entry per n_on value present.
    """
    h = np.linspace(0.0, 1.0, n_hatch)
    g = np.linspace(0.0, 1.0, n_gen)
    i, j = np.triu_indices(n_gen)          # i <= j  ->  g[j] >= g[i]
    p0, p1 = g[j], g[i]                    # p0 >= p1

    groups = []
    non = n_on_of(p0, p1)
    for k in (0, 1, 2):
        m = non == k
        if not m.any():
            continue
        q0, q1 = p0[m], p1[m]
        ah = np.repeat(h, len(q0))
        a0 = np.tile(q0, len(h))
        a1 = np.tile(q1, len(h))
        groups.append((k, ah, a0, a1))
    return groups


def count_actions(groups):
    return sum(len(g[1]) for g in groups)


# ---------------------------------------------------------------- interpolation

class Grid2D:
    """Regular 2D grid with clamped bilinear lookup."""

    def __init__(self, sa, sb):
        self.sa, self.sb = sa, sb
        self.NA, self.NB = len(sa), len(sb)
        self.a0, self.da = sa[0], sa[1] - sa[0]
        self.b0, self.db = sb[0], sb[1] - sb[0]

    def states(self):
        """Flattened (NA*NB,) coordinate arrays in C order (a major)."""
        A, B = np.meshgrid(self.sa, self.sb, indexing="ij")
        return A.ravel(), B.ravel()

    def interp(self, V, xa, xb):
        """V has shape (NA, NB); xa/xb any matching shape. Clamped at the edges."""
        fa = (xa - self.a0) / self.da
        fb = (xb - self.b0) / self.db
        ia = np.clip(fa.astype(np.int64), 0, self.NA - 2)
        ib = np.clip(fb.astype(np.int64), 0, self.NB - 2)
        wa = np.clip(fa - ia, 0.0, 1.0)
        wb = np.clip(fb - ib, 0.0, 1.0)
        v00 = V[ia, ib]
        v01 = V[ia, ib + 1]
        v10 = V[ia + 1, ib]
        v11 = V[ia + 1, ib + 1]
        return ((v00 * (1 - wb) + v01 * wb) * (1 - wa)
                + (v10 * (1 - wb) + v11 * wb) * wa)


def make_state_grid(p, prices, inflow_A, inflow_B, restprice, n_a, n_b, margin=1.02):
    """
    Grid bounds derived from the model, not guessed.

    Lower bounds: filling_at_lrw for both. Neither can go below it -- the hatch
    clips at filling_at_hatchlevel (= the LRW filling, since hatch_masl = LRW)
    and the tunnel clips at max(0, res - filling_at_lrw).

    Upper bounds: the maximum each reservoir reaches under the policy that stores
    the most water in it. For RES_A that is "hatch always closed"; for RES_B it is
    "hatch always open, generators off", which is the largest inflow it can ever
    receive.

    These are not heuristics but proven bounds on the reachable set: hatch release
    is non-negative so any release lowers RES_A, and overflow is monotone in
    level, so no policy can put RES_A above the hatch-closed trajectory. The same
    argument gives the RES_B bound. `margin` is therefore only float slack, not a
    safety factor -- keeping it near 1 buys grid resolution where the trajectory
    actually lives.
    """
    T = len(prices)
    zeros, ones = [0.0] * T, [1.0] * T

    _, steps_A = R2.simulate_sequence(
        p, {"hatch": zeros, "g0": zeros, "g1": zeros},
        inflow_A, inflow_B, prices, restprice)
    max_A = max(s.res_A_Mm3_next for s in steps_A)

    _, steps_B = R2.simulate_sequence(
        p, {"hatch": ones, "g0": zeros, "g1": zeros},
        inflow_A, inflow_B, prices, restprice)
    max_B = max(s.res_B_Mm3_next for s in steps_B)

    a_min, b_min = p.upper.filling_at_lrw_Mm3, p.lower.filling_at_lrw_Mm3
    sa = np.linspace(a_min, a_min + (max_A - a_min) * margin, n_a)
    sb = np.linspace(b_min, b_min + (max_B - b_min) * margin, n_b)
    return Grid2D(sa, sb), max_A, max_B


# ---------------------------------------------------------------- backward pass

def terminal_value(p, resA, resB, restprice):
    lo = np.clip((resB - p.lower.filling_at_lrw_Mm3) / p.lower.active_capacity_Mm3,
                 0.0, 1.0) * p.lower.active_capacity_Mm3
    active = lo
    if p.value_upper_storage:
        up = np.clip((resA - p.upper.filling_at_lrw_Mm3) / p.upper.active_capacity_Mm3,
                     0.0, 1.0) * p.upper.active_capacity_Mm3
        active = active + up
    return p.station.local_energy_equivalent * active * 1000.0 * restprice


def backward_induction(p, prices, inflow_A, inflow_B, restprice, grid, groups,
                       max_block_elems=2_000_000, verbose=False):
    """
    V[t] has shape (NA, NB, 3): value-to-go from the start of step t, indexed by
    [storage_A, storage_B, n_on_prev].
    """
    T = len(prices)
    SA, SB = grid.states()
    N = len(SA)
    ss = p.station.powstat_startstop / 2.0

    V = [None] * T
    V_next = None

    for t in range(T - 1, -1, -1):
        Vt = np.full((N, 3), -np.inf)
        for n_on, ah, a0, a1 in groups:
            M = len(ah)
            chunk = max(1, min(M, max_block_elems // max(1, N)))
            for lo in range(0, M, chunk):
                sl = slice(lo, lo + chunk)
                profit, rA, rB = transition_block(
                    p, SA, SB, ah[sl], a0[sl], a1[sl],
                    inflow_A[t], inflow_B[t], prices[t])
                if t == T - 1:
                    cont = terminal_value(p, rA, rB, restprice)
                else:
                    cont = grid.interp(V_next[:, :, n_on], rA, rB)
                best = (profit + cont).max(axis=1)
                for n_prev in (0, 1, 2):
                    cand = best - ss * abs(n_on - n_prev)
                    np.maximum(Vt[:, n_prev], cand, out=Vt[:, n_prev])
        V[t] = Vt.reshape(grid.NA, grid.NB, 3)
        V_next = V[t]
        if verbose and (t % 5 == 0 or t == T - 1):
            print(f"    t={t:3d}  V range [{V[t].min():.1f}, {V[t].max():.1f}]",
                  flush=True)
    return V


# ---------------------------------------------------------------- forward pass

def emit_labelled_actions(plan_n_on, plan_hi, plan_lo):
    """
    Turn the DP's (n_on, high level, low level) plan into concrete per-generator
    action series that realise exactly |n_on(t) - n_on(t-1)| transitions -- the
    cost the DP charged.

    Greedy: keep whichever generators were already running, start the other only
    when n_on increases, stop the one that keeps the plan's level ordering when
    it decreases. With identical generators this is always achievable, which is
    the whole content of the relabelling argument.
    """
    T = len(plan_n_on)
    g0, g1 = [0.0] * T, [0.0] * T
    running = []           # generator indices currently on, most recent last
    for t in range(T):
        k = plan_n_on[t]
        while len(running) > k:
            running.pop()
        while len(running) < k:
            cand = 0 if 0 not in running else 1
            running.append(cand)
        levels = sorted([plan_hi[t], plan_lo[t]], reverse=True)[:k]
        vals = [0.0, 0.0]
        for idx, gen in enumerate(running):
            vals[gen] = levels[idx]
        g0[t], g1[t] = vals[0], vals[1]
    return g0, g1


def forward_rollout(p, V, prices, inflow_A, inflow_B, restprice, grid, groups,
                    init_fr=None):
    """
    Re-optimize at the exact (continuous, off-grid) forward state each step,
    using V[t+1] as the continuation value. Returns (actions_dict, value).
    """
    T = len(prices)
    ss = p.station.powstat_startstop / 2.0
    sA, sB = R2.initial_state(p, init_fr)
    n_prev = 0                     # powerstation.cpp:243-245

    plan_n_on, plan_hi, plan_lo, plan_hatch = [], [], [], []
    n_cells = 0

    for t in range(T):
        best_val, best = -np.inf, None
        for n_on, ah, a0, a1 in groups:
            profit, rA, rB = transition_block(
                p, np.array([sA]), np.array([sB]), ah, a0, a1,
                inflow_A[t], inflow_B[t], prices[t])
            profit, rA, rB = profit[0], rA[0], rB[0]
            n_cells += len(ah)
            if t == T - 1:
                cont = terminal_value(p, rA, rB, restprice)
            else:
                cont = grid.interp(V[t + 1][:, :, n_on], rA, rB)
            total = profit + cont - ss * abs(n_on - n_prev)
            k = int(np.argmax(total))
            if total[k] > best_val:
                best_val = float(total[k])
                best = (n_on, float(ah[k]), float(a0[k]), float(a1[k]),
                        float(rA[k]), float(rB[k]))
        n_on, h, hi, lo, sA, sB = best
        plan_n_on.append(n_on)
        plan_hatch.append(h)
        plan_hi.append(hi)
        plan_lo.append(lo)
        n_prev = n_on

    g0, g1 = emit_labelled_actions(plan_n_on, plan_hi, plan_lo)
    actions = {"hatch": plan_hatch, "g0": g0, "g1": g1}
    vf, _ = R2.simulate_sequence(p, actions, inflow_A, inflow_B, prices, restprice)
    return actions, vf, n_cells


# ---------------------------------------------------------------- driver

def solve(p, prices, inflow_A, inflow_B, restprice,
          n_a=161, n_b=161, n_hatch_bwd=21, n_gen_bwd=21,
          n_hatch_fwd=201, n_gen_fwd=101, max_block_elems=2_000_000,
          verbose=False):
    grid, max_A, max_B = make_state_grid(p, prices, inflow_A, inflow_B, restprice,
                                         n_a, n_b)
    groups_bwd = make_action_grid(n_hatch_bwd, n_gen_bwd)
    groups_fwd = make_action_grid(n_hatch_fwd, n_gen_fwd)

    V = backward_induction(p, prices, inflow_A, inflow_B, restprice, grid,
                           groups_bwd, max_block_elems, verbose)
    actions, vf, fwd_cells = forward_rollout(p, V, prices, inflow_A, inflow_B,
                                             restprice, grid, groups_fwd)

    T = len(prices)
    n_bwd = count_actions(groups_bwd)
    sA0, sB0 = R2.initial_state(p)
    return {
        "actions": actions,
        "vf_replica": vf,
        "v0_grid": float(grid.interp(V[0][:, :, 0], np.array(sA0), np.array(sB0))),
        "state_grid_A": [float(grid.sa[0]), float(grid.sa[-1]), grid.NA],
        "state_grid_B": [float(grid.sb[0]), float(grid.sb[-1]), grid.NB],
        "max_res_A_hatch_closed": float(max_A),
        "max_res_B_hatch_open": float(max_B),
        "n_actions_bwd": n_bwd,
        "n_actions_fwd": count_actions(groups_fwd),
        "n_transition_cells": T * grid.NA * grid.NB * n_bwd + fwd_cells,
        "value_upper_storage": p.value_upper_storage,
    }


# ---------------------------------------------------------------- self-check

def check_against_replica(p, prices, inflow_A, inflow_B, n=6, seed=0, tol=1e-9):
    """transition_block must agree with replica2.step branch for branch."""
    rng = np.random.default_rng(seed)
    A, B = p.upper, p.lower
    worst = 0.0
    for _ in range(n):
        sA = float(rng.uniform(A.filling_at_lrw_Mm3, A.filling_at_hrw_Mm3 * 1.3))
        sB = float(rng.uniform(B.filling_at_lrw_Mm3, B.filling_at_hrw_Mm3 * 1.3))
        t = int(rng.integers(0, len(prices)))
        ah = np.array([0.0, 0.13, 0.5, 1.0] * 4)
        a0 = np.repeat(np.array([0.0, 0.005, 0.37, 1.0]), 4)
        a1 = np.tile(np.array([0.0, 0.02, 0.61, 0.9]), 4)
        prof, rA, rB = transition_block(p, np.array([sA]), np.array([sB]),
                                        ah, a0, a1, inflow_A[t], inflow_B[t],
                                        prices[t])
        for k in range(len(ah)):
            r = R2.step(p, sA, sB, (0.0, 0.0), float(ah[k]),
                        (float(a0[k]), float(a1[k])),
                        inflow_A[t], inflow_B[t], prices[t])
            ref = r.profit + r.startstop_cost      # block excludes start/stop
            worst = max(worst, abs(ref - prof[0, k]),
                        abs(r.res_A_Mm3_next - rA[0, k]),
                        abs(r.res_B_Mm3_next - rB[0, k]))
    assert worst < tol, f"dp2.transition_block disagrees with replica2.step by {worst}"
    return worst


if __name__ == "__main__":
    import time
    from params2 import INSTANCES, load_series

    p = INSTANCES["res_casc_A"]
    prices, qA, qB, rp = load_series(p)

    w = check_against_replica(p, prices, qA, qB)
    print(f"check_against_replica: worst |d| = {w:.3e}   OK")

    groups = make_action_grid(21, 21)
    print(f"action grid 21x21: {count_actions(groups)} actions in "
          f"{[(g[0], len(g[1])) for g in groups]}")

    grid, mA, mB = make_state_grid(p, prices, qA, qB, rp, 161, 161)
    SA, SB = grid.states()
    print(f"state grid: A [{grid.sa[0]:.3f}, {grid.sa[-1]:.3f}] x "
          f"B [{grid.sb[0]:.3f}, {grid.sb[-1]:.3f}], {len(SA)} points")

    ah, a0, a1 = groups[-1][1][:80], groups[-1][2][:80], groups[-1][3][:80]
    t0 = time.time()
    for _ in range(3):
        transition_block(p, SA, SB, ah, a0, a1, qA[0], qB[0], prices[0])
    dtc = (time.time() - t0) / 3
    cells = len(SA) * len(ah)
    print(f"transition_block: {cells / dtc / 1e6:.2f} Mcells/s")

    total = 30 * len(SA) * count_actions(groups)
    print(f"estimated backward pass: {total:.3e} cells -> "
          f"{total / (cells / dtc) / 60:.1f} min")
