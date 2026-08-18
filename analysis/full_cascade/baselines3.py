#!/usr/bin/env python
"""
Baselines for the full uTAHPS cascade.

  B0  the dataset's own actions_utahps.txt
  B1  price threshold per station, full production when on
  B2  price threshold plus a tuned level per station
  B3  myopic, water valued at RESTPRICE * chain equivalent, no lookahead
  B4  coordinate ascent, one variable at one timestep per move
  B5  B4's optimum plus pairwise moves

Everything is evaluated through replica3 -- the transition validated per step
against real HERSS for all 12 nodes in validate3_replica.py -- and each winner is
re-evaluated on the real simulator in run_full_cascade.py. No feasibility repair
anywhere: a candidate that asks for more water than is available pays the
aggressive-action penalty exactly as it would in HERSS.

WHY B5 STARTS FROM B4's OPTIMUM. On res_casc_A, B5 ran its own multi-start with
the same seeds and a strict superset of B4's moves, and came out 21 EUR WORSE --
not because pairwise moves hurt, but because a superset of moves takes a
different trajectory through the landscape and can land in a different local
optimum. That confounds the only question B5 exists to answer: how much does
single-variable ascent leave behind because it cannot move two variables at
once? Starting B5 at B4's converged point removes the confound entirely. B5 >= B4
then holds by construction, the difference is attributable to the pairwise
neighbourhoods alone, and the gain decomposes cleanly by neighbourhood type.

THE NEIGHBOURHOODS, AND WHY (a) NOT (c) IS THE PRIMARY ONE HERE. At daily
resolution the routing delay is ZERO steps: 77-96 % of an impulse leaves each
channel within the same step (params3.channel_impulse_response), and node
execution is idnr-ordered within a timestep, so an upstream release at t reaches
the downstream station at t.

  (a) two stations at the SAME step -- the real cascade coupling
  (b) the same station at two adjacent steps
  (c) upstream station at t with downstream station at t+1 -- RESERVOIR MEDIATED,
      not routing delay: water that sits in the downstream reservoir overnight,
      plus the 4-23 % channel tail

Budget accounting. Three numbers are recorded for every method and reported in
separate columns, because they are not interchangeable:
  n_full_evaluations  full-horizon candidate trajectories considered
  n_step_cells        vectorized single-step transitions actually computed
  seconds             wall clock
Only wall clock is comparable across method families; a batched sweep and a
scalar loop cost very different amounts per "evaluation".
"""

import itertools
import time
from dataclasses import dataclass

import numpy as np

import replica3

# Candidate rows evaluated at once. Purely a memory/throughput knob: chunks are
# independent and concatenated, so the search trajectory is bit-identical
# whatever this is set to. This is the lever to pull first if peak RSS is the
# binding constraint -- it costs a little throughput and NO resolution.
MAX_BATCH = 40000


# ------------------------------------------------------------------ bookkeeping

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


class Series:
    """Instance time series bundled once so every routine takes the same object."""

    def __init__(self, plan, prices, inflow, restprice):
        self.plan = plan
        self.p = plan.p
        self.prices = np.asarray(prices, float)
        self.T = len(self.prices)
        self.Q = np.array([[inflow[i][t] for i in plan.inflow_res_order]
                           for t in range(self.T)])
        self.restprice = restprice
        self.n_sta = len(self.p.stations)
        self.sta_names = [f"g{s.idnr}" for s in self.p.stations]

    def to_dict(self, M):
        """(T, n_sta) matrix -> {'g<idnr>': [...]}"""
        return {n: [float(x) for x in M[:, k]] for k, n in enumerate(self.sta_names)}

    def to_matrix(self, actions):
        return replica3.actions_to_matrix(self.plan, actions, self.T)


def full_vf(s, M):
    """Scalar full-horizon value through the validated replica."""
    state = replica3.initial_state(s.plan, B=1)
    total = 0.0
    for t in range(s.T):
        pf, state = replica3.step(s.plan, state, M[t][None, :], s.Q[t], s.prices[t])
        total += pf[0]
    return float(total + replica3.terminal_value_Euro(s.plan, state, s.restprice)[0])


# ------------------------------------------------------------------ incumbent

class Incumbent:
    """
    Precomputed prefix of a trajectory: the state at the START of each step and
    the profit accumulated before it.

    A perturbation at step t only changes the trajectory from t onward, so a
    candidate can be evaluated by resuming from here instead of replaying the
    horizon. Vectorising over the perturbed index changes only the runtime, never
    the search trajectory: every entry is still one full-horizon evaluation and
    is counted as one.
    """

    def __init__(self, s, M):
        plan, T = s.plan, s.T
        self.M = M

        self.res = np.empty((T, len(s.p.reservoirs)))
        self.chan = np.empty((T, plan.n_linres_total))
        self.prev = np.empty((T, s.n_sta))
        self.prefix = np.empty(T)

        state = replica3.initial_state(plan, B=1)
        acc = 0.0
        for t in range(T):
            self.res[t] = state.res_Mm3[0]
            self.chan[t] = state.chan_m3[0]
            self.prev[t] = state.prev_act[0]
            self.prefix[t] = acc
            pf, state = replica3.step(plan, state, M[t][None, :], s.Q[t], s.prices[t])
            acc += pf[0]
        self.vf = float(acc + replica3.terminal_value_Euro(plan, state, s.restprice)[0])


def resume_batch(s, inc, start_idx, over):
    """
    Evaluate B candidates that follow the incumbent except for the overrides.

    start_idx  (B,)               first step at which each candidate deviates,
                                  REQUIRED to be sorted ascending
    over       (B, K, n_sta)      override values for steps start_idx+0 .. +K-1
                                  (np.nan = keep the incumbent's value)

    Sortedness is what makes this cheap. With start_idx ascending, the set of
    candidates already active at step t is a contiguous PREFIX of the batch, and
    the set whose offset into `over` equals k is a contiguous SLICE. Both become
    slices instead of boolean masks, which is the difference between one numpy
    call per step and one gather per step per row.

    Returns (vf (B,), n_step_cells).
    """
    plan, T = s.plan, s.T
    B, K, n_sta = over.shape

    # nact[t] = number of candidates with start_idx <= t
    nact = np.searchsorted(start_idx, np.arange(-1, T), side="right")

    def n_at(t):
        return 0 if t < -1 else int(nact[t + 1])

    RES = np.empty((B, inc.res.shape[1]))
    CHAN = np.empty((B, inc.chan.shape[1]))
    PREV = np.empty((B, n_sta))
    PROFIT = np.empty(B)
    A = np.empty((B, n_sta))

    cells = 0
    t0 = int(start_idx[0])
    for t in range(t0, T):
        n = n_at(t)
        if n == 0:
            continue
        # rows that become active exactly at t start from the incumbent's state
        lo = n_at(t - 1)
        if n > lo:
            RES[lo:n] = inc.res[t]
            CHAN[lo:n] = inc.chan[t]
            PREV[lo:n] = inc.prev[t]
            PROFIT[lo:n] = inc.prefix[t]

        A[:n] = inc.M[t]
        # offset k into `over` corresponds to the rows that started at t-k
        for k in range(K):
            a, b = n_at(t - k - 1), n_at(t - k)
            if b <= a:
                continue
            v = over[a:b, k, :]
            np.copyto(A[a:b], v, where=~np.isnan(v))

        st = replica3.State(RES[:n], CHAN[:n], PREV[:n])
        pf, st2 = replica3.step(plan, st, A[:n], s.Q[t], s.prices[t])
        PROFIT[:n] += pf
        RES[:n] = st2.res_Mm3
        CHAN[:n] = st2.chan_m3
        PREV[:n] = st2.prev_act
        cells += n

    final = replica3.State(RES, CHAN, PREV)
    return PROFIT + replica3.terminal_value_Euro(plan, final, s.restprice), cells


def resume_chunked(s, inc, start_idx, over, max_batch=MAX_BATCH):
    """resume_batch split into memory-bounded chunks. Bit-identical results."""
    B = len(start_idx)
    if B <= max_batch:
        return resume_batch(s, inc, start_idx, over)
    vals, cells = [], 0
    for a in range(0, B, max_batch):
        b = min(a + max_batch, B)
        v, c = resume_batch(s, inc, start_idx[a:b], over[a:b])
        vals.append(v)
        cells += c
    return np.concatenate(vals), cells


# ------------------------------------------------------------------ move sets

def _single_moves(s, levels):
    """
    One variable, one timestep. This is B4's entire neighbourhood.

    Yields (tag, start_idx, over, meta) with start_idx ascending, as
    resume_batch requires. Emitted one variable at a time so each batch stays
    within MAX_BATCH without chunking in the common case.
    """
    T, L, n = s.T, len(levels), s.n_sta
    for k in range(n):
        start = np.repeat(np.arange(T), L)
        over = np.full((T * L, 1, n), np.nan)
        over[:, 0, k] = np.tile(levels, T)
        yield (f"single:{s.sta_names[k]}", start, over,
               {"kind": "single", "vars": (k,), "levels": np.tile(levels, T)})


def _pair_moves(s, levels, upstream_pairs):
    """
    B5's additional neighbourhoods. See the module docstring for why (a) is the
    primary one at daily resolution and (c) is reservoir mediated.
    """
    T, n = s.T, s.n_sta
    LL0, LL1 = np.meshgrid(levels, levels, indexing="ij")
    LL0, LL1 = LL0.ravel(), LL1.ravel()
    P = len(LL0)

    def emit(tag, n_start, K, fill, meta):
        start = np.repeat(np.arange(n_start), P)
        over = np.full((n_start * P, K, n), np.nan)
        a = np.tile(LL0, n_start)
        b = np.tile(LL1, n_start)
        fill(over, a, b)
        meta = dict(meta, a=a, b=b)
        return (tag, start, over, meta)

    # (a) two stations at the same step
    for i, j in itertools.combinations(range(n), 2):
        tag = f"a_same:{s.sta_names[i]}+{s.sta_names[j]}"
        if (i, j) in upstream_pairs:
            tag += ":cascade"
        yield emit(tag, T, 1,
                   lambda o, a, b, i=i, j=j: (o[:, 0, i].__setitem__(slice(None), a),
                                              o[:, 0, j].__setitem__(slice(None), b)),
                   {"kind": "a", "vars": (i, j)})

    # (b) the same station at two adjacent steps
    for i in range(n):
        yield emit(f"b_adj:{s.sta_names[i]}", T - 1, 2,
                   lambda o, a, b, i=i: (o[:, 0, i].__setitem__(slice(None), a),
                                         o[:, 1, i].__setitem__(slice(None), b)),
                   {"kind": "b", "vars": (i, i)})

    # (c) upstream station at t with downstream station at t+1
    for i, j in sorted(upstream_pairs):
        yield emit(f"c_next:{s.sta_names[i]}->{s.sta_names[j]}", T - 1, 2,
                   lambda o, a, b, i=i, j=j: (o[:, 0, i].__setitem__(slice(None), a),
                                              o[:, 1, j].__setitem__(slice(None), b)),
                   {"kind": "c", "vars": (i, j)})


def upstream_station_pairs(s):
    """
    {(i, j)} with station i strictly upstream of station j, as column indices.

    Walks ptr_downstream_node from each station. SVEIGSHYL_II is fed by GRESSE
    and discharges straight into DALSANA, bypassing TOPPSY, so (SVOLETJONN,
    SVEIGSHYL_II) is NOT a cascade pair even though both sit high in the system.
    """
    p = s.p
    col = {st.idnr: k for k, st in enumerate(p.stations)}
    out = set()
    for st in p.stations:
        cur = p.downlink_to[st.idnr]
        seen = set()
        while cur is not None and cur >= 0 and cur not in seen:
            seen.add(cur)
            if p.node_kind[cur] == "PSTATION":
                out.add((col[st.idnr], col[cur]))
                cur = p.downlink_to[cur]
            elif p.node_kind[cur] == "RESERVOIR":
                cur = p.tunnel_to[cur]
            else:
                cur = p.channel_to[cur]
    return out


def apply_move(M, meta, t, a, b=None):
    """Write a winning move into the incumbent action matrix, in place."""
    kind, vars_ = meta["kind"], meta["vars"]
    if kind == "single":
        M[t, vars_[0]] = a
    elif kind == "a":
        M[t, vars_[0]], M[t, vars_[1]] = a, b
    elif kind in ("b", "c"):
        M[t, vars_[0]], M[t + 1, vars_[1]] = a, b
    else:
        raise ValueError(kind)


# ------------------------------------------------------------------ ascent

def coordinate_ascent(s, levels, seed=None, start_M=None, pairwise=False,
                      pair_levels=None, epsilon=0.01, max_iters=1000000,
                      time_limit=None, verbose=False, budget=None,
                      max_batch=MAX_BATCH, on_iter=None):
    """
    Best-improvement coordinate ascent (Matheussen, Granmo & Sharma 2019 in the
    B4 case): evaluate every candidate move against the incumbent, accept the
    single best if it improves V by more than `epsilon`, repeat until none does.

    pairwise=False -> B4 (single-variable moves only)
    pairwise=True  -> B4's moves PLUS the pairwise neighbourhoods

    time_limit stops the ascent early and reports converged=False. It exists for
    the pilot; a run that hits it has NOT converged and must be reported as such.
    """
    rng = np.random.default_rng(seed)
    if start_M is None:
        M = rng.uniform(0.0, 1.0, (s.T, s.n_sta))
    else:
        M = np.array(start_M, dtype=float, copy=True)

    if pair_levels is None:
        pair_levels = np.round(np.linspace(0.0, 1.0, 11), 4)
    pairs = upstream_station_pairs(s) if pairwise else set()

    budget = budget or Budget()
    vf = full_vf(s, M)
    budget.add(1, s.T)
    t_start = time.time()
    iters, converged, gain_by_tag = 0, False, {}

    while iters < max_iters:
        inc = Incumbent(s, M)
        budget.add(0, s.T)                    # prefix pass, not a candidate

        batches = list(_single_moves(s, levels))
        if pairwise:
            batches += list(_pair_moves(s, pair_levels, pairs))

        best = (-np.inf, None)
        for tag, start, over, meta in batches:
            vals, cells = resume_chunked(s, inc, start, over, max_batch)
            budget.add(len(start), cells)
            k = int(np.argmax(vals))
            gain = float(vals[k]) - vf
            if gain > best[0]:
                t = int(start[k])
                if meta["kind"] == "single":
                    best = (gain, (tag, meta, t, float(meta["levels"][k]), None))
                else:
                    best = (gain, (tag, meta, t, float(meta["a"][k]),
                                   float(meta["b"][k])))

        if best[0] <= epsilon:
            converged = True
            break

        tag, meta, t, a, b = best[1]
        apply_move(M, meta, t, a, b)
        vf = full_vf(s, M)
        budget.add(1, s.T)
        gain_by_tag[tag] = gain_by_tag.get(tag, 0.0) + best[0]
        iters += 1

        if on_iter is not None:
            on_iter(iters, vf, tag, t)
        if verbose and iters % 25 == 0:
            print(f"      iter {iters}: VF={vf:.2f} (last {tag} t={t}) "
                  f"[{time.time() - t_start:.0f} s]", flush=True)
        if time_limit is not None and time.time() - t_start > time_limit:
            break

    budget.seconds = time.time() - t_start
    return {"M": M, "vf": vf, "iterations": iters, "converged": converged,
            "budget": budget, "gain_by_tag": gain_by_tag,
            "n_levels": len(levels)}


def b4_restart(s, seed, coarse_levels=None, fine_levels=None, epsilon=0.01,
               time_limit=None, verbose=False, max_batch=MAX_BATCH):
    """
    One B4 restart: coarse grid to convergence, then polished on a fine grid.

    The polish is not cosmetic. On HJELLE it added 2531 and 3836 EUR on two
    restarts -- different amounts, so dropping it would inject grid noise
    directly into the restart spread, which is the headline measurement.
    """
    if coarse_levels is None:
        coarse_levels = np.round(np.linspace(0.0, 1.0, 21), 4)
    if fine_levels is None:
        fine_levels = np.round(np.linspace(0.0, 1.0, 201), 4)

    t0 = time.time()
    budget = Budget()
    coarse = coordinate_ascent(s, coarse_levels, seed=seed, epsilon=epsilon,
                               time_limit=time_limit, verbose=verbose,
                               budget=budget, max_batch=max_batch)
    remaining = None if time_limit is None else max(0.0, time_limit - (time.time() - t0))
    fine = coordinate_ascent(s, fine_levels, start_M=coarse["M"], epsilon=epsilon,
                             time_limit=remaining, verbose=verbose,
                             budget=budget, max_batch=max_batch)
    budget.seconds = time.time() - t0
    return {
        "seed": seed,
        "coarse": {"vf": coarse["vf"], "iterations": coarse["iterations"],
                   "converged": coarse["converged"], "n_levels": coarse["n_levels"]},
        "fine": {"vf": fine["vf"], "iterations": fine["iterations"],
                 "converged": fine["converged"], "n_levels": fine["n_levels"]},
        "polish_gain": fine["vf"] - coarse["vf"],
        "converged": coarse["converged"] and fine["converged"],
        "budget": budget.as_dict(),
        "M": fine["M"],
    }


def b5_from(s, M0, pair_levels=None, fine_levels=None, epsilon=0.01,
            time_limit=None, verbose=False, max_batch=MAX_BATCH):
    """
    B5: continue from B4's optimum with the pairwise neighbourhoods added.

    Returns the gain decomposed by neighbourhood type, which is the point of the
    exercise -- see the module docstring.
    """
    if fine_levels is None:
        fine_levels = np.round(np.linspace(0.0, 1.0, 201), 4)
    if pair_levels is None:
        pair_levels = np.round(np.linspace(0.0, 1.0, 11), 4)

    r = coordinate_ascent(s, fine_levels, start_M=M0, pairwise=True,
                          pair_levels=pair_levels, epsilon=epsilon,
                          time_limit=time_limit, verbose=verbose,
                          max_batch=max_batch)
    by_kind = {"single": 0.0, "a": 0.0, "b": 0.0, "c": 0.0}
    for tag, g in r["gain_by_tag"].items():
        key = ("single" if tag.startswith("single") else
               "a" if tag.startswith("a_same") else
               "b" if tag.startswith("b_adj") else "c")
        by_kind[key] += g
    r["gain_by_kind"] = by_kind
    r["n_pair_levels"] = len(pair_levels)
    return r


# ------------------------------------------------------------------ B0 - B3

def b0_shipped(s, actions):
    t0 = time.time()
    M = s.to_matrix(actions)
    vf = full_vf(s, M)
    b = Budget()
    b.add(1, s.T)
    b.seconds = time.time() - t0
    return {"M": M, "vf": vf, "budget": b.as_dict()}


def _threshold_M(s, K_on, level, order):
    """Station runs at `level` on its K_on highest-price steps, else off."""
    M = np.zeros((s.T, s.n_sta))
    for k in range(s.n_sta):
        M[order[:K_on[k]], k] = level[k]
    return M


def _tune_threshold(s, levels, K_grid, verbose=False):
    """
    Cyclic coordinate tuning over (K_on, level) per station.

    A joint grid over eight parameters is 10^8 points and pointless; the stations
    are coupled, so one pass is not enough either. Cycling until no station's
    best pair changes is the cheap honest compromise, and the number of sweeps is
    reported.
    """
    order = np.argsort(-s.prices)
    K_on = [s.T // 2] * s.n_sta
    level = [1.0] * s.n_sta
    budget = Budget()
    t0 = time.time()

    best_vf = full_vf(s, _threshold_M(s, K_on, level, order))
    budget.add(1, s.T)

    sweeps = 0
    for sweeps in range(1, 11):
        changed = False
        for k in range(s.n_sta):
            combos = [(K, L) for K in K_grid for L in levels]
            Ms = np.empty((len(combos), s.T, s.n_sta))
            for c, (K, L) in enumerate(combos):
                kk, ll = list(K_on), list(level)
                kk[k], ll[k] = K, L
                Ms[c] = _threshold_M(s, kk, ll, order)
            vals, cells = replica3.simulate_batch(s.plan, Ms, {
                i: s.Q[:, j] for j, i in enumerate(s.plan.inflow_res_order)},
                s.prices, s.restprice)
            budget.add(len(combos), cells)
            c = int(np.argmax(vals))
            if vals[c] > best_vf + 1e-9:
                best_vf = float(vals[c])
                K_on[k], level[k] = combos[c]
                changed = True
        if verbose:
            print(f"      threshold sweep {sweeps}: VF={best_vf:.2f} "
                  f"K={K_on} L={[round(x, 3) for x in level]}", flush=True)
        if not changed:
            break

    budget.seconds = time.time() - t0
    M = _threshold_M(s, K_on, level, order)
    return {"M": M, "vf": best_vf, "budget": budget.as_dict(),
            "parameters": {"K_on": list(K_on), "level": [float(x) for x in level],
                           "sweeps": sweeps}}


def b1_threshold(s, verbose=False):
    """Full production when on. Four parameters."""
    K_grid = list(range(0, s.T + 1, 5)) + [s.T]
    return _tune_threshold(s, [1.0], sorted(set(K_grid)), verbose)


def b2_threshold_level(s, verbose=False):
    """Threshold plus a tuned level per station. Eight parameters."""
    K_grid = list(range(0, s.T + 1, 5)) + [s.T]
    levels = list(np.round(np.arange(0.05, 1.0001, 0.05), 3))
    return _tune_threshold(s, levels, sorted(set(K_grid)), verbose)


def b3_myopic(s, n_level=11, verbose=False):
    """
    Greedy, no lookahead. At each step pick the joint action maximising immediate
    profit minus the marginal value of the water it consumes, with the marginal
    value taken from RESTPRICE and the CHAIN equivalent:

        w_r = restprice * chain_equivalent[r] * 1000   [EUR/Mm3]

    which is d(terminal term)/d(active Mm3) for reservoir r under CalcVF -- see
    replica3.terminal_value_Euro. Using each station's own
    LOCAL_ENERGY_EQUIVALENT instead would undervalue every reservoir that still
    has stations below it, and would make emptying the top of the cascade look
    myopically correct when it is not.
    """
    plan = s.plan
    w = np.array([s.restprice * s.p.chain_equivalent[r.idnr] * 1000.0
                  for r in s.p.reservoirs])

    grid = np.linspace(0.0, 1.0, n_level)
    combos = np.array(list(itertools.product(grid, repeat=s.n_sta)))
    Mn = len(combos)

    t0 = time.time()
    budget = Budget()
    state = replica3.initial_state(plan, B=1)
    out = np.empty((s.T, s.n_sta))

    for t in range(s.T):
        batch = replica3.State(np.repeat(state.res_Mm3, Mn, axis=0),
                               np.repeat(state.chan_m3, Mn, axis=0),
                               np.repeat(state.prev_act, Mn, axis=0))
        before = batch.res_Mm3.copy()
        pf, nxt = replica3.step(plan, batch, combos, s.Q[t], s.prices[t])
        used = (before + s.p.m3s_to_Mm3(s.Q[t])[None, :]) - nxt.res_Mm3
        score = pf - used @ w
        budget.add(Mn, Mn)
        k = int(np.argmax(score))
        out[t] = combos[k]
        state = replica3.State(nxt.res_Mm3[k:k + 1].copy(),
                               nxt.chan_m3[k:k + 1].copy(),
                               nxt.prev_act[k:k + 1].copy())
        if verbose and t % 100 == 0:
            print(f"      myopic t={t}", flush=True)

    vf = full_vf(s, out)
    budget.add(1, s.T)
    budget.seconds = time.time() - t0
    return {"M": out, "vf": vf, "budget": budget.as_dict(),
            "water_value_EUR_per_Mm3": {r.name: float(w[i])
                                        for i, r in enumerate(s.p.reservoirs)}}
