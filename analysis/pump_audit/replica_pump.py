#!/usr/bin/env python
"""
Python replica of one HERSS timestep for a topology containing a PUMP node.

Scope: the node classes used by the pump-audit instances -
RESERVOIR (curve-based, optional tunnel outlet, optional hatch outlet,
overflow curve), PSTATION (one generator, shared penstock), PUMP, CHANNEL
(cascade of linear reservoirs).

Every formula is cited against the C++ source at the commit under audit
(HERSS VERSION 4.0.00 / VERSION_DATE 20260814), repository commit 7c3d31e:

  src/pump.cpp          Pump::Simulate (:190-243), Pump::CalcPowerAndCost
                        (:247-329), Pump::calcEfficiency (:162-188)
  src/reservoir.cpp     Reservoir::Simulate (:466-770), CalcOverflow (:151-275),
                        InitReservoir (:299-...)
  src/powerstation.cpp  Powerstation::Simulate (:110-307), GetTunnelFLow,
                        calcEfficiency
  src/channel.cpp       Channel::Simulate, Channel::SetStartState (:338)
  src/cascadedreservoirs.cpp   route / routeOneReservoir
  src/herss.cpp         node loop + pump post-pass (:725-753)
  src/riversystem.cpp   Riversystem::CalcVF (:433-...)

THE THREE THINGS A REASONABLE REIMPLEMENTATION OF THE PUMP WOULD GET WRONG

 1. EXECUTION ORDER. herss.cpp:725-745 runs every node once per step in
    ASCENDING IDNR ORDER, and a PUMP's idnr is required to be lower than both
    its source and its target (Pump::ValidatePumpSettings). So the pump moves
    water BEFORE either reservoir runs: it sees the source volume as it stood
    at the END of the previous step, with none of this step's inflow and none
    of this step's turbine tailwater. Pumping and generating in the same step
    do NOT see each other.

 2. TWO-PHASE POWER. Pump::Simulate only moves water. Power, head and cost are
    computed afterwards, in a SECOND pass over pumps at the end of the step
    (herss.cpp:747-752), from src/tgt levels that the reservoirs recorded while
    they ran (reservoir.cpp:506-507 start, :715-716 end). The head is the
    difference of the two AVERAGED levels, so it already includes the effect of
    this step's own pumping on both reservoirs.

 3. THE HEAD DATUM IS NOT THE POWERSTATION'S. The pump lifts from the SOURCE
    RESERVOIR'S WATER LEVEL to the TARGET RESERVOIR'S WATER LEVEL; a turbine
    drops from its reservoir's level to the fixed POWSTAT_MASL. Head loss is
    ADDED for the pump (pump.cpp:268) and SUBTRACTED for a turbine. Efficiency
    DIVIDES for the pump (:299) and MULTIPLIES for a turbine.

Deliberately not implemented, each checked absent in the audit instances:
OUTLET_AUTO_QMIN, AUTO_QMIN, MAX_ADJUST, channel QMIN, FAST_OVERFLOW,
USE_SPILLWAY, reservoir geometry (all instances use RESERVOIR_CURVE),
multi-generator stations, PUMP_CURVE (all use UNIFORM_NORMALIZED_CURVE).
build_params() raises if an instance uses any of them.
"""

import math
from arraycurve import ArrayCurve

GRAVITY = 9.80665                      # src/herss.h
AGGRESSIVE_ACTIONS_COST = 1000.0       # src/herss.h:99
N_UNIFORM_EFF_CURVE_POINTS = 11        # src/herss.h


# ============================================================ node parameters

class Reservoir:
    def __init__(self, idnr, name, HRW, LRW, res_penalty, curve_masl, curve_Mm3,
                 ovfl_masl, ovfl_m3s, ovfl_to, tunnel_to=None,
                 hatch_to=None, hatch_minQ=0.0, hatch_maxQ=0.0, hatch_masl=0.0):
        self.idnr, self.name = idnr, name
        self.HRW, self.LRW, self.res_penalty = HRW, LRW, res_penalty
        self.masl2Mm3 = ArrayCurve(curve_masl, curve_Mm3)
        self.Mm32masl = ArrayCurve(curve_Mm3, curve_masl)
        self.ovfl = ArrayCurve(ovfl_masl, ovfl_m3s)
        self.ovfl_masl0 = ovfl_masl[0]
        self.ovfl_masl_max = ovfl_masl[-1]
        self.ovfl_to = ovfl_to
        self.tunnel_to = tunnel_to
        self.hatch_to = hatch_to
        self.hatch_minQ, self.hatch_maxQ = hatch_minQ, hatch_maxQ
        self.hatch_masl = hatch_masl
        # InitReservoir: filling at LRW/HRW straight off the curve
        self.fill_lrw = self.masl2Mm3.x2y_scalar(LRW)
        self.fill_hrw = self.masl2Mm3.x2y_scalar(HRW)
        self.fill_hatch = self.masl2Mm3.x2y_scalar(hatch_masl) if hatch_to is not None else 0.0

    def init_Mm3(self, fr):
        return self.fill_lrw + fr * (self.fill_hrw - self.fill_lrw)


class Pstation:
    def __init__(self, idnr, name, downlink_to, curve_Q, curve_psnt, max_discharge,
                 gen_eff, headlosscoef, powstat_masl, startstop, e_eq):
        self.idnr, self.name = idnr, name
        self.downlink_to = downlink_to
        self.turbine = ArrayCurve(curve_Q, curve_psnt)
        self.max_discharge = max_discharge
        self.gen_eff = gen_eff
        self.headlosscoef = headlosscoef
        self.powstat_masl = powstat_masl
        self.startstop = startstop
        self.e_eq = e_eq

    def eff(self, q):
        # powerstation.cpp calcEfficiency: hard zero below 1e-6
        return 0.0 if q < 0.000001 else self.turbine.x2y_scalar(q) / 100.0


class Pump:
    def __init__(self, idnr, name, source, target, inlet_masl, max_discharge,
                 headlosscoef, motor_eff, startstop, uniform_curve):
        self.idnr, self.name = idnr, name
        self.source, self.target = source, target
        self.inlet_masl = inlet_masl
        self.max_discharge = max_discharge
        self.headlosscoef = headlosscoef
        self.motor_eff = motor_eff
        self.startstop = startstop
        self.curve = list(uniform_curve)
        assert len(self.curve) == N_UNIFORM_EFF_CURVE_POINTS

    def eff(self, q):
        """pump.cpp:162-188 calcEfficiency, UNIFORM_NORMALIZED_CURVE branch.

        NOTE this is NOT ArrayCurve: it is a plain 11-point lookup on Qn =
        q/max_discharge with the top index clamped, so Qn == 1.0 lands on the
        segment [9,10] with t == 1.0. It never goes through ArrayCurve, and so
        never gets ArrayCurve's xdiff/ydiff sanity checks either.
        """
        if q < 0.000001:
            return 0.0
        n = N_UNIFORM_EFF_CURVE_POINTS
        Qn = q / self.max_discharge
        i = int(Qn * (n - 1))
        if i > n - 2:
            i = n - 2
        t = Qn * (n - 1) - i
        return (self.curve[i] + t * (self.curve[i + 1] - self.curve[i])) / 100.0


class Channel:
    def __init__(self, idnr, name, downstream_to, n_linres, k_hours):
        self.idnr, self.name = idnr, name
        self.downstream_to = downstream_to
        self.n_linres = n_linres
        # cascadedreservoirs.cpp: K is split across the cascade
        self.k_res_seconds = (k_hours * 3600.0) / n_linres if n_linres else 0.0


class Params:
    def __init__(self, dt, nodes, restprice):
        self.dt = dt
        self.nodes = nodes                       # idnr -> node object
        self.order = sorted(nodes)               # herss.cpp: ascending idnr
        self.restprice = restprice

    def m3s_to_Mm3(self, q):  return q * self.dt / 1e6
    def Mm3_to_m3s(self, v):  return v * 1e6 / self.dt


# ============================================================ one timestep

def step(p, state, actions, inflow_m3s, price, rec=None):
    """One HERSS timestep.

    state    dict: res_Mm3{idnr}, res_masl{idnr}, chan_m3{idnr:[...]},
             prev_act{idnr}
    actions  dict idnr -> action in [0,1] (stations, pumps, hatches)
    inflow   dict idnr -> local inflow [m3/s]
    Returns  (profit_Euro, new_state)
    """
    dt = p.dt
    res = dict(state["res_Mm3"])
    masl = dict(state["res_masl"])          # level carried from END of last step
    chan = {k: list(v) for k, v in state["chan_m3"].items()}
    up = {i: 0.0 for i in p.order}          # up_inflow [m3/s]

    profit = 0.0
    pump_src_start, pump_src_end = {}, {}
    pump_tgt_start, pump_tgt_end = {}, {}
    pumped_Mm3 = {}
    st_start_masl, st_end_masl = {}, {}
    agg_cost = {}

    for idnr in p.order:
        nd = p.nodes[idnr]

        # ------------------------------------------------------------ PUMP
        if isinstance(nd, Pump):
            # pump.cpp:190-243. Runs BEFORE both reservoirs (idnr is lower), so
            # res[source] here is still the end-of-previous-step volume.
            a = actions.get(idnr, 0.0)
            if a < -0.000001 or a > 1.000001:
                raise ValueError(f"pump action out of range: {a} (HERSS exits here)")
            req_Mm3 = p.m3s_to_Mm3(max(0.0, a) * nd.max_discharge)
            src = p.nodes[nd.source]
            fill_at_inlet = src.masl2Mm3.x2y_scalar(nd.inlet_masl)
            available = max(0.0, res[nd.source] - fill_at_inlet)
            actual = min(req_Mm3, available)

            res[nd.source] -= actual        # :224
            res[nd.target] += actual        # :228
            pumped_Mm3[idnr] = actual
            continue

        # ------------------------------------------------------- RESERVOIR
        if isinstance(nd, Reservoir):
            v = res[idnr]
            m = masl[idnr]                  # :506 - stale level, NOT refreshed

            # :506-507 / :715-716 the pump records start and end levels here
            for q in p.order:
                nq = p.nodes[q]
                if isinstance(nq, Pump):
                    if nq.source == idnr: pump_src_start[q] = m
                    if nq.target == idnr: pump_tgt_start[q] = m

            v += p.m3s_to_Mm3(inflow_m3s.get(idnr, 0.0))      # :492
            v += p.m3s_to_Mm3(up[idnr])                        # :497

            tunnel_Mm3 = 0.0
            if nd.tunnel_to is not None:
                st = p.nodes[nd.tunnel_to]
                sm = min(m, nd.HRW)                            # :520-524
                up_res = max(0.0, v - nd.fill_lrw)             # :531
                a = actions.get(st.idnr, 0.0)
                flow = 0.0 if a < 0.0000001 else a * st.max_discharge
                Q_Mm3 = p.m3s_to_Mm3(flow)
                if Q_Mm3 > up_res:                             # GetTunnelFLow
                    agg_cost[st.idnr] = (Q_Mm3 - up_res) * AGGRESSIVE_ACTIONS_COST
                    flow = 0.0
                else:
                    agg_cost[st.idnr] = 0.0
                up[st.idnr] = flow
                tunnel_Mm3 = p.m3s_to_Mm3(flow)
                st_start_masl[st.idnr] = sm
            v -= tunnel_Mm3                                    # :559
            m = nd.Mm32masl.x2y_scalar(v)                      # :566

            hatch_Mm3 = 0.0
            if nd.hatch_to is not None:                        # :572-610
                ah = actions.get(idnr, 0.0)
                if ah < -0.000001 or ah > 1.000001:
                    raise ValueError(f"hatch action out of range: {ah}")
                if m > nd.hatch_masl:
                    q = nd.hatch_minQ + ah * (nd.hatch_maxQ - nd.hatch_minQ)
                    hatch_Mm3 = p.m3s_to_Mm3(q)
                    cur = nd.masl2Mm3.x2y_scalar(m)
                    hatch_Mm3 = min(hatch_Mm3, cur - nd.fill_hatch)
                up[nd.hatch_to] += p.Mm3_to_m3s(hatch_Mm3)
                v -= hatch_Mm3
                m = nd.Mm32masl.x2y_scalar(v)

            # ----- CalcOverflow :151-275, overflow-curve branch -------------
            ov = 0.0
            if m > nd.ovfl_masl0:
                if m > nd.ovfl_masl_max:
                    raise ValueError(f"res_masl {m} above overflow curve max "
                                     f"{nd.ovfl_masl_max} (HERSS exits here)")
                ov = p.m3s_to_Mm3(nd.ovfl.x2y_scalar(m))
                ov = min(ov, v - nd.fill_hrw)                  # :208-210
                if ov < 0.0:
                    raise ValueError("negative overflow (HERSS exits here)")
            up[nd.ovfl_to] += p.Mm3_to_m3s(ov)
            v -= ov                                            # :686
            m = nd.Mm32masl.x2y_scalar(v)                      # :691-696

            if nd.tunnel_to is not None:
                st_end_masl[nd.tunnel_to] = min(m, nd.HRW)     # :704-709

            for q in p.order:
                nq = p.nodes[q]
                if isinstance(nq, Pump):
                    if nq.source == idnr: pump_src_end[q] = m
                    if nq.target == idnr: pump_tgt_end[q] = m

            if m < nd.LRW:                                     # :700
                profit -= (nd.res_penalty * dt / 3600.0) * (nd.LRW - m)

            res[idnr], masl[idnr] = v, m
            if rec is not None:
                rec.setdefault((idnr, "res_Mm3"), []).append(v)
                rec.setdefault((idnr, "res_masl"), []).append(m)
                rec.setdefault((idnr, "overflow_m3s"), []).append(p.Mm3_to_m3s(ov))
                rec.setdefault((idnr, "tunnelflow_m3s"), []).append(p.Mm3_to_m3s(tunnel_Mm3))
                rec.setdefault((idnr, "hatchflow_m3s"), []).append(p.Mm3_to_m3s(hatch_Mm3))
            continue

        # -------------------------------------------------------- PSTATION
        if isinstance(nd, Pstation):
            a = actions.get(idnr, 0.0)
            Q = a * nd.max_discharge
            if Q > up[idnr] * 1.000001:        # powerstation.cpp:144-153
                Q = 0.0
            Hb = (st_start_masl[idnr] + st_end_masl[idnr]) / 2.0 - nd.powstat_masl
            Hn = Hb - nd.headlosscoef * Q * Q
            eta = nd.eff(Q)
            mwh = (eta * 1000.0 * GRAVITY * Hn * Q / 1e6) * nd.gen_eff * dt / 3600.0
            income = mwh * price
            ss = (nd.startstop / 2.0
                  if (a > 0.01) != (state["prev_act"].get(idnr, 0.0) > 0.01) else 0.0)
            profit += income - ss - agg_cost.get(idnr, 0.0)
            if nd.downlink_to is not None and nd.downlink_to >= 0:
                up[nd.downlink_to] += Q
            if rec is not None:
                rec.setdefault((idnr, "Power"), []).append(mwh)
                rec.setdefault((idnr, "income"), []).append(income)
                rec.setdefault((idnr, "Hbrutto"), []).append(Hb)
                rec.setdefault((idnr, "Hnetto"), []).append(Hn)
            continue

        # --------------------------------------------------------- CHANNEL
        if isinstance(nd, Channel):
            q = up[idnr]
            S = chan[idnr]
            f = math.exp(-dt / nd.k_res_seconds) if nd.k_res_seconds > 0 else 0.0
            for i in range(nd.n_linres):
                s_old = S[i]
                s_new = s_old * f + nd.k_res_seconds * (1.0 - f) * q
                vol_out = s_old + q * dt - s_new
                S[i] = s_new
                q = max(vol_out / dt, 0.0)
            if nd.downstream_to is not None and nd.downstream_to >= 0:
                up[nd.downstream_to] += q
            if rec is not None:
                rec.setdefault((idnr, "tot_outflow"), []).append(q)
            continue

    # ---- second pass over pumps: herss.cpp:747-752 -> Pump::CalcPowerAndCost
    for idnr in p.order:
        nd = p.nodes[idnr]
        if not isinstance(nd, Pump):
            continue
        actual = pumped_Mm3.get(idnr, 0.0)
        Q = p.Mm3_to_m3s(actual)
        src_avg = (pump_src_start[idnr] + pump_src_end[idnr]) / 2.0     # :259
        tgt_avg = (pump_tgt_start[idnr] + pump_tgt_end[idnr]) / 2.0
        Hb = tgt_avg - src_avg                                          # :262
        Hn = Hb + nd.headlosscoef * Q * Q                               # :268 ADDED
        if Hn < 0.0:
            raise ValueError("negative pump net head (HERSS exits here)")
        eta = nd.eff(Q)
        P_hyd_MW = 1000.0 * GRAVITY * Hn * Q / 1e6                      # :297
        power_MW = P_hyd_MW / (eta * nd.motor_eff) if eta > 0.0 else 0.0  # :299 DIVIDED
        mwh = power_MW * dt / 3600.0
        cost = mwh * price
        a = actions.get(idnr, 0.0)
        # :308-318 start/stop keys off the ACTION, not the actual pumped volume
        ss = (nd.startstop / 2.0
              if (a > 0.01) != (state["prev_act"].get(idnr, 0.0) > 0.01) else 0.0)
        profit -= cost + ss
        if rec is not None:
            rec.setdefault((idnr, "pumped_Mm3"), []).append(actual)
            rec.setdefault((idnr, "Power"), []).append(-mwh)
            rec.setdefault((idnr, "cost"), []).append(cost + ss)
            rec.setdefault((idnr, "Hbrutto"), []).append(Hb)
            rec.setdefault((idnr, "Hnetto"), []).append(Hn)

    new_prev = dict(state["prev_act"])
    for idnr in p.order:
        if isinstance(p.nodes[idnr], (Pstation, Pump)):
            new_prev[idnr] = actions.get(idnr, 0.0)
    return profit, dict(res_Mm3=res, res_masl=masl, chan_m3=chan, prev_act=new_prev)


# ============================================================ horizon / VF

def terminal_value_Euro(p, state, restprice):
    """riversystem.cpp CalcVF: sum over PSTATION of
    e_eq * upstream_remaining_active_Mm3 * 1000, times restprice.

    upstream_remaining_active is accumulated by walking each reservoir's chain
    downstream (herss.cpp:759-768); a PUMP has remaining_active_Mm3 == 0 and no
    ptr_downstream_node, so it forwards nothing and is invisible to this term.
    A pump therefore changes the terminal value ONLY through the volumes it
    left in the two reservoirs.
    """
    tot_MWh = 0.0
    for idnr in p.order:
        nd = p.nodes[idnr]
        if not isinstance(nd, Pstation):
            continue
        upstream = 0.0
        for r in p.order:
            rn = p.nodes[r]
            if not isinstance(rn, Reservoir):
                continue
            if _flows_into(p, r, idnr):
                v = state["res_Mm3"][r]
                fr = (v - rn.fill_lrw) / (rn.fill_hrw - rn.fill_lrw)
                act = fr * (rn.fill_hrw - rn.fill_lrw)
                if fr > 1.0: act = rn.fill_hrw - rn.fill_lrw
                if fr < 0.0: act = 0.0
                upstream += act
        tot_MWh += nd.e_eq * upstream * 1e6 / 1e3
    return tot_MWh * restprice, tot_MWh


def _flows_into(p, res_idnr, station_idnr):
    """Walk the downstream chain from a reservoir; True if it reaches the station."""
    seen, cur = set(), res_idnr
    while cur is not None and cur >= 0 and cur not in seen:
        seen.add(cur)
        nd = p.nodes.get(cur)
        if cur == station_idnr:
            return True
        if isinstance(nd, Reservoir):
            # reservoir.cpp:1147-1154: downstream_idnr is the TUNNEL node when
            # there is one, otherwise the OVERFLOW node. The hatch node is NOT
            # on this chain, even when the hatch is the reservoir's only real
            # outlet - so terminal value follows the overflow path.
            cur = nd.tunnel_to if nd.tunnel_to is not None else nd.ovfl_to
        elif isinstance(nd, Pstation):
            cur = nd.downlink_to
        elif isinstance(nd, Channel):
            cur = nd.downstream_to
        else:
            return False
    return False


def simulate(p, init_fr, action_seq, inflow_seq, prices, restprice, chan_init):
    """Full horizon. Returns (VF, profit_total, terminal_Euro, rec)."""
    state = dict(
        res_Mm3={i: p.nodes[i].init_Mm3(init_fr[i])
                 for i in p.order if isinstance(p.nodes[i], Reservoir)},
        res_masl={}, chan_m3={}, prev_act={})
    for i in p.order:
        nd = p.nodes[i]
        if isinstance(nd, Reservoir):
            state["res_masl"][i] = nd.Mm32masl.x2y_scalar(state["res_Mm3"][i])
        elif isinstance(nd, Channel):
            state["chan_m3"][i] = [x * 1e6 for x in chan_init[i]]
    rec, total = {}, 0.0
    for t, price in enumerate(prices):
        pr, state = step(p, state, action_seq[t], inflow_seq[t], price, rec)
        total += pr
    term_E, term_MWh = terminal_value_Euro(p, state, restprice)
    return total + term_E, total, term_E, rec, state
