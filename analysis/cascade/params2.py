#!/usr/bin/env python
r"""
Instance parameters for the two-reservoir res_casc_A replica.

Every field is read straight out of analysis/instances/res_casc_A/topology.txt
(itself a byte-for-byte copy of data/res_casc_A/topology.txt); nothing is
derived or tuned here.

Topology, for reference:

    RES_A (0) --hatch(qmax 6.0, masl 848)--> RES_B (1) --tunnel--> PSTAT_B (4)
      |                                        |                      |
      overflow -> CHAN2 (2) ------\            overflow -> CHAN3 (3) --+
                                   \                                   |
                                    +------> CHANNEL5 (5) -> outlet <--+

Two consequences of that wiring, both verified in source AND in the shipped
output file, drive everything downstream:

  1. RES_A's stored water is worth ZERO in the objective. CalcVF's terminal term
     runs over PSTATION nodes and their upstream_remaining_active_Mm3, which
     herss.cpp:691 accumulates along ptr_downstream_node only. For a reservoir
     with no tunnel, reservoir.cpp:1065-1073 sets that pointer to the OVERFLOW
     target -- the hatch does not count. So RES_A's chain is 0 -> 2 -> 5, which
     never reaches PSTAT_B. Confirmed in
     data/res_casc_A/output/riversystem_ResCascA_output.txt:
         tot_active_remaining_Mm3 = 18.000   (9.0 from each reservoir)
         tot_remaining_MWh        =  990.000 = 0.11 * 9.0 * 1000  -> RES_B only
     Water in RES_A only has value if the hatch moves it to RES_B and PSTAT_B
     turbines it inside the horizon, and the hatch is rate limited to
     6.0 m3/s = 0.5184 Mm3/day.

  2. The channels cannot affect V. They earn no income, their only cost is the
     QMIN penalty (QMIN -9999 = off in all three), and all three sit downstream
     of PSTAT_B so none enters its upstream_remaining_active_Mm3. Verified
     empirically in build_res_casc_A.py: shipped placeholder storages vs
     steady-state storages give dVF = 0.0000 exactly. The replica therefore does
     not model them.
"""

import os
import sys
from dataclasses import dataclass, field, replace

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "analysis", "scarcity_gap"))

from arraycurve import ArrayCurve  # noqa: E402  reused unchanged

GRAVITY = 9.80665                  # herss.h
AGGRESSIVE_ACTIONS_COST = 1000.0   # herss.h HERSS_AGGRESSIVE_ACTIONS_COST


def _a(*v):
    return np.array(v, dtype=float)


@dataclass(frozen=True)
class ReservoirParams:
    name: str
    idnr: int
    HRW: float
    LRW: float
    RES_PENALTY: float
    curve_masl: np.ndarray
    curve_Mm3: np.ndarray
    overflow_masl: np.ndarray
    overflow_m3s: np.ndarray
    init_fr: float
    # hatch, if any
    hatch_qmin: float = -1.0
    hatch_qmax: float = -1.0
    hatch_masl: float = -1.0

    curve_masl_2_Mm3: ArrayCurve = field(init=False)
    curve_Mm3_2_masl: ArrayCurve = field(init=False)
    curve_overflow: ArrayCurve = field(init=False)
    filling_at_lrw_Mm3: float = field(init=False)
    filling_at_hrw_Mm3: float = field(init=False)
    filling_at_hatch_Mm3: float = field(init=False)
    active_capacity_Mm3: float = field(init=False)

    def __post_init__(self):
        s = lambda k, v: object.__setattr__(self, k, v)
        s("curve_masl_2_Mm3", ArrayCurve(self.curve_masl, self.curve_Mm3))
        s("curve_Mm3_2_masl", ArrayCurve(self.curve_Mm3, self.curve_masl))
        s("curve_overflow", ArrayCurve(self.overflow_masl, self.overflow_m3s))
        # reservoir.cpp:310-311, 327 -- all three go through the ArrayCurve
        lrw = self.curve_masl_2_Mm3.x2y(self.LRW)
        hrw = self.curve_masl_2_Mm3.x2y(self.HRW)
        s("filling_at_lrw_Mm3", lrw)
        s("filling_at_hrw_Mm3", hrw)
        s("active_capacity_Mm3", hrw - lrw)
        s("filling_at_hatch_Mm3",
          self.curve_masl_2_Mm3.x2y(self.hatch_masl) if self.has_hatch else -1.0)

    @property
    def has_hatch(self):
        return self.hatch_qmax >= 0.0

    def init_Mm3(self, init_fr=None):
        # reservoir.cpp:315
        fr = self.init_fr if init_fr is None else init_fr
        return self.filling_at_lrw_Mm3 + fr * self.active_capacity_Mm3


@dataclass(frozen=True)
class StationParams:
    name: str
    idnr: int
    n_generators: int
    max_discharge: float          # per generator
    static_gen_efficiency: float
    headlosscoef: float
    shared_penstock: bool
    powstat_masl: float
    powstat_startstop: float
    local_energy_equivalent: float
    turbine_q: np.ndarray
    turbine_pct: np.ndarray

    curve_turbine: ArrayCurve = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "curve_turbine",
                           ArrayCurve(self.turbine_q, self.turbine_pct))


@dataclass(frozen=True)
class CascadeParams:
    name: str
    dataset_dir: str
    globalfile: str
    pricefile: str
    inflowfile: str
    dt_seconds: float
    upper: ReservoirParams        # RES_A, hatch to `lower`
    lower: ReservoirParams        # RES_B, tunnel to `station`
    station: StationParams
    # If True the terminal term also values the upper reservoir. Synthetic
    # variant only (task A4); the verbatim instance is False, matching CalcVF.
    value_upper_storage: bool = False

    def m3s_to_Mm3(self, q):
        return q * self.dt_seconds / 1_000_000.0

    def Mm3_to_m3s(self, v):
        return v * 1_000_000.0 / self.dt_seconds

    def with_upper_valued(self):
        return replace(self, name=f"{self.name}_vkorr", value_upper_storage=True)


# ------------------------------------------------------------------ res_casc_A

_RES_CURVE_MASL_A = _a(847, 848, 849, 850, 857, 858, 860)
_RES_CURVE_MM3 = _a(0.0, 1.0, 2.37, 3.24, 10.0, 15.0, 500.0)
_RES_CURVE_MASL_B = _a(747, 748, 749, 750, 757, 758, 760)

RES_A = ReservoirParams(
    name="RES_A", idnr=0,
    HRW=857.0, LRW=848.0, RES_PENALTY=300.0,
    curve_masl=_RES_CURVE_MASL_A, curve_Mm3=_RES_CURVE_MM3,
    overflow_masl=_a(857, 858, 860), overflow_m3s=_a(0.0, 10.0, 200.0),
    init_fr=0.86,
    hatch_qmin=0.0, hatch_qmax=6.0, hatch_masl=848.0,
)

RES_B = ReservoirParams(
    name="RES_B", idnr=1,
    HRW=757.0, LRW=748.0, RES_PENALTY=300.0,
    curve_masl=_RES_CURVE_MASL_B, curve_Mm3=_RES_CURVE_MM3,
    overflow_masl=_a(757, 758, 760), overflow_m3s=_a(0.0, 10.0, 200.0),
    init_fr=0.79,
)

PSTAT_B = StationParams(
    name="PSTAT_B", idnr=4,
    n_generators=2, max_discharge=4.0,
    static_gen_efficiency=0.96, headlosscoef=0.3, shared_penstock=True,
    powstat_masl=690.0, powstat_startstop=2.0, local_energy_equivalent=0.11,
    turbine_q=_a(0.00, 1.00, 1.72, 2.27, 2.79, 3.19, 3.47, 3.67, 3.79, 4.00),
    turbine_pct=_a(0, 50, 80, 90, 93, 93, 93, 92, 91, 88),
)

RES_CASC_A = CascadeParams(
    name="res_casc_A",
    dataset_dir=os.path.join(REPO, "analysis", "instances", "res_casc_A") + "/",
    globalfile="global.txt", pricefile="pricefile.txt", inflowfile="inflowseries.txt",
    dt_seconds=86400,
    upper=RES_A, lower=RES_B, station=PSTAT_B,
)

RES_CASC_A_VKORR = RES_CASC_A.with_upper_valued()

INSTANCES = {
    "res_casc_A": RES_CASC_A,
    "res_casc_A_vkorr": RES_CASC_A_VKORR,
}


def load_series(p):
    """(prices, inflow_upper, inflow_lower, restprice) from the instance's files."""
    with open(p.dataset_dir + p.pricefile) as f:
        lines = [l.strip() for l in f if l.strip()]
    restprice = float(lines[0].split()[1])
    prices = [float(l.split()[1]) for l in lines[2:]]

    with open(p.dataset_dir + p.inflowfile) as f:
        lines = [l.split() for l in f if l.strip()]
    header = lines[0]
    col_up = header.index(str(p.upper.idnr))
    col_lo = header.index(str(p.lower.idnr))
    inflow_up = [float(r[col_up]) for r in lines[1:]]
    inflow_lo = [float(r[col_lo]) for r in lines[1:]]

    assert len(prices) == len(inflow_up) == len(inflow_lo)
    return prices, inflow_up, inflow_lo, restprice


def regime_numbers(p):
    """
    Screening ratios. The single-reservoir rho/R are reported per reservoir, plus
    the transfer-limited ratios that the single-reservoir versions cannot see.
    """
    prices, q_up, q_lo, _ = load_series(p)
    T = len(prices)
    dt = p.dt_seconds

    infl_up = sum(q_up) * dt / 1e6
    infl_lo = sum(q_lo) * dt / 1e6
    init_up = p.upper.init_fr * p.upper.active_capacity_Mm3
    init_lo = p.lower.init_fr * p.lower.active_capacity_Mm3

    station_cap = p.station.n_generators * p.station.max_discharge * dt * T / 1e6
    hatch_cap = p.upper.hatch_qmax * dt * T / 1e6

    return {
        "T": T,
        "dt_seconds": dt,
        "active_Mm3_upper": p.upper.active_capacity_Mm3,
        "active_Mm3_lower": p.lower.active_capacity_Mm3,
        "init_active_Mm3_upper": init_up,
        "init_active_Mm3_lower": init_lo,
        "inflow_Mm3_upper": infl_up,
        "inflow_Mm3_lower": infl_lo,
        "station_capacity_Mm3": station_cap,
        "hatch_capacity_Mm3": hatch_cap,
        # system-level, comparable with the single-reservoir instances
        "R_system": (p.upper.active_capacity_Mm3 + p.lower.active_capacity_Mm3) / station_cap,
        "rho_system": (init_up + init_lo + infl_up + infl_lo) / station_cap,
        # transfer-limited: can the hatch even pass what the upper reservoir holds?
        "available_upper_Mm3": init_up + infl_up,
        "hatch_binding_ratio": (init_up + infl_up) / hatch_cap,
        # what the lower reservoir can receive at most, vs what it can turbine
        "rho_lower_max": (init_lo + infl_lo + min(hatch_cap, init_up + infl_up)) / station_cap,
    }
