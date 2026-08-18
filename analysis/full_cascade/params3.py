#!/usr/bin/env python
r"""
Instance parameters for the full uTAHPS cascade (`utahps_daily`).

Unlike params2.py, which hardcodes the two res_casc_A reservoirs, this module
PARSES analysis/instances/utahps_daily/topology.txt. Twelve nodes with reservoir
curves of 7-14 points each are too much to transcribe by hand without an error
that would silently bias every later number.

Topology, as parsed (idnr in parentheses):

    HJELLE (0) --tunnel--> SVOLETJONN (1) --> VANAROSEN (2) ---\
      |                                                          \
      overflow ------------------------------> VANAROSEN (2)      +--> TOPPSY (5)
                                                                 /
    GRESSE (3) --overflow--> GRONANI (4) ---------------------- /
      |
      tunnel --> SVEIGSHYL_II (7) --\
                                     +--> DALSANA (8) --> KROKNESVATN (9)
    TOPPSY (5) --tunnel--> SVEIGSHYL_I (6) --/                      |
      |                                                             tunnel
      overflow --> DALSANA (8)                                        |
                                                                      v
                                                              EASTER (10) --> HYNNEKLEIV (11) --> outlet
                                                                      ^
    KROKNESVATN (9) --overflow--> HYNNEKLEIV (11) -------------------/

Three facts about this instance, all verified in source and confirmed against
the shipped output file, drive the rest of the harness:

  1. THE CASCADE TERMINAL TERM WORKS HERE. All four reservoirs have
     OUTLET_TUNNEL, so reservoir.cpp:1063-1073 points ptr_downstream_node at the
     POWERSTATION, not the overflow node. The res_casc_A pathology -- upper
     reservoir water worth exactly zero -- does not recur. herss.cpp:686-693
     accumulates upstream_remaining_active_Mm3 in a SINGLE pass over nodes in
     idnr order, which is correct here only because every downstream idnr is
     larger than its upstream idnr; assert_topological_order() checks that
     rather than assuming it.

     Chain equivalents, i.e. the sum of LOCAL_ENERGY_EQUIVALENT over every
     PSTATION a reservoir's water still has to pass:

         HJELLE       0.11 + 0.11 + 0.11 = 0.33 kWh/m3
         GRESSE       0.39 + 0.11        = 0.50
         TOPPSY       0.11 + 0.11        = 0.22
         KROKNESVATN  0.11               = 0.11

     Checked against data/utahps_daily/output/riversystem_uTAHPS_output.txt:
     the shipped run ends with active volumes 2.2569 / 15.74 / 126.64 / 199.27
     Mm3, and 0.33*2.2569 + 0.50*15.74 + 0.22*126.64 + 0.11*199.27, times 1000,
     is 58396 MWh against the file's tot_remaining_MWh = 58394.966.

  2. THE ROUTING DELAY IS SUB-TIMESTEP. K_TRAVELTIME_HOURS is 4/1/6/4 h against
     dt = 86400 s, so exp(-dt/k_res) underflows to ~0 and 77-96 % of an impulse
     leaves the channel in the SAME step (see channel_impulse_response()). Node
     execution is idnr-ordered WITHIN a step (herss.cpp:669-677), so an upstream
     release at t reaches the downstream station at t. The cascade coupling is
     same-step; there is no tau >= 1 lag to exploit at daily resolution.

  3. CHANNELS CANNOT BE DROPPED. In res_casc_A every channel sat downstream of
     the only station and was provably value-neutral. Here VANAROSEN, GRONANI
     and DALSANA carry water BETWEEN power stations, so their storage changes
     what the downstream reservoir has available. They earn no income and
     channel.cpp:127 sets their remaining_active_Mm3 to 0, but channel.cpp:105
     forwards their outflow and herss.cpp:692 forwards their
     upstream_remaining_active_Mm3.

Cited line numbers are upstream commit 029a2d5, HERSS VERSION 3.1.03 /
VERSION_DATE 20260611.
"""

import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "analysis", "scarcity_gap"))
sys.path.insert(0, os.path.join(REPO, "analysis", "cascade"))

from arraycurve import ArrayCurve                      # noqa: E402  reused unchanged
from params2 import (AGGRESSIVE_ACTIONS_COST, GRAVITY,  # noqa: E402  reused unchanged
                     ReservoirParams, StationParams)

NOT_IN_USE = -9999


# ------------------------------------------------------------------ topology parsing

def _strip(path):
    """Topology lines with comments and blanks removed, tokenised."""
    out = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line.split())
    return out


def _f(tok):
    return float(tok)


def _i(tok):
    return int(float(tok))


def parse_topology(path):
    """
    {idnr: node dict} for every NODE block in the topology file.

    Curve keywords are followed by N data rows that are not keywords, so they
    are consumed explicitly rather than by keyword dispatch.
    """
    rows = _strip(path)
    nodes = {}
    i = 0
    while i < len(rows):
        r = rows[i]
        if r[0] != "NODE":
            i += 1
            continue
        kind, idnr, name = r[1], _i(r[2]), r[3]
        node = {"kind": kind, "idnr": idnr, "name": name}
        if kind == "CHANNEL":
            # NODE CHANNEL idnr name downstream_idnr
            node["downstream_idnr"] = _i(r[4])
        i += 1
        while i < len(rows) and rows[i][0] != "ENDNODE":
            k = rows[i]
            key = k[0]
            if key == "RESERVOIR_CURVE":
                n = _i(k[1])
                pts = rows[i + 1:i + 1 + n]
                node["curve_masl"] = [_f(p[0]) for p in pts]
                node["curve_Mm3"] = [_f(p[1]) for p in pts]
                i += n
            elif key == "OVERFLOW_CURVE":
                n = _i(k[1])
                node["overflow_to"] = _i(k[2])
                pts = rows[i + 1:i + 1 + n]
                node["overflow_masl"] = [_f(p[0]) for p in pts]
                node["overflow_m3s"] = [_f(p[1]) for p in pts]
                i += n
            elif key == "TURBINE_CURVE":
                n = _i(k[1])
                pts = rows[i + 1:i + 1 + n]
                node.setdefault("turbine_q", {})[node["_gen"]] = [_f(p[0]) for p in pts]
                node.setdefault("turbine_pct", {})[node["_gen"]] = [_f(p[1]) for p in pts]
                i += n
            elif key == "GENERATOR":
                node["_gen"] = _i(k[1])
            elif key == "GENERATOR_MAX_DISCHARGE":
                node.setdefault("gen_max_discharge", {})[node["_gen"]] = _f(k[1])
            elif key == "SHARED_PENSTOCK":
                node["shared_penstock"] = k[1].upper() == "TRUE"
            elif key in ("NR_GENERATORS", "DOWNLINK_IDNR", "OUTLET_HATCH",
                         "OUTLET_TUNNEL", "OUTLET_AUTO_QMIN", "N_CASCADE_LINRES",
                         "AUTO_QMIN", "MAX_ADJUST", "QMIN"):
                node[key.lower()] = _i(k[1])
            else:
                node[key.lower()] = _f(k[1])
            i += 1
        node.pop("_gen", None)
        nodes[idnr] = node
        i += 1
    return nodes


def parse_start_state(path):
    """
    {'reservoirs': {idnr: init_fr}, 'channels': {idnr: [Mm3, ...]}}

    Channel storages are read positionally after the node name, matching
    channel.cpp:339-351.
    """
    res, chan = {}, {}
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tok = line.split()
            if tok[0] != "NODE":
                continue
            if tok[1] == "RESERVOIR":
                res[int(tok[2])] = float(tok[4])
            elif tok[1] == "CHANNEL":
                chan[int(tok[2])] = [float(x) for x in tok[4:]]
    return {"reservoirs": res, "channels": chan}


# ------------------------------------------------------------------ channel params

@dataclass(frozen=True)
class ChannelParams:
    """
    One CHANNEL node: a cascade of linear reservoirs.

    cascadedreservoirs.cpp:41  k_res = K_TRAVELTIME_HOURS*3600 / N_CASCADE_LINRES
    cascadedreservoirs.cpp:106 S_next = S*exp(-dt/k_res) + k_res*(1-exp)*q_in
    """
    name: str
    idnr: int
    n_linres: int
    K_traveltime_hours: float
    downstream_idnr: int          # < 0 = system outlet
    init_storage_Mm3: tuple

    k_res_seconds: float = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "k_res_seconds",
                           self.K_traveltime_hours * 3600.0 / self.n_linres)

    @property
    def in_use_downstream(self):
        return self.downstream_idnr >= 0

    def decay(self, dt_seconds):
        return math.exp(-dt_seconds / self.k_res_seconds)


# ------------------------------------------------------------------ system params

@dataclass(frozen=True)
class SystemParams:
    """The whole river system, ordered by idnr, which is also execution order."""
    name: str
    dataset_dir: str
    globalfile: str
    pricefile: str
    inflowfile: str
    actionfile: str
    dt_seconds: float

    reservoirs: tuple            # ReservoirParams, ascending idnr
    stations: tuple              # StationParams, ascending idnr
    channels: tuple              # ChannelParams, ascending idnr

    node_kind: dict              # idnr -> 'RESERVOIR' | 'PSTATION' | 'CHANNEL'
    tunnel_to: dict              # reservoir idnr -> station idnr
    overflow_to: dict            # reservoir idnr -> node idnr
    downlink_to: dict            # station idnr -> node idnr
    channel_to: dict             # channel idnr -> node idnr, or None
    chain_equivalent: dict       # reservoir idnr -> kWh/m3 over the whole chain

    horizon: tuple = None        # (t_start, t_end) half-open, or None for all

    def m3s_to_Mm3(self, q):
        return q * self.dt_seconds / 1_000_000.0

    def Mm3_to_m3s(self, v):
        return v * 1_000_000.0 / self.dt_seconds

    @property
    def res_idnrs(self):
        return tuple(r.idnr for r in self.reservoirs)

    @property
    def sta_idnrs(self):
        return tuple(s.idnr for s in self.stations)

    @property
    def chan_idnrs(self):
        return tuple(c.idnr for c in self.channels)

    @property
    def action_names(self):
        """One decision variable per generator. No reservoir has a hatch here."""
        return tuple(f"g{s.idnr}" for s in self.stations)

    def station(self, idnr):
        return next(s for s in self.stations if s.idnr == idnr)

    def reservoir(self, idnr):
        return next(r for r in self.reservoirs if r.idnr == idnr)


def _downstream_of(nodes, idnr):
    """
    ptr_downstream_node, as HERSS assigns it.

    reservoir.cpp:1063-1073  overflow first, then tunnel OVERWRITES it if present
    powerstation.cpp         DOWNLINK_IDNR
    channel.cpp:188-195      the NODE line's last field, negative = outlet
    """
    n = nodes[idnr]
    if n["kind"] == "RESERVOIR":
        if n.get("outlet_tunnel", NOT_IN_USE) != NOT_IN_USE:
            return n["outlet_tunnel"]
        return n["overflow_to"]
    if n["kind"] == "PSTATION":
        return n["downlink_idnr"]
    d = n["downstream_idnr"]
    return d if d >= 0 else None


def assert_topological_order(nodes):
    """
    herss.cpp:686-693 pushes remaining water downstream in ONE pass over nodes in
    idnr order. That is only correct if every link points at a larger idnr; a
    back-edge would silently drop the contribution. Checked, not assumed.
    """
    for idnr in sorted(nodes):
        d = _downstream_of(nodes, idnr)
        if d is not None and d <= idnr:
            raise AssertionError(
                f"node {idnr} ({nodes[idnr]['name']}) points downstream at {d}: "
                "the single-pass terminal accumulation in herss.cpp:686-693 "
                "would be wrong for this topology")


def chain_equivalents(nodes):
    """
    reservoir idnr -> sum of LOCAL_ENERGY_EQUIVALENT over every PSTATION on the
    path to the outlet.

    This is exactly what herss.cpp:686-693 computes cumulatively: a reservoir's
    remaining_active_Mm3 is added to its downstream node's
    upstream_remaining_active_Mm3, channels and stations forward it unchanged
    (channel.cpp:127 and powerstation.cpp:294-295 both set their OWN
    remaining_active_Mm3 to 0), and riversystem.cpp:436,474 multiplies each
    station's accumulated total by that station's own energy equivalent.
    """
    out = {}
    for idnr, n in nodes.items():
        if n["kind"] != "RESERVOIR":
            continue
        total, cur, seen = 0.0, _downstream_of(nodes, idnr), set()
        while cur is not None:
            if cur in seen:
                raise AssertionError(f"cycle in topology at node {cur}")
            seen.add(cur)
            if nodes[cur]["kind"] == "PSTATION":
                total += nodes[cur]["local_energy_equivalent"]
            cur = _downstream_of(nodes, cur)
        out[idnr] = total
    return out


def build_system(dataset_dir, name="utahps_daily",
                 globalfile="global_utahps_daily.txt",
                 topologyfile="topology_utahps.txt",
                 startstatefile="start_state_utahps.txt",
                 pricefile="pricefile_utahps.txt",
                 inflowfile="inflowseries_utahps.txt",
                 actionfile="actions_utahps.txt",
                 dt_seconds=86400.0, horizon=None):
    if not dataset_dir.endswith("/"):
        dataset_dir += "/"
    nodes = parse_topology(dataset_dir + topologyfile)
    state = parse_start_state(dataset_dir + startstatefile)
    assert_topological_order(nodes)

    reservoirs, stations, channels = [], [], []
    for idnr in sorted(nodes):
        n = nodes[idnr]
        if n["kind"] == "RESERVOIR":
            if n.get("outlet_hatch", NOT_IN_USE) != NOT_IN_USE:
                raise NotImplementedError(
                    f"reservoir {n['name']} has an outlet hatch; replica3 models "
                    "tunnel + overflow only")
            reservoirs.append(ReservoirParams(
                name=n["name"], idnr=idnr,
                HRW=n["hrw"], LRW=n["lrw"], RES_PENALTY=n["res_penalty"],
                curve_masl=np.array(n["curve_masl"]),
                curve_Mm3=np.array(n["curve_Mm3"]),
                overflow_masl=np.array(n["overflow_masl"]),
                overflow_m3s=np.array(n["overflow_m3s"]),
                init_fr=state["reservoirs"][idnr]))
        elif n["kind"] == "PSTATION":
            ng = n["nr_generators"]
            if ng != 1:
                raise NotImplementedError(
                    f"station {n['name']} has {ng} generators; this instance is "
                    "one generator per station")
            stations.append(StationParams(
                name=n["name"], idnr=idnr, n_generators=ng,
                max_discharge=n["gen_max_discharge"][0],
                static_gen_efficiency=n["static_generator_efficiency"],
                headlosscoef=n["headlosscoef"],
                # powerstation.cpp:24 -- default false, only set by the keyword
                shared_penstock=n.get("shared_penstock", False),
                powstat_masl=n["powstat_masl"],
                powstat_startstop=n["powstat_startstop"],
                local_energy_equivalent=n["local_energy_equivalent"],
                turbine_q=np.array(n["turbine_q"][0]),
                turbine_pct=np.array(n["turbine_pct"][0])))
        else:
            channels.append(ChannelParams(
                name=n["name"], idnr=idnr,
                n_linres=n["n_cascade_linres"],
                K_traveltime_hours=n["k_traveltime_hours"],
                downstream_idnr=n["downstream_idnr"],
                init_storage_Mm3=tuple(state["channels"][idnr])))
            if len(state["channels"][idnr]) != n["n_cascade_linres"]:
                raise ValueError(
                    f"channel {n['name']}: state file has "
                    f"{len(state['channels'][idnr])} storages, topology says "
                    f"{n['n_cascade_linres']}")

    return SystemParams(
        name=name, dataset_dir=dataset_dir, globalfile=globalfile,
        pricefile=pricefile, inflowfile=inflowfile, actionfile=actionfile,
        dt_seconds=dt_seconds,
        reservoirs=tuple(reservoirs), stations=tuple(stations),
        channels=tuple(channels),
        node_kind={i: nodes[i]["kind"] for i in sorted(nodes)},
        tunnel_to={r.idnr: nodes[r.idnr]["outlet_tunnel"] for r in reservoirs},
        overflow_to={r.idnr: nodes[r.idnr]["overflow_to"] for r in reservoirs},
        downlink_to={s.idnr: nodes[s.idnr]["downlink_idnr"] for s in stations},
        channel_to={c.idnr: (c.downstream_idnr if c.in_use_downstream else None)
                    for c in channels},
        chain_equivalent=chain_equivalents(nodes),
        horizon=horizon)


# ------------------------------------------------------------------ series

def load_series(p):
    """
    (prices, inflow, restprice) with inflow a {reservoir_idnr: [m3/s]} dict.

    The inflow file's header names reservoir idnrs; only reservoirs receive
    local inflow in this topology.
    """
    with open(p.dataset_dir + p.pricefile) as f:
        lines = [l.strip() for l in f if l.strip()]
    restprice = float(lines[0].split()[1])
    prices = [float(l.split()[1]) for l in lines[2:]]

    with open(p.dataset_dir + p.inflowfile) as f:
        rows = [l.split() for l in f if l.strip()]
    header = rows[0]
    inflow = {}
    for r in p.reservoirs:
        col = header.index(str(r.idnr))
        inflow[r.idnr] = [float(row[col]) for row in rows[1:]]
        assert len(inflow[r.idnr]) == len(prices)

    if p.horizon is not None:
        t0, t1 = p.horizon
        prices = prices[t0:t1]
        inflow = {k: v[t0:t1] for k, v in inflow.items()}

    return prices, inflow, restprice


def load_actions(p, path=None):
    """The shipped action file as {'g<idnr>': [...]} (B0)."""
    with open(path or (p.dataset_dir + p.actionfile)) as f:
        rows = [l.split() for l in f if l.strip()]
    header = rows[0]
    out = {}
    for s in p.stations:
        col = header.index(f"{s.idnr}_0")
        series = [float(r[col]) for r in rows[1:]]
        out[f"g{s.idnr}"] = series[p.horizon[0]:p.horizon[1]] if p.horizon else series
    return out


# ------------------------------------------------------------------ diagnostics

def channel_impulse_response(p, n_steps=6):
    """
    Fraction of a unit impulse leaving each channel in step 0, 1, 2, ...

    Not a model component -- it is the measurement behind premise correction 2.
    At dt = 86400 s and K of 1-6 h the response is essentially all in step 0.
    """
    out = {}
    for c in p.channels:
        f = c.decay(p.dt_seconds)
        S = [0.0] * c.n_linres
        frac = []
        for t in range(n_steps):
            q = 1.0 if t == 0 else 0.0
            for i in range(c.n_linres):
                Sn = S[i] * f + c.k_res_seconds * (1.0 - f) * q
                vol = S[i] + q * p.dt_seconds - Sn
                S[i] = Sn
                q = max(0.0, vol / p.dt_seconds)
            frac.append(q)
        out[c.idnr] = {"name": c.name, "n_linres": c.n_linres,
                       "K_hours": c.K_traveltime_hours,
                       "k_res_seconds": c.k_res_seconds,
                       "decay": f, "fraction_out": frac}
    return out


def regime_numbers(p):
    """
    rho and R per reservoir, reported two ways.

    'own'  local inflow only -- directly comparable with the single-reservoir
           slices measured earlier (hjelle_daily, gresse_daily, toppsy_daily,
           kroknesvatn_daily), which received nothing from upstream.
    'full' local inflow plus everything the upstream chain can deliver, bounded
           by the upstream stations' discharge capacity. This is an UPPER bound
           on what actually arrives, not the realised throughflow, which depends
           on the policy. The realised numbers come from diagnose3 on a solution.

        R   = active storage / station capacity over the horizon
        rho = (initial active storage + inflow) / station capacity
    """
    prices, inflow, _ = load_series(p)
    T = len(prices)
    dt = p.dt_seconds

    cap = {s.idnr: s.n_generators * s.max_discharge * dt * T / 1e6
           for s in p.stations}

    own_Mm3 = {r.idnr: sum(inflow[r.idnr]) * dt / 1e6 for r in p.reservoirs}
    init_Mm3 = {r.idnr: r.init_fr * r.active_capacity_Mm3 for r in p.reservoirs}

    # upper bound on delivered upstream water: every upstream reservoir's own
    # available water, capped by the narrowest station on the path between them
    upstream_Mm3 = {}
    for r in p.reservoirs:
        total = 0.0
        for other in p.reservoirs:
            if other.idnr >= r.idnr:
                continue
            cur, bottleneck, reaches = p.tunnel_to[other.idnr], math.inf, False
            while cur is not None:
                if p.node_kind[cur] == "PSTATION":
                    bottleneck = min(bottleneck, cap[cur])
                if cur == r.idnr:
                    reaches = True
                    break
                cur = (p.tunnel_to.get(cur) if p.node_kind[cur] == "RESERVOIR"
                       else p.downlink_to.get(cur, p.channel_to.get(cur)))
            if reaches:
                total += min(own_Mm3[other.idnr] + init_Mm3[other.idnr], bottleneck)
        upstream_Mm3[r.idnr] = total

    out = {"T": T, "dt_seconds": dt, "station_capacity_Mm3": cap,
           "per_reservoir": {}}
    for r in p.reservoirs:
        st = p.tunnel_to[r.idnr]
        c = cap[st]
        out["per_reservoir"][r.idnr] = {
            "name": r.name,
            "station": p.station(st).name,
            "active_capacity_Mm3": r.active_capacity_Mm3,
            "init_active_Mm3": init_Mm3[r.idnr],
            "own_inflow_Mm3": own_Mm3[r.idnr],
            "upstream_bound_Mm3": upstream_Mm3[r.idnr],
            "station_capacity_Mm3": c,
            "chain_equivalent_kWh_m3": p.chain_equivalent[r.idnr],
            "R": r.active_capacity_Mm3 / c,
            "rho_own": (init_Mm3[r.idnr] + own_Mm3[r.idnr]) / c,
            "rho_full_bound": (init_Mm3[r.idnr] + own_Mm3[r.idnr]
                               + upstream_Mm3[r.idnr]) / c,
        }
    return out


# ------------------------------------------------------------------ instances

INSTANCE_DIR = os.path.join(REPO, "analysis", "instances", "utahps_daily")

_CACHE = {}


def get(key="utahps_daily", horizon=None):
    ck = (key, horizon)
    if ck not in _CACHE:
        if key != "utahps_daily":
            raise KeyError(key)
        _CACHE[ck] = build_system(INSTANCE_DIR, name=key, horizon=horizon)
    return _CACHE[ck]


if __name__ == "__main__":
    p = get()
    print(f"{p.name}: {len(p.reservoirs)} reservoirs, {len(p.stations)} stations, "
          f"{len(p.channels)} channels")
    print("\nchain equivalents [kWh/m3]:")
    for r in p.reservoirs:
        print(f"  {r.name:12s} (idnr {r.idnr:2d})  {p.chain_equivalent[r.idnr]:.2f}  "
              f"active {r.active_capacity_Mm3:8.2f} Mm3  init_fr {r.init_fr}")
    print("\nchannel impulse response (fraction out per step):")
    for idnr, d in channel_impulse_response(p).items():
        frac = "  ".join(f"{x:.4f}" for x in d["fraction_out"][:4])
        print(f"  {d['name']:12s} N={d['n_linres']} K={d['K_hours']:.0f}h "
              f"k_res={d['k_res_seconds']:.0f}s  {frac}")
    print("\nregime numbers:")
    rn = regime_numbers(p)
    print(f"  T = {rn['T']}, dt = {rn['dt_seconds']:.0f} s")
    for idnr, d in rn["per_reservoir"].items():
        print(f"  {d['name']:12s} R={d['R']:.3f}  rho_own={d['rho_own']:.3f}  "
              f"rho_full<={d['rho_full_bound']:.3f}  "
              f"({d['station']}, cap {d['station_capacity_Mm3']:.1f} Mm3)")
