#!/usr/bin/env python
"""
Diagnosis of a solution: what the policy actually does, node by node.

Objective values alone cannot support a claim about WHY one method beats
another, and in HERSS almost every constraint is penalised rather than enforced,
so a method can win by buying violations cheaply (CLAUDE.md section 11). Every
result therefore carries a feasibility table alongside its value.

The quantities here are the ones the run was designed to answer:

  spill        overflow volume and step count per reservoir -- the working
               hypothesis is that binding overflow is what makes the problem
               hard, and it is the only mechanism the single-reservoir slices
               could not exhibit in a cascade
  feasibility  aggressive actions, LRW penalties, start/stop, per node
  operation    level and head range per reservoir, distinct production levels
               per station
  coupling     correlation between stations' production series, and the
               realised throughflow each reservoir received from upstream --
               the difference between rho_own and what actually arrived
"""

import numpy as np

import replica3


def _flat(trace, key, T):
    """(idnr, field) trace, recorded as T arrays of shape (1,), as a length-T array."""
    return np.array([float(x[0]) for x in trace[key]]) if key in trace else np.zeros(T)


def summarise(s, tag, M):
    """Full diagnosis of one action matrix, evaluated through the replica."""
    p, plan, T = s.p, s.plan, s.T
    trace = {}
    inflow = {i: s.Q[:, j] for j, i in enumerate(plan.inflow_res_order)}
    vf, profits = replica3.simulate_sequence(plan, M, inflow, s.prices,
                                             s.restprice, trace=trace)

    out = {"tag": tag, "vf_replica": float(vf),
           "negative_overflow_events": int(trace.get("negative_overflow_events", 0))}

    # ---------------------------------------------------------------- spill
    spill = {}
    for r in p.reservoirs:
        ov = _flat(trace, (r.idnr, "overflow_m3s"), T)
        vol = p.m3s_to_Mm3(ov)
        spill[r.name] = {
            "overflow_Mm3": float(vol.sum()),
            "overflow_steps": int((ov > 1e-9).sum()),
            "overflow_max_m3s": float(ov.max()),
            # what that water would have been worth had it stayed below HRW
            "foregone_value_Euro": float(vol.sum() * p.chain_equivalent[r.idnr]
                                         * 1000.0 * s.restprice),
        }
    out["spill"] = spill

    # ---------------------------------------------------------- feasibility
    feas = {"per_reservoir": {}, "per_station": {}}
    for r in p.reservoirs:
        lrw = _flat(trace, (r.idnr, "lrw_cost"), T)
        masl = _flat(trace, (r.idnr, "res_masl"), T)
        feas["per_reservoir"][r.name] = {
            "lrw_cost_Euro": float(lrw.sum()),
            "lrw_steps": int((lrw > 1e-9).sum()),
            "steps_above_HRW": int((masl > r.HRW + 1e-9).sum()),
        }
    for st in p.stations:
        agg = _flat(trace, (st.idnr, "aggressive_cost"), T)
        ss = _flat(trace, (st.idnr, "startstop_cost"), T)
        feas["per_station"][st.name] = {
            "aggressive_cost_Euro": float(agg.sum()),
            "aggressive_steps": int((agg > 1e-9).sum()),
            "startstop_cost_Euro": float(ss.sum()),
            "startstop_events": int(round(ss.sum() / (st.powstat_startstop / 2.0)))
            if st.powstat_startstop else 0,
        }
    out["feasibility"] = feas

    # ------------------------------------------------------------ operation
    oper = {"per_reservoir": {}, "per_station": {}}
    for r in p.reservoirs:
        masl = _flat(trace, (r.idnr, "res_masl"), T)
        fr = _flat(trace, (r.idnr, "res_fr"), T)
        oper["per_reservoir"][r.name] = {
            "masl_min": float(masl.min()), "masl_max": float(masl.max()),
            "masl_range": float(masl.max() - masl.min()),
            "fr_min": float(fr.min()), "fr_max": float(fr.max()),
            "fr_end": float(fr[-1]),
            "LRW": r.LRW, "HRW": r.HRW,
        }
    prod = {}
    for st in p.stations:
        pw = _flat(trace, (st.idnr, "power_MWh"), T)
        hb = _flat(trace, (st.idnr, "Hbrutto"), T)
        hn = _flat(trace, (st.idnr, "Hnetto"), T)
        a = M[:, [k for k, x in enumerate(p.stations) if x.idnr == st.idnr][0]]
        prod[st.name] = pw
        oper["per_station"][st.name] = {
            "production_MWh": float(pw.sum()),
            "steps_producing": int((pw > 1e-9).sum()),
            "distinct_action_levels": int(len(np.unique(np.round(a, 6)))),
            "distinct_action_levels_at_1e3": int(len(np.unique(np.round(a, 3)))),
            "action_at_zero_steps": int((a < 1e-9).sum()),
            "action_at_one_steps": int((a > 1.0 - 1e-9).sum()),
            "Hbrutto_min": float(hb.min()), "Hbrutto_max": float(hb.max()),
            "Hnetto_min": float(hn.min()), "Hnetto_max": float(hn.max()),
        }
    out["operation"] = oper

    # ------------------------------------------------------------- coupling
    names = [st.name for st in p.stations]
    corr = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = prod[names[i]], prod[names[j]]
            if a.std() < 1e-12 or b.std() < 1e-12:
                corr[f"{names[i]}~{names[j]}"] = None
            else:
                corr[f"{names[i]}~{names[j]}"] = float(np.corrcoef(a, b)[0, 1])
    realised = {}
    for r in p.reservoirs:
        up = _flat(trace, (r.idnr, "up_inflow_m3s"), T)
        own = s.Q[:, plan.res_col[r.idnr]]
        realised[r.name] = {
            "own_inflow_Mm3": float(p.m3s_to_Mm3(own).sum()),
            "upstream_received_Mm3": float(p.m3s_to_Mm3(up).sum()),
            "upstream_share": float(p.m3s_to_Mm3(up).sum()
                                    / max(p.m3s_to_Mm3(up + own).sum(), 1e-12)),
        }
    out["coupling"] = {"production_correlation": corr,
                       "realised_inflow": realised}

    # ------------------------------------------------------------- economics
    income = sum(_flat(trace, (st.idnr, "income"), T).sum() for st in p.stations)
    out["economics"] = {
        "income_Euro": float(income),
        "profit_Euro": float(profits.sum()),
        "terminal_Euro": float(vf - profits.sum()),
        "terminal_share_of_vf": float((vf - profits.sum()) / vf),
        "production_MWh": float(sum(prod[n].sum() for n in names)),
    }
    return out


def realised_regime(s, M):
    """
    rho per reservoir using the inflow that ACTUALLY arrived under this policy,
    against the static bound in params3.regime_numbers.

    params3 can only bound the upstream contribution, because how much arrives
    is a function of the policy. This is the measured version, and the pair is
    what the report compares against the single-reservoir slices.
    """
    p, plan, T = s.p, s.plan, s.T
    trace = {}
    inflow = {i: s.Q[:, j] for j, i in enumerate(plan.inflow_res_order)}
    replica3.simulate_sequence(plan, M, inflow, s.prices, s.restprice, trace=trace)

    out = {}
    for r in p.reservoirs:
        st = p.station(p.tunnel_to[r.idnr])
        cap = st.n_generators * st.max_discharge * p.dt_seconds * T / 1e6
        own = float(p.m3s_to_Mm3(s.Q[:, plan.res_col[r.idnr]]).sum())
        up = float(p.m3s_to_Mm3(_flat(trace, (r.idnr, "up_inflow_m3s"), T)).sum())
        init = r.init_fr * r.active_capacity_Mm3
        out[r.name] = {
            "R": r.active_capacity_Mm3 / cap,
            "rho_own": (init + own) / cap,
            "rho_realised": (init + own + up) / cap,
            "own_inflow_Mm3": own, "upstream_received_Mm3": up,
            "init_active_Mm3": init, "station_capacity_Mm3": cap,
        }
    return out
