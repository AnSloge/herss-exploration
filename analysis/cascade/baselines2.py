#!/usr/bin/env python
"""
Baselines for res_casc_A, the first instance with coupled decision variables.

  B0  the dataset's own actions.txt
  B2  price threshold with tuned level, plus a constant hatch level
  B3  myopic, no lookahead
  B4  coordinate ascent -- one variable, one timestep per move
  B5  coordinate ascent -- B4's moves PLUS pairwise moves

B4 vs B5 is the measurement this instance exists for. B4 changes one variable at
a time and therefore cannot, by construction, find an improvement that requires
two variables to move together. B5 is the minimal extension that can.

B5's added neighbourhoods:

  (a) hatch[t] together with one generator at the SAME step
  (b) the same variable at two ADJACENT steps
  (c) hatch[t] together with one generator at step t+1

(c) is the one that matters most here and is the reason B5 exists in this form.
The coupling in res_casc_A is not primarily simultaneous, it is DELAYED: a hatch
release at step t lands in RES_B's up_inflow[t], but whether RES_B can turbine it
depends on RES_B's volume, which depends on earlier releases. The improvement
that genuinely needs two variables is therefore "release more at t, produce more
at t or t+1". Dropping (c) would risk B5 failing to find the coupling and the
measurement concluding, falsely, that no coupling weakness exists.

B5's move set is a strict superset of B4's at every stage, including the fine
polish, so the comparison is not confounded by move-set granularity. Pairwise
moves always use the coarse level grid: 201x201 level pairs per timestep pair
would cost 100x more for a resolution the fine single-move polish already
provides.

Everything is evaluated through replica2 -- the transition validated against real
HERSS in validate2_replica.py -- and each winner is re-evaluated on the real
simulator in run_cascade.py. No feasibility repair anywhere: a candidate that
asks for more water than is available pays the aggressive-action penalty exactly
as it would in HERSS.

Budget accounting. Three numbers are recorded for every method and reported in
separate columns, because they are not interchangeable:
  n_full_evaluations  full-horizon candidate trajectories considered
  n_step_cells        vectorized single-step transitions actually computed
  seconds             wall clock
Only wall clock is comparable across method families; a batched sweep and a
scalar loop cost very different amounts per "evaluation".
"""

import time
from dataclasses import dataclass

import numpy as np

import replica2 as R2
from params2 import AGGRESSIVE_ACTIONS_COST, GRAVITY


# ---------------------------------------------------------------- vectorized step

def _vec_step(p, SA, SB, prev_g0, prev_g1, a_h, a_g0, a_g1,
              inflow_A, inflow_B, price):
    """
    Element-wise replica2.step over paired arrays. Every array has the same
    shape; scalars are broadcast. Returns (profit, resA_next, resB_next) with
    profit INCLUDING the start/stop cost (unlike dp2.transition_block, which
    excludes it because the DP adds it per prev-state).
    """
    A, B, st = p.upper, p.lower, p.station
    dt = p.dt_seconds

    resA = SA + p.m3s_to_Mm3(inflow_A)
    maslA = A.curve_Mm3_2_masl.x2y(resA)

    hatch_req = p.m3s_to_Mm3(A.hatch_qmin + a_h * (A.hatch_qmax - A.hatch_qmin))
    max_hatch = A.curve_masl_2_Mm3.x2y(maslA) - A.filling_at_hatch_Mm3
    hatch = np.where(maslA > A.hatch_masl, np.minimum(hatch_req, max_hatch), 0.0)
    hatch_up_m3s = p.Mm3_to_m3s(hatch)
    resA = resA - hatch

    maslA = A.curve_Mm3_2_masl.x2y(resA)
    ovA = p.m3s_to_Mm3(A.curve_overflow.x2y(maslA))
    ovA = np.minimum(ovA, resA - A.filling_at_hrw_Mm3)
    ovA = np.where(maslA <= A.overflow_masl[0], 0.0, ovA)
    resA = resA - ovA
    maslA_end = A.curve_Mm3_2_masl.x2y(resA)
    lrw_A = np.where(maslA_end < A.LRW,
                     (A.RES_PENALTY * dt / 3600.0) * (A.LRW - maslA_end), 0.0)

    start_masl_B = np.minimum(B.curve_Mm3_2_masl.x2y(SB), B.HRW)
    resB = SB + p.m3s_to_Mm3(inflow_B) + p.m3s_to_Mm3(hatch_up_m3s)
    up_res = np.maximum(0.0, resB - B.filling_at_lrw_Mm3)

    flow = np.where(a_g0 + a_g1 < 0.0000001, 0.0, (a_g0 + a_g1) * st.max_discharge)
    Q_Mm3 = p.m3s_to_Mm3(flow)
    aggressive = Q_Mm3 > up_res
    agg_cost = np.where(aggressive, (Q_Mm3 - up_res) * AGGRESSIVE_ACTIONS_COST, 0.0)
    tunnel = np.where(aggressive, 0.0, flow)

    resB = resB - p.m3s_to_Mm3(tunnel)
    maslB = B.curve_Mm3_2_masl.x2y(resB)
    ovB = p.m3s_to_Mm3(B.curve_overflow.x2y(maslB))
    ovB = np.minimum(ovB, resB - B.filling_at_hrw_Mm3)
    ovB = np.where(maslB <= B.overflow_masl[0], 0.0, ovB)
    resB = resB - ovB
    maslB_end = B.curve_Mm3_2_masl.x2y(resB)
    lrw_B = np.where(maslB_end < B.LRW,
                     (B.RES_PENALTY * dt / 3600.0) * (B.LRW - maslB_end), 0.0)
    end_masl_B = np.minimum(maslB_end, B.HRW)

    Q0 = a_g0 * st.max_discharge
    Q1 = a_g1 * st.max_discharge
    total_Q = Q0 + Q1
    zeroed = total_Q > tunnel * 1.000001
    Q0 = np.where(zeroed, 0.0, Q0)
    Q1 = np.where(zeroed, 0.0, Q1)
    total_Q = np.where(zeroed, 0.0, total_Q)

    Hbrutto = (start_masl_B + end_masl_B) / 2.0 - st.powstat_masl
    Hnetto = Hbrutto - st.headlosscoef * total_Q * total_Q
    e0 = np.where(Q0 < 0.000001, 0.0, st.curve_turbine.x2y(Q0) / 100.0)
    e1 = np.where(Q1 < 0.000001, 0.0, st.curve_turbine.x2y(Q1) / 100.0)
    power = ((e0 * Q0 + e1 * Q1) * 1000.0 * GRAVITY * Hnetto / 1_000_000.0
             * st.static_gen_efficiency * dt / 3600.0)
    income = power * price

    ss = st.powstat_startstop / 2.0
    startstop = (np.where((a_g0 > 0.01) != (prev_g0 > 0.01), ss, 0.0)
                 + np.where((a_g1 > 0.01) != (prev_g1 > 0.01), ss, 0.0))

    return income - agg_cost - lrw_A - lrw_B - startstop, resA, resB


def _terminal_vec(p, resA, resB, restprice):
    lo = np.clip((resB - p.lower.filling_at_lrw_Mm3) / p.lower.active_capacity_Mm3,
                 0.0, 1.0) * p.lower.active_capacity_Mm3
    active = lo
    if p.value_upper_storage:
        up = np.clip((resA - p.upper.filling_at_lrw_Mm3) / p.upper.active_capacity_Mm3,
                     0.0, 1.0) * p.upper.active_capacity_Mm3
        active = active + up
    return p.station.local_energy_equivalent * active * 1000.0 * restprice


@dataclass
class Budget:
    n_full_evaluations: int = 0
    n_step_cells: int = 0
    seconds: float = 0.0

    def add(self, evals, cells):
        self.n_full_evaluations += int(evals)
        self.n_step_cells += int(cells)

    def as_dict(self):
        return {"n_full_evaluations": self.n_full_evaluations,
                "n_step_cells": self.n_step_cells,
                "seconds": round(self.seconds, 2)}


# ---------------------------------------------------------------- batch machinery

class Series:
    """Instance time series bundled once so every routine takes the same object."""

    def __init__(self, p, prices, inflow_A, inflow_B, restprice):
        self.p = p
        self.prices = np.asarray(prices, float)
        self.qA = np.asarray(inflow_A, float)
        self.qB = np.asarray(inflow_B, float)
        self.restprice = restprice
        self.T = len(self.prices)


def full_vf(s, actions):
    """Scalar full-horizon value through the validated replica."""
    return R2.simulate_sequence(s.p, actions, s.qA, s.qB, s.prices, s.restprice)[0]


def batch_vf(s, H, G0, G1):
    """
    Full-horizon value for B candidate trajectories given as (B, T) matrices.
    Returns (vf, n_step_cells).
    """
    B_, T = H.shape
    sA0, sB0 = R2.initial_state(s.p)
    sA = np.full(B_, sA0)
    sB = np.full(B_, sB0)
    profit = np.zeros(B_)
    pg0 = np.zeros(B_)
    pg1 = np.zeros(B_)
    for t in range(T):
        pf, sA, sB = _vec_step(s.p, sA, sB, pg0, pg1, H[:, t], G0[:, t], G1[:, t],
                               s.qA[t], s.qB[t], s.prices[t])
        profit += pf
        pg0, pg1 = G0[:, t], G1[:, t]
    return profit + _terminal_vec(s.p, sA, sB, s.restprice), B_ * T


class Incumbent:
    """
    Precomputed prefix of a trajectory: state at the START of each step, profit
    accumulated before it, and the previous step's generator actions.

    A single-step (or two-step) perturbation only changes the trajectory from
    that step onward, so a candidate can be evaluated by resuming from here
    instead of replaying the horizon. Vectorizing over the perturbed index
    changes only the runtime, never the search trajectory: every entry is still
    one full-horizon evaluation and is counted as one.
    """

    def __init__(self, s, actions):
        T = s.T
        H = np.asarray(actions["hatch"], float)
        G0 = np.asarray(actions["g0"], float)
        G1 = np.asarray(actions["g1"], float)
        self.H, self.G0, self.G1 = H, G0, G1

        self.stateA = np.empty(T)
        self.stateB = np.empty(T)
        self.prefix = np.empty(T)
        self.prev_g0 = np.empty(T)
        self.prev_g1 = np.empty(T)

        sA, sB = R2.initial_state(s.p)
        acc = 0.0
        pg = (0.0, 0.0)
        for t in range(T):
            self.stateA[t], self.stateB[t], self.prefix[t] = sA, sB, acc
            self.prev_g0[t], self.prev_g1[t] = pg
            r = R2.step(s.p, sA, sB, pg, H[t], (G0[t], G1[t]),
                        s.qA[t], s.qB[t], s.prices[t])
            acc += r.profit
            sA, sB = r.res_A_Mm3_next, r.res_B_Mm3_next
            pg = (G0[t], G1[t])
        self.vf = acc + R2.terminal_value_Euro(s.p, sA, sB, s.restprice)


def resume_batch(s, inc, start_idx, over_h, over_g0, over_g1):
    """
    Evaluate B candidates that follow the incumbent except for the overrides.

    start_idx  (B,)      first step at which the candidate deviates
    over_*     (B, K)    override values for steps start_idx + 0 .. start_idx+K-1
                         (np.nan = keep the incumbent's value at that step)

    Returns (vf, n_step_cells).
    """
    T = s.T
    B_ = len(start_idx)
    K = over_h.shape[1]

    sA = inc.stateA[start_idx].copy()
    sB = inc.stateB[start_idx].copy()
    profit = inc.prefix[start_idx].copy()
    pg0 = inc.prev_g0[start_idx].copy()
    pg1 = inc.prev_g1[start_idx].copy()

    cells = 0
    t0 = int(start_idx.min())
    for t in range(t0, T):
        m = start_idx <= t
        if not m.any():
            continue
        off = t - start_idx[m]
        h = np.full(m.sum(), inc.H[t])
        g0 = np.full(m.sum(), inc.G0[t])
        g1 = np.full(m.sum(), inc.G1[t])
        act = off < K
        if act.any():
            rows = np.nonzero(m)[0][act]
            cols = off[act]
            for tgt, src in ((h, over_h), (g0, over_g0), (g1, over_g1)):
                v = src[rows, cols]
                ok = ~np.isnan(v)
                idx = np.nonzero(act)[0][ok]
                tgt[idx] = v[ok]
        pf, rA, rB = _vec_step(s.p, sA[m], sB[m], pg0[m], pg1[m], h, g0, g1,
                               s.qA[t], s.qB[t], s.prices[t])
        profit[m] += pf
        sA[m], sB[m] = rA, rB
        pg0[m], pg1[m] = g0, g1
        cells += int(m.sum())
    return profit + _terminal_vec(s.p, sA, sB, s.restprice), cells


# ---------------------------------------------------------------- B0

def b0_shipped(s):
    rows = [l.split() for l in open(s.p.dataset_dir + "actions.txt") if l.strip()]
    hdr = rows[0]
    actions = {
        "hatch": [float(r[hdr.index(str(s.p.upper.idnr))]) for r in rows[1:]],
        "g0": [float(r[hdr.index(f"{s.p.station.idnr}_0")]) for r in rows[1:]],
        "g1": [float(r[hdr.index(f"{s.p.station.idnr}_1")]) for r in rows[1:]],
    }
    t0 = time.time()
    vf = full_vf(s, actions)
    b = Budget()
    b.add(1, s.T)
    b.seconds = time.time() - t0
    return actions, vf, b


# ---------------------------------------------------------------- B2

def b2_threshold_level_hatch(s, K_range=None, L_range=None, h_range=None):
    """
    Station runs at level L on the K highest-price steps and is off otherwise;
    the hatch sits at a constant level h. Both generators take the same level, so
    this is the natural two-variable extension of the B2 family used on the
    single-reservoir instances.
    """
    T = s.T
    if K_range is None:
        K_range = np.arange(0, T + 1)
    if L_range is None:
        L_range = np.round(np.arange(0.02, 1.0001, 0.02), 3)
    if h_range is None:
        h_range = np.round(np.linspace(0.0, 1.0, 21), 3)

    order = np.argsort(-s.prices)
    t0 = time.time()
    budget = Budget()
    best = None

    # sweep K in the outer loop so each batch stays small and cache friendly
    for K in K_range:
        on = np.zeros(T, bool)
        on[order[:K]] = True
        nL, nh = len(L_range), len(h_range)
        B_ = nL * nh
        G = np.where(on[None, :], np.repeat(L_range, nh)[:, None], 0.0)
        H = np.tile(h_range, nL)[:, None] * np.ones((1, T))
        vf, cells = batch_vf(s, H, G, G.copy())
        budget.add(B_, cells)
        k = int(np.argmax(vf))
        if best is None or vf[k] > best[0]:
            best = (float(vf[k]), int(K), float(np.repeat(L_range, nh)[k]),
                    float(np.tile(h_range, nL)[k]))

    vf_best, K, L, h = best
    on = np.zeros(T, bool)
    on[order[:K]] = True
    actions = {"hatch": [h] * T,
               "g0": [L if on[t] else 0.0 for t in range(T)],
               "g1": [L if on[t] else 0.0 for t in range(T)]}
    budget.seconds = time.time() - t0
    return actions, vf_best, {"K": K, "L": L, "hatch_level": h}, budget


# ---------------------------------------------------------------- B3

def b3_myopic(s, w_upper=None, n_hatch=41, n_gen=41):
    """
    Greedy, no lookahead. At each step pick the action maximising immediate
    profit minus the marginal value of the water it consumes, with the marginal
    value taken straight from RESTPRICE and the topology constant:

        w = restprice * local_energy_equivalent * 1000   [EUR/Mm3]

    which is d(terminal term)/d(active Mm3) in riversystem.cpp:436,474.

    w_upper is the value assigned to water in RES_A. Two variants are reported:

      w_upper = w  (default, PRIMARY). RES_A water is valued like RES_B water.
        This is the myopically sensible valuation and the one that makes B3
        measure what B3 is for: the loss from having no lookahead.

      w_upper = 0  (SECONDARY). This is the true terminal derivative for RES_A
        under CalcVF as written -- RES_A is not in PSTAT_B's upstream chain, so
        its stored water is worth nothing. But then B3 measures the lookahead
        loss PLUS the inherited modelling artefact, with no way to separate them,
        and "empty RES_A immediately" stops being a myopic mistake and becomes
        myopically correct. It is reported, but it cannot be the primary.
    """
    w = s.restprice * s.p.station.local_energy_equivalent * 1000.0
    wA = w if w_upper is None else w_upper

    h_grid = np.linspace(0.0, 1.0, n_hatch)
    g_grid = np.linspace(0.0, 1.0, n_gen)
    HH, GG = np.meshgrid(h_grid, g_grid, indexing="ij")
    HH, GG = HH.ravel(), GG.ravel()
    M = len(HH)

    t0 = time.time()
    budget = Budget()
    sA, sB = R2.initial_state(s.p)
    pg0 = pg1 = 0.0
    out_h, out_g = [], []

    for t in range(s.T):
        SA = np.full(M, sA)
        SB = np.full(M, sB)
        pf, rA, rB = _vec_step(s.p, SA, SB, np.full(M, pg0), np.full(M, pg1),
                               HH, GG, GG, s.qA[t], s.qB[t], s.prices[t])
        used_A = (SA + s.p.m3s_to_Mm3(s.qA[t])) - rA
        used_B = (SB + s.p.m3s_to_Mm3(s.qB[t])) - rB
        score = pf - wA * used_A - w * used_B
        budget.add(M, M)
        k = int(np.argmax(score))
        out_h.append(float(HH[k]))
        out_g.append(float(GG[k]))
        sA, sB = float(rA[k]), float(rB[k])
        pg0 = pg1 = float(GG[k])

    actions = {"hatch": out_h, "g0": out_g, "g1": list(out_g)}
    vf = full_vf(s, actions)
    budget.add(1, s.T)
    budget.seconds = time.time() - t0
    return actions, vf, budget


# ---------------------------------------------------------------- B4 / B5 moves

def _single_moves(s, inc, levels):
    """One variable, one timestep. This is B4's entire neighbourhood."""
    T, L = s.T, len(levels)
    nan = np.nan
    batches = []
    for var in range(3):
        start = np.repeat(np.arange(T), L)
        vals = np.tile(levels, T)
        oh = np.full((T * L, 1), nan)
        og0 = np.full((T * L, 1), nan)
        og1 = np.full((T * L, 1), nan)
        [oh, og0, og1][var][:, 0] = vals
        batches.append((start, oh, og0, og1,
                        [("hatch", "g0", "g1")[var]] * (T * L),
                        start.copy(), vals, None, None, None))
    return batches


def _pair_moves(s, inc, levels):
    """
    B5's additional neighbourhoods:
      (a) hatch[t] with g0[t] / g1[t]      -- simultaneous
      (b) v[t] with v[t+1] for each v      -- adjacent, same variable
      (c) hatch[t] with g0[t+1] / g1[t+1]  -- delayed, the important one
    """
    T, L = s.T, len(levels)
    nan = np.nan
    LL0, LL1 = np.meshgrid(levels, levels, indexing="ij")
    LL0, LL1 = LL0.ravel(), LL1.ravel()
    P = len(LL0)
    batches = []

    def emit(tag, n_start, k, fill):
        start = np.repeat(np.arange(n_start), P)
        oh = np.full((n_start * P, k), nan)
        og0 = np.full((n_start * P, k), nan)
        og1 = np.full((n_start * P, k), nan)
        a = np.tile(LL0, n_start)
        b = np.tile(LL1, n_start)
        fill(oh, og0, og1, a, b)
        batches.append((start, oh, og0, og1, [tag] * (n_start * P),
                        start.copy(), a, b, None, None))

    # (a) hatch[t] + generator[t]
    emit("a_hatch_g0_same", T, 1,
         lambda oh, g0, g1, a, b: (oh.__setitem__((slice(None), 0), a),
                                   g0.__setitem__((slice(None), 0), b)))
    emit("a_hatch_g1_same", T, 1,
         lambda oh, g0, g1, a, b: (oh.__setitem__((slice(None), 0), a),
                                   g1.__setitem__((slice(None), 0), b)))
    # (b) same variable at t and t+1
    emit("b_hatch_adj", T - 1, 2,
         lambda oh, g0, g1, a, b: (oh.__setitem__((slice(None), 0), a),
                                   oh.__setitem__((slice(None), 1), b)))
    emit("b_g0_adj", T - 1, 2,
         lambda oh, g0, g1, a, b: (g0.__setitem__((slice(None), 0), a),
                                   g0.__setitem__((slice(None), 1), b)))
    emit("b_g1_adj", T - 1, 2,
         lambda oh, g0, g1, a, b: (g1.__setitem__((slice(None), 0), a),
                                   g1.__setitem__((slice(None), 1), b)))
    # (c) hatch[t] + generator[t+1] -- the delayed coupling
    emit("c_hatch_g0_next", T - 1, 2,
         lambda oh, g0, g1, a, b: (oh.__setitem__((slice(None), 0), a),
                                   g0.__setitem__((slice(None), 1), b)))
    emit("c_hatch_g1_next", T - 1, 2,
         lambda oh, g0, g1, a, b: (oh.__setitem__((slice(None), 0), a),
                                   g1.__setitem__((slice(None), 1), b)))
    return batches


def _apply_move(actions, tag, t, a, b):
    """Write the winning move into the incumbent action dict, in place."""
    H, G0, G1 = actions["hatch"], actions["g0"], actions["g1"]
    if tag == "hatch":
        H[t] = a
    elif tag == "g0":
        G0[t] = a
    elif tag == "g1":
        G1[t] = a
    elif tag == "a_hatch_g0_same":
        H[t], G0[t] = a, b
    elif tag == "a_hatch_g1_same":
        H[t], G1[t] = a, b
    elif tag == "b_hatch_adj":
        H[t], H[t + 1] = a, b
    elif tag == "b_g0_adj":
        G0[t], G0[t + 1] = a, b
    elif tag == "b_g1_adj":
        G1[t], G1[t + 1] = a, b
    elif tag == "c_hatch_g0_next":
        H[t], G0[t + 1] = a, b
    elif tag == "c_hatch_g1_next":
        H[t], G1[t + 1] = a, b
    else:
        raise ValueError(tag)


def coordinate_ascent(s, seed, levels, pairwise, start_actions=None,
                      pair_levels=None, epsilon=0.01, max_iters=100000,
                      verbose=False, budget=None):
    """
    Best-improvement coordinate ascent (Matheussen, Granmo & Sharma 2019 in the
    B4 case): evaluate every candidate move against the incumbent, accept the
    single best if it improves V by more than `epsilon`, repeat until none does.

    pairwise=False -> B4 (single-variable moves only)
    pairwise=True  -> B5 (single moves plus the pairwise neighbourhoods)
    """
    rng = np.random.default_rng(seed)
    T = s.T
    if start_actions is None:
        actions = {"hatch": list(rng.uniform(0, 1, T)),
                   "g0": list(rng.uniform(0, 1, T)),
                   "g1": list(rng.uniform(0, 1, T))}
    else:
        actions = {k: list(v) for k, v in start_actions.items()}

    if pair_levels is None:
        pair_levels = np.round(np.linspace(0.0, 1.0, 21), 4)

    budget = budget or Budget()
    vf = full_vf(s, actions)
    budget.add(1, T)
    iters = 0
    converged = False

    while iters < max_iters:
        inc = Incumbent(s, actions)
        budget.add(0, T)                      # prefix pass, not a candidate
        batches = _single_moves(s, inc, levels)
        if pairwise:
            batches += _pair_moves(s, inc, pair_levels)

        best_gain, best_move = -np.inf, None
        for start, oh, og0, og1, tags, ts, va, vb, _, _ in batches:
            vals, cells = resume_batch(s, inc, start, oh, og0, og1)
            budget.add(len(start), cells)
            k = int(np.argmax(vals))
            gain = float(vals[k]) - vf
            if gain > best_gain:
                best_gain = gain
                best_move = (tags[k], int(ts[k]), float(va[k]),
                             None if vb is None else float(vb[k]))

        if best_gain <= epsilon:
            converged = True
            break

        _apply_move(actions, *best_move)
        vf = full_vf(s, actions)
        budget.add(1, T)
        iters += 1
        if verbose and iters % 25 == 0:
            print(f"      seed={seed} pairwise={pairwise} iter {iters}: "
                  f"VF={vf:.2f} (last {best_move[0]} t={best_move[1]})", flush=True)

    return actions, vf, iters, converged, budget


def multistart(s, pairwise, seeds=(1, 2), coarse_levels=None, fine_levels=None,
               epsilon=0.01, max_iters=4000, verbose=False):
    """
    Each restart runs to convergence on a coarse 21-point level grid, then is
    polished to convergence on a 201-point grid.

    The polish is not cosmetic: on HJELLE it added 2531 / 3836 EUR. Without it
    the gap against a published method would be inflated by pure discretization,
    since the DP rollout searches a much finer grid.

    The spread between restarts is returned and reported: it is the noise floor
    against which any B5-minus-B4 difference has to be judged.
    """
    if coarse_levels is None:
        coarse_levels = np.round(np.linspace(0.0, 1.0, 21), 4)
    if fine_levels is None:
        fine_levels = np.round(np.linspace(0.0, 1.0, 201), 4)

    runs = []
    for seed in seeds:
        t0 = time.time()
        budget = Budget()
        a_c, vf_c, it_c, cv_c, budget = coordinate_ascent(
            s, seed, coarse_levels, pairwise, epsilon=epsilon,
            max_iters=max_iters, verbose=verbose, budget=budget)
        a_f, vf_f, it_f, cv_f, budget = coordinate_ascent(
            s, seed, fine_levels, pairwise, start_actions=a_c,
            epsilon=epsilon, max_iters=max_iters, verbose=verbose, budget=budget)
        budget.seconds = time.time() - t0
        runs.append({
            "seed": seed,
            "coarse": {"vf": vf_c, "iterations": it_c, "converged": cv_c,
                       "n_levels": len(coarse_levels)},
            "fine": {"vf": vf_f, "iterations": it_f, "converged": cv_f,
                     "n_levels": len(fine_levels)},
            "polish_gain": vf_f - vf_c,
            "budget": budget.as_dict(),
            "actions": {k: [float(x) for x in v] for k, v in a_f.items()},
        })
        print(f"    {'B5' if pairwise else 'B4'} seed={seed}: "
              f"coarse {vf_c:.2f} ({it_c} it, conv={cv_c}) -> "
              f"fine {vf_f:.2f} ({it_f} it, conv={cv_f}) "
              f"[{budget.seconds:.1f} s]", flush=True)

    best = max(runs, key=lambda r: r["fine"]["vf"])
    spread = max(r["fine"]["vf"] for r in runs) - min(r["fine"]["vf"] for r in runs)
    return best, runs, spread
