#!/usr/bin/env python
"""
Python replica of the HERSS timestep for the full uTAHPS cascade (12 nodes).

Every formula is cited against the C++ source at upstream commit 029a2d5
(HERSS VERSION 3.1.03 / VERSION_DATE 20260611):

  src/reservoir.cpp           Reservoir::Simulate (:428-716), CalcOverflow (:154-275),
                              InitReservoir (:295-360)
  src/powerstation.cpp        Powerstation::Simulate (:110-307),
                              GetTunnelFLow (:746-793), calcEfficiency (:70-106)
  src/channel.cpp             Channel::Simulate (:71-134)
  src/cascadedreservoirs.cpp  route (:83-92), routeOneReservoir (:94-117)
  src/herss.cpp               node loop (:661-677), terminal accumulation (:686-693)
  src/riversystem.cpp         Riversystem::CalcVF (:406-480)
  src/arraycurve.cpp          ArrayCurve::x2y (ported in scarcity_gap/arraycurve.py)

WHY THIS IS VECTORIZED THROUGHOUT. The search in baselines3 evaluates tens of
thousands of candidate trajectories per coordinate-ascent iteration, so the step
must run over a batch axis. Keeping a separate scalar implementation for
validation would mean two transcriptions of ~200 lines of subtle transition
logic that can silently drift apart -- and it is the validated one that would
stop being the one the search uses. There is therefore ONE implementation,
operating on arrays of shape (B,); validation runs it with B = 1.

STRUCTURE OF A TIMESTEP. herss.cpp:669-677 loops nodes in idnr order, and idnr
order is topological for this topology (params3.assert_topological_order checks
it). So a release at the top of the cascade propagates all the way to the outlet
WITHIN the same timestep -- there is no lag to model between nodes beyond what
the channel routing itself retains, and at dt = 86400 s against
K_TRAVELTIME_HOURS of 1-6 h that retention is 4-23 % of one step.

Node execution, per node kind:

  RESERVOIR   local inflow and up_inflow are added (:474-478), the downstream
              station is handed the STALE level and the above-LRW volume
              (:499-509), the tunnel flow comes back from GetTunnelFLow and is
              subtracted, then overflow, then the LRW penalty.
  PSTATION    flow per generator, the second aggressive-action guard (:145-153),
              head from the average of the reservoir's start and end level,
              efficiency curve, start/stop cost, and the flow is pushed into the
              downstream node's up_inflow (:262-263).
  CHANNEL     one pass through the cascade of linear reservoirs, outflow pushed
              downstream (:105). Channels earn no income and value no water
              (:127) but they DO forward upstream_remaining_active_Mm3.

DETAILS A REASONABLE REIMPLEMENTATION WOULD GET WRONG

  1. The level the powerstation sees as `start_of_stp_masl` is the level at the
     END OF THE PREVIOUS STEP, before today's inflow. reservoir.cpp:483 -- the
     refresh after inflow -- is commented out, so `res_masl` at :499 is still
     last step's value. InitReservoir:321 sets it from the curve, so recomputing
     it from the carried volume is exact at t = 0 too.

  2. CalcOverflow's HRW clip sits INSIDE the `res_masl > masl_start_overflow`
     guard (:190-213). Hoisting it out makes `overflow = res_Mm3 - filling_at_hrw`
     fire with a negative value whenever the reservoir is below HRW, which
     subtracts a negative volume and pins the reservoir at HRW forever.

  3. The clip compares against RAW res_Mm3 (:208), not a curve round trip.

  4. There are TWO aggressive-action guards, and they are not redundant.
     GetTunnelFLow zeroes the RELEASE (powerstation.cpp:786-790); Simulate then
     zeroes the PRODUCTION because total_Q now exceeds the tunnel flow it was
     handed (:144-153). Both must fire, or a station produces from water that
     never left the reservoir.

  5. Efficiency is zero below 1e-6 m3/s (powerstation.cpp:85-87), not
     curve.x2y(0).

BRANCHES DELIBERATELY ABSENT, each verified in source for THIS topology:
  - OUTLET_HATCH is -9999 on all four reservoirs (params3 raises if not).
  - OUTLET_AUTO_QMIN, AUTO_QMIN and MAX_ADJUST are -9999 everywhere.
  - Channel QMIN is -9999 everywhere, so cost_qmin is identically zero.
  - POWSTAT_MIN_DISCHARGE is a SOFT constraint: powerstation.cpp:157-164 only
    logs a warning and the production-zeroing is commented out (:198). The
    shipped run trips it at t = 222 and 252 and still produces.
  - FLOODLEVEL_PENALTY is read from file but never applied (CLAUDE.md section 9).
  - FAST_OVERFLOW and USE_SPILLWAY are false, so CalcOverflow takes the
    overflow-curve branch.

ONE DELIBERATE DIVERGENCE. When the ArrayCurve round trip puts `res_masl` above
the overflow curve's first point while `res_Mm3` is still below filling_at_hrw,
HERSS computes a negative overflow and calls LOG_ERR, which exits the process
(reservoir.cpp:216-231). A search cannot have its evaluator abort, so the
replica clamps the overflow at zero. `step(..., trace=...)` counts every such
event in trace['negative_overflow_events']; validate3 and diagnose3 report the
count, so the divergence is measured rather than hidden. It is expected to be
zero -- the band is narrower than one ArrayCurve bucket.
"""

from dataclasses import dataclass

import numpy as np

from params3 import AGGRESSIVE_ACTIONS_COST, GRAVITY


# ------------------------------------------------------------------ compiled plan

@dataclass
class Plan:
    """
    Execution order and index bookkeeping, precomputed once per SystemParams.

    Rebuilding the idnr -> column maps inside the step would dominate the
    runtime; nothing here depends on the state.
    """
    p: object
    order: tuple                 # (kind, obj) in idnr order == execution order
    n_nodes: int
    node_col: dict               # idnr -> column in the up_inflow array
    res_col: dict                # reservoir idnr -> column in the volume array
    sta_col: dict                # station idnr -> column in the action array
    chan_slice: dict             # channel idnr -> slice into the linres array
    n_linres_total: int
    inflow_res_order: tuple      # reservoir idnrs, matching the inflow columns


def build_plan(p):
    order = []
    for idnr in sorted(p.node_kind):
        kind = p.node_kind[idnr]
        if kind == "RESERVOIR":
            order.append((kind, p.reservoir(idnr)))
        elif kind == "PSTATION":
            order.append((kind, p.station(idnr)))
        else:
            order.append((kind, next(c for c in p.channels if c.idnr == idnr)))

    chan_slice, k = {}, 0
    for c in p.channels:
        chan_slice[c.idnr] = slice(k, k + c.n_linres)
        k += c.n_linres

    return Plan(
        p=p, order=tuple(order), n_nodes=len(p.node_kind),
        node_col={idnr: i for i, idnr in enumerate(sorted(p.node_kind))},
        res_col={r.idnr: i for i, r in enumerate(p.reservoirs)},
        sta_col={s.idnr: i for i, s in enumerate(p.stations)},
        chan_slice=chan_slice, n_linres_total=k,
        inflow_res_order=tuple(r.idnr for r in p.reservoirs))


# ------------------------------------------------------------------ state

@dataclass
class State:
    """
    Everything carried from one timestep to the next, batched over axis 0.

    res_Mm3     (B, n_res)          reservoir volumes at the end of the step
    chan_m3     (B, n_linres_total) linear-reservoir storages, in m3
    prev_act    (B, n_sta)          previous step's generator actions
    """
    res_Mm3: np.ndarray
    chan_m3: np.ndarray
    prev_act: np.ndarray

    @property
    def B(self):
        return self.res_Mm3.shape[0]

    def copy(self):
        return State(self.res_Mm3.copy(), self.chan_m3.copy(), self.prev_act.copy())

    def take(self, idx):
        return State(self.res_Mm3[idx].copy(), self.chan_m3[idx].copy(),
                     self.prev_act[idx].copy())


def initial_state(plan, B=1, init_fr=None):
    """
    reservoir.cpp:315 for volumes, channel.cpp:301 for the linear reservoirs,
    powerstation.cpp:243-245 for the previous action at t = 0 (hardcoded 0.0,
    regardless of what the state file says).
    """
    p = plan.p
    fr = init_fr or {}
    res = np.empty((B, len(p.reservoirs)))
    for r in p.reservoirs:
        res[:, plan.res_col[r.idnr]] = r.init_Mm3(fr.get(r.idnr))

    chan = np.empty((B, plan.n_linres_total))
    for c in p.channels:
        chan[:, plan.chan_slice[c.idnr]] = np.asarray(c.init_storage_Mm3) * 1e6

    return State(res, chan, np.zeros((B, len(p.stations))))


# ------------------------------------------------------------------ pieces

def _overflow_Mm3(p, r, masl, res_Mm3):
    """
    reservoir.cpp:154-275 Reservoir::CalcOverflow, use_overflow_curve branch.

    The guard structure is load bearing -- see module docstring, point 2. The
    zero clamp is the one deliberate divergence, also documented there.
    """
    ov = p.m3s_to_Mm3(r.curve_overflow.x2y(masl))
    ov = np.minimum(ov, res_Mm3 - r.filling_at_hrw_Mm3)
    ov = np.where(masl > r.overflow_masl[0], ov, 0.0)
    return np.maximum(ov, 0.0)


def _efficiency(st, q):
    """powerstation.cpp:85-87 zero below 1e-6, :104 curve.x2y(q)/100."""
    return np.where(q < 0.000001, 0.0, st.curve_turbine.x2y(q) / 100.0)


def _route(plan, c, S_m3, q_in_m3s, dt):
    """
    cascadedreservoirs.cpp:83-117, in place on the (B, n_linres) storage slice.

    routeOneReservoir uses the exact discrete update of a linear reservoir under
    constant inflow over the step; the outflow reported is the STEP AVERAGE
    (volume balance), not the instantaneous end-of-step value.
    """
    f = c.decay(dt)
    k = c.k_res_seconds
    q = q_in_m3s
    for i in range(c.n_linres):
        s_old = S_m3[:, i]
        s_new = s_old * f + k * (1.0 - f) * q
        vol_out = s_old + q * dt - s_new
        S_m3[:, i] = s_new
        q = np.maximum(vol_out / dt, 0.0)
    return q


# ------------------------------------------------------------------ one timestep

def step(plan, state, actions, inflow_m3s, price, trace=None):
    """
    One HERSS timestep for the whole system.

    plan        from build_plan
    state       State, batch size B
    actions     (B, n_sta) generator actions in [0,1], column order == p.stations
    inflow_m3s  (n_res,) local inflow this step, order == plan.inflow_res_order
    price       scalar EUR/MWh
    trace       optional dict; when given, per-node quantities are recorded under
                (idnr, field) keys and negative-overflow events are counted

    Returns (profit, new_state) where profit is (B,) and already includes income
    minus every cost component CalcVF sums over all nodes: start/stop, aggressive
    actions and both reservoirs' LRW penalties.
    """
    p = plan.p
    dt = p.dt_seconds
    B = state.B

    res = state.res_Mm3.copy()
    chan = state.chan_m3.copy()
    up = np.zeros((B, plan.n_nodes))          # up_inflow [m3/s], per node column

    profit = np.zeros(B)
    # what each station is handed by its reservoir, before its own Simulate runs
    start_masl = {}
    end_masl = {}
    tunnel_m3s = {}
    # GetTunnelFLow charges the aggressive-action cost while the RESERVOIR runs
    # (powerstation.cpp:786-790 is called from reservoir.cpp:514), but HERSS
    # books it on the STATION's cost line (:288). Carried across so the traced
    # per-station profit matches the node output file.
    agg_by_station = {}

    for kind, node in plan.order:
        col = plan.node_col[node.idnr]

        # ------------------------------------------------ RESERVOIR
        if kind == "RESERVOIR":
            j = plan.res_col[node.idnr]
            v = res[:, j]

            # :499-503 the station sees the level from the END of the previous
            # step, before today's inflow, clipped at HRW.
            sm = np.minimum(node.curve_Mm3_2_masl.x2y(v), node.HRW)

            # :474-478 local inflow and upstream inflow, added separately.
            # res_col and inflow_res_order share p.reservoirs order, so j indexes
            # both the volume array and the inflow vector.
            q_local = inflow_m3s[j]
            v = v + p.m3s_to_Mm3(q_local) + p.m3s_to_Mm3(up[:, col])

            # :509 only water above LRW is usable for production
            up_res = np.maximum(0.0, v - node.filling_at_lrw_Mm3)

            # --- powerstation.cpp:746-793 GetTunnelFLow ---------------------
            st = p.station(p.tunnel_to[node.idnr])
            a = actions[:, plan.sta_col[st.idnr]]
            flow = np.where(a < 0.0000001, 0.0, a * st.max_discharge)
            Q_Mm3 = p.m3s_to_Mm3(flow)
            aggressive = Q_Mm3 > up_res
            agg_cost = np.where(aggressive, (Q_Mm3 - up_res) * AGGRESSIVE_ACTIONS_COST,
                                0.0)
            flow = np.where(aggressive, 0.0, flow)

            # :516 assignment, not accumulation -- a station's only upstream is
            # its own reservoir's tunnel.
            up[:, plan.node_col[st.idnr]] = flow
            tunnel_m3s[st.idnr] = flow
            agg_by_station[st.idnr] = agg_cost
            profit -= agg_cost

            # :536 subtract the release, :538-544 refresh the level
            v = v - p.m3s_to_Mm3(flow)
            masl = node.curve_Mm3_2_masl.x2y(v)

            # :625-637 overflow into the overflow node's up_inflow
            ov = _overflow_Mm3(p, node, masl, v)
            up[:, plan.node_col[p.overflow_to[node.idnr]]] += p.Mm3_to_m3s(ov)
            v = v - ov
            masl_end = node.curve_Mm3_2_masl.x2y(v)

            # :645-653 LRW penalty, proportional to the depth below LRW
            lrw = np.where(masl_end < node.LRW,
                           (node.RES_PENALTY * dt / 3600.0) * (node.LRW - masl_end),
                           0.0)
            profit -= lrw

            # :655-661 the station's end_of_stp_masl, HRW clipped
            start_masl[st.idnr] = sm
            end_masl[st.idnr] = np.minimum(masl_end, node.HRW)
            res[:, j] = v

            if trace is not None:
                _neg = np.minimum(p.m3s_to_Mm3(node.curve_overflow.x2y(masl)),
                                  v + ov - node.filling_at_hrw_Mm3)
                _neg = np.where(masl > node.overflow_masl[0], _neg, 0.0)
                trace.setdefault("negative_overflow_events", 0)
                trace["negative_overflow_events"] += int((_neg < 0.0).sum())
                trace.setdefault((node.idnr, "res_Mm3"), []).append(v.copy())
                trace.setdefault((node.idnr, "res_masl"), []).append(masl_end.copy())
                trace.setdefault((node.idnr, "res_fr"), []).append(
                    ((v - node.filling_at_lrw_Mm3) / node.active_capacity_Mm3).copy())
                trace.setdefault((node.idnr, "up_inflow_m3s"), []).append(up[:, col].copy())
                trace.setdefault((node.idnr, "tunnelflow_m3s"), []).append(flow.copy())
                trace.setdefault((node.idnr, "overflow_m3s"), []).append(
                    p.Mm3_to_m3s(ov).copy())
                trace.setdefault((node.idnr, "lrw_cost"), []).append(lrw.copy())

        # ------------------------------------------------ PSTATION
        elif kind == "PSTATION":
            k = plan.sta_col[node.idnr]
            a = actions[:, k]
            Q = a * node.max_discharge

            # :144-153 the second aggressive guard: up_inflow is the (possibly
            # zeroed) tunnel flow, so this fires exactly when the release was
            # zeroed. Not redundant -- see module docstring, point 4.
            Q = np.where(Q > up[:, col] * 1.000001, 0.0, Q)

            # :167 head from the average of the reservoir's start and end level
            Hb = (start_masl[node.idnr] + end_masl[node.idnr]) / 2.0 - node.powstat_masl
            # :173-175 shared penstock: head loss on the combined flow. With one
            # generator per station the two branches coincide, but both are kept
            # because the topology sets SHARED_PENSTOCK only on SVOLETJONN.
            Hn = Hb - node.headlosscoef * Q * Q

            eta = _efficiency(node, Q)
            mwh = (eta * 1000.0 * GRAVITY * Hn * Q / 1_000_000.0
                   * node.static_gen_efficiency * dt / 3600.0)
            income = mwh * price

            # :240-258 start/stop cost, counted per generator
            ss = np.where((a > 0.01) != (state.prev_act[:, k] > 0.01),
                          node.powstat_startstop / 2.0, 0.0)
            profit += income - ss

            # :262-263 the flow leaves for the downstream node
            dn = p.downlink_to[node.idnr]
            if dn is not None and dn >= 0:
                up[:, plan.node_col[dn]] += Q

            if trace is not None:
                agg = agg_by_station[node.idnr]
                trace.setdefault((node.idnr, "up_inflow_m3s"), []).append(up[:, col].copy())
                trace.setdefault((node.idnr, "tot_outflow_m3s"), []).append(Q.copy())
                trace.setdefault((node.idnr, "Hbrutto"), []).append(Hb.copy())
                trace.setdefault((node.idnr, "Hnetto"), []).append(Hn.copy())
                trace.setdefault((node.idnr, "power_MWh"), []).append(mwh.copy())
                trace.setdefault((node.idnr, "income"), []).append(income.copy())
                trace.setdefault((node.idnr, "startstop_cost"), []).append(ss.copy())
                trace.setdefault((node.idnr, "aggressive_cost"), []).append(agg.copy())
                # :283 profit = income - startstopCost - aggressive_actions_cost
                trace.setdefault((node.idnr, "profit"), []).append(
                    (income - ss - agg).copy())

        # ------------------------------------------------ CHANNEL
        else:
            sl = plan.chan_slice[node.idnr]
            q_out = _route(plan, node, chan[:, sl], up[:, col], dt)
            dn = p.channel_to[node.idnr]
            if dn is not None:
                up[:, plan.node_col[dn]] += q_out

            if trace is not None:
                trace.setdefault((node.idnr, "up_inflow_m3s"), []).append(up[:, col].copy())
                trace.setdefault((node.idnr, "storage_Mm3"), []).append(
                    chan[:, sl].sum(axis=1).copy() / 1e6)
                trace.setdefault((node.idnr, "tot_outflow_m3s"), []).append(q_out.copy())

    return profit, State(res, chan, actions.copy())


# ------------------------------------------------------------------ horizon

def terminal_value_Euro(plan, state, restprice):
    """
    riversystem.cpp:436,474 -- sum over PSTATION nodes of
    local_energy_equivalent * upstream_remaining_active_Mm3 * 1000, times
    restprice.

    Written per RESERVOIR using the chain equivalent, which is the same sum
    reindexed: herss.cpp:686-693 pushes each reservoir's remaining_active_Mm3
    down the chain, stations and channels forward it unchanged (both set their
    own remaining_active_Mm3 to zero), so

        SUM_s e_s * SUM_{r above s} ra_r  ==  SUM_r ra_r * SUM_{s below r} e_s

    build_utahps_daily.py checks the right-hand side against the simulator's own
    tot_remaining_MWh (58394.977 derived vs 58394.966 reported).

    Only water between LRW and HRW counts (reservoir.cpp:664-677): water above
    HRW is worth zero, which is what makes spill expensive.
    """
    p = plan.p
    mwh = np.zeros(state.B)
    for r in p.reservoirs:
        v = state.res_Mm3[:, plan.res_col[r.idnr]]
        fr = np.clip((v - r.filling_at_lrw_Mm3) / r.active_capacity_Mm3, 0.0, 1.0)
        mwh += p.chain_equivalent[r.idnr] * fr * r.active_capacity_Mm3 * 1000.0
    return mwh * restprice


def actions_to_matrix(plan, actions, T):
    """{'g<idnr>': [...]} -> (T, n_sta) in p.stations column order."""
    p = plan.p
    M = np.empty((T, len(p.stations)))
    for s in p.stations:
        series = actions[f"g{s.idnr}"]
        if len(series) != T:
            raise ValueError(f"g{s.idnr}: expected {T} actions, got {len(series)}")
        M[:, plan.sta_col[s.idnr]] = series
    return M


def simulate_sequence(plan, actions, inflow, prices, restprice, init_fr=None,
                      trace=None):
    """
    Full-horizon replica run for ONE action sequence.

    actions: {'g<idnr>': [...]} or a (T, n_sta) matrix.
    Returns (VF, per-step profit array).
    """
    p = plan.p
    T = len(prices)
    M = actions if isinstance(actions, np.ndarray) else actions_to_matrix(plan, actions, T)
    Q = np.array([[inflow[i][t] for i in plan.inflow_res_order] for t in range(T)])

    state = initial_state(plan, B=1, init_fr=init_fr)
    profits = np.empty(T)
    for t in range(T):
        pf, state = step(plan, state, M[t][None, :], Q[t], prices[t], trace=trace)
        profits[t] = pf[0]
    vf = profits.sum() + terminal_value_Euro(plan, state, restprice)[0]
    return vf, profits


def simulate_batch(plan, M, inflow, prices, restprice, init_fr=None):
    """
    Full-horizon value for B candidate trajectories.

    M: (B, T, n_sta). Returns (vf (B,), n_step_cells).
    """
    B, T, _ = M.shape
    Q = np.array([[inflow[i][t] for i in plan.inflow_res_order] for t in range(T)])
    state = initial_state(plan, B=B, init_fr=init_fr)
    total = np.zeros(B)
    for t in range(T):
        pf, state = step(plan, state, M[:, t, :], Q[t], prices[t])
        total += pf
    return total + terminal_value_Euro(plan, state, restprice), B * T
