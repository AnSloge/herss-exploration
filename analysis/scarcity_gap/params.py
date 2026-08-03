#!/usr/bin/env python
"""
Instance parameters for the single-reservoir HERSS replica.

Every field is read straight out of a topology/start-state/price file; nothing
is derived or tuned here. Three instances are defined:

  mini_utahps_daily  -- the previous gating instance (abundance regime,
                        rho=1.82), kept only so test_regression.py can prove
                        the parameterisation did not change any formula.
  hjelle_daily       -- scarcity-regime slice, rho=0.78, R=0.07
  gresse_daily       -- scarcity-regime slice, rho=0.56, R=0.32
"""

import os
from dataclasses import dataclass, field, replace

import numpy as np

from arraycurve import ArrayCurve

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GRAVITY = 9.80665                  # herss.h
AGGRESSIVE_ACTIONS_COST = 1000.0   # herss.h HERSS_AGGRESSIVE_ACTIONS_COST


@dataclass(frozen=True)
class InstanceParams:
    name: str
    dataset_dir: str
    pricefile: str
    inflowfile: str
    globalfile: str
    dt_seconds: float
    reservoir_init_fr: float

    # reservoir node
    HRW: float
    LRW: float
    RES_PENALTY: float
    reservoir_curve_masl: np.ndarray
    reservoir_curve_Mm3: np.ndarray
    overflow_curve_masl: np.ndarray
    overflow_curve_m3s: np.ndarray

    # powerstation node
    generator_max_discharge: float
    static_generator_efficiency: float
    headlosscoef: float
    powstat_masl: float
    powstat_startstop: float
    local_energy_equivalent: float
    turbine_curve_q: np.ndarray
    turbine_curve_pct: np.ndarray

    # derived -- all four curves are HERSS ArrayCurve objects, not np.interp.
    # reservoir.cpp:100-144 initArrayCurves builds ac_res_masl_2_Mm3,
    # ac_res_Mm3_2_masl and ac_ovefl_masl_2_m3s; powerstation.cpp builds
    # generators[g].eff_curve the same way.
    curve_masl_2_Mm3: ArrayCurve = field(init=False)
    curve_Mm3_2_masl: ArrayCurve = field(init=False)
    curve_overflow: ArrayCurve = field(init=False)
    curve_turbine: ArrayCurve = field(init=False)
    filling_at_lrw_Mm3: float = field(init=False)
    filling_at_hrw_Mm3: float = field(init=False)
    active_capacity_Mm3: float = field(init=False)

    def __post_init__(self):
        s = lambda k, v: object.__setattr__(self, k, v)
        s("curve_masl_2_Mm3", ArrayCurve(self.reservoir_curve_masl, self.reservoir_curve_Mm3))
        s("curve_Mm3_2_masl", ArrayCurve(self.reservoir_curve_Mm3, self.reservoir_curve_masl))
        s("curve_overflow", ArrayCurve(self.overflow_curve_masl, self.overflow_curve_m3s))
        s("curve_turbine", ArrayCurve(self.turbine_curve_q, self.turbine_curve_pct))
        # reservoir.cpp:310-311 -- these go through the ArrayCurve too
        lrw = self.curve_masl_2_Mm3.x2y(self.LRW)
        hrw = self.curve_masl_2_Mm3.x2y(self.HRW)
        s("filling_at_lrw_Mm3", lrw)
        s("filling_at_hrw_Mm3", hrw)
        s("active_capacity_Mm3", hrw - lrw)

    def m3s_to_Mm3(self, q_m3s):
        return q_m3s * self.dt_seconds / 1_000_000.0

    def Mm3_to_m3s(self, q_Mm3):
        return q_Mm3 * 1_000_000.0 / self.dt_seconds

    def with_energy_equivalent(self, e):
        """Sensitivity variant: same physics, different terminal water value."""
        return replace(self, name=f"{self.name}_e{e}", local_energy_equivalent=e)


def _a(*v):
    return np.array(v, dtype=float)


# ---------------------------------------------------------------- instances

MINI_UTAHPS_DAILY = InstanceParams(
    name="mini_utahps_daily",
    dataset_dir=os.path.join(REPO, "data", "mini_utahps_daily") + "/",
    pricefile="pricefile.txt",
    inflowfile="inflowseries.txt",
    globalfile="global.txt",
    dt_seconds=86400,
    reservoir_init_fr=0.67,
    HRW=757.0, LRW=748.0, RES_PENALTY=300.0,
    reservoir_curve_masl=_a(747, 748, 749, 750, 757, 758, 760),
    reservoir_curve_Mm3=_a(0.0, 1.0, 2.37, 3.24, 10.0, 15.0, 500.0),
    overflow_curve_masl=_a(757, 758, 760),
    overflow_curve_m3s=_a(0.0, 10.0, 200.0),
    generator_max_discharge=4.0,
    static_generator_efficiency=0.96,
    headlosscoef=0.3,
    powstat_masl=690.0,
    powstat_startstop=2.0,
    local_energy_equivalent=0.11,
    turbine_curve_q=_a(0.00, 1.00, 1.72, 2.27, 2.79, 3.19, 3.47, 3.67, 3.79, 4.00),
    turbine_curve_pct=_a(0, 50, 80, 90, 93, 93, 93, 92, 91, 88),
)

# analysis/instances/hjelle_daily/topology.txt  (verbatim from utahps_daily)
HJELLE_DAILY = InstanceParams(
    name="hjelle_daily",
    dataset_dir=os.path.join(REPO, "analysis", "instances", "hjelle_daily") + "/",
    pricefile="pricefile.txt",
    inflowfile="inflowseries.txt",
    globalfile="global.txt",
    dt_seconds=86400,
    reservoir_init_fr=0.7,
    HRW=757.0, LRW=748.0, RES_PENALTY=300.0,
    reservoir_curve_masl=_a(747, 748, 749, 750, 757, 758, 760),
    reservoir_curve_Mm3=_a(0.0, 1.0, 2.37, 3.24, 10.0, 15.0, 100.0),
    overflow_curve_masl=_a(757, 758, 760),
    overflow_curve_m3s=_a(0.0, 10.0, 200.0),
    generator_max_discharge=4.0,
    static_generator_efficiency=0.96,
    headlosscoef=0.3,
    powstat_masl=690.0,
    powstat_startstop=2.0,
    local_energy_equivalent=0.11,
    turbine_curve_q=_a(0.00, 1.00, 1.72, 2.27, 2.79, 3.19, 3.47, 3.67, 3.79, 4.00),
    turbine_curve_pct=_a(0, 50, 80, 90, 93, 93, 93, 92, 91, 88),
)

# analysis/instances/gresse_daily/topology.txt  (verbatim from utahps_daily)
GRESSE_DAILY = InstanceParams(
    name="gresse_daily",
    dataset_dir=os.path.join(REPO, "analysis", "instances", "gresse_daily") + "/",
    pricefile="pricefile.txt",
    inflowfile="inflowseries.txt",
    globalfile="global.txt",
    dt_seconds=86400,
    reservoir_init_fr=0.8,
    HRW=749.0, LRW=740.0, RES_PENALTY=300.0,
    reservoir_curve_masl=_a(725, 730, 735, 740, 741, 743, 745, 748, 749, 750, 751, 752, 755),
    reservoir_curve_Mm3=_a(20.70, 46.68, 75.31, 106.60, 113.09, 126.28, 139.81,
                           160.86, 168.04, 175.34, 180.34, 200.34, 500.0),
    overflow_curve_masl=_a(749.0, 751.0, 755.0),
    overflow_curve_m3s=_a(0.0, 10.0, 200.0),
    generator_max_discharge=6.0,
    static_generator_efficiency=0.96,
    headlosscoef=0.145,
    powstat_masl=581.0,
    powstat_startstop=2.0,
    local_energy_equivalent=0.39,
    turbine_curve_q=_a(0.00, 0.60, 0.72, 1.04, 1.28, 1.52, 2.04, 2.40, 5.76, 6.00),
    turbine_curve_pct=_a(0, 50, 60, 70, 80, 85, 90, 91, 90, 89),
)

# Sensitivity variant of HJELLE. SVOLETJONN's LOCAL_ENERGY_EQUIVALENT of 0.11
# kWh/m3 is only ~68% of the station's own full-head equivalent (~0.163), so
# terminal water is systematically underpriced there while GRESSE's 0.39 is
# ~96% of its own (~0.409). That confounds a HJELLE-vs-GRESSE comparison, since
# the two instances then differ in water value as well as in storage depth.
#
# This is a real instance directory with 0.163 written into topology.txt, NOT a
# Python-side override: overriding only the replica would leave the real
# simulator optimising a different objective, and every cross-check against
# HERSS would silently compare two different value functions.
HJELLE_DAILY_E163 = InstanceParams(
    **{**{k: v for k, v in HJELLE_DAILY.__dict__.items()
          if k in InstanceParams.__dataclass_fields__
          and InstanceParams.__dataclass_fields__[k].init},
       "name": "hjelle_daily_e163",
       "dataset_dir": os.path.join(REPO, "analysis", "instances", "hjelle_daily_e163") + "/",
       "local_energy_equivalent": 0.163}
)

INSTANCES = {
    "mini": MINI_UTAHPS_DAILY,
    "hjelle": HJELLE_DAILY,
    "gresse": GRESSE_DAILY,
    "hjelle_e163": HJELLE_DAILY_E163,
}


def load_series(p):
    """Return (prices, inflows, restprice) read from the instance's own files."""
    with open(p.dataset_dir + p.pricefile) as f:
        lines = [l.strip() for l in f if l.strip()]
    restprice = float(lines[0].split()[1])
    prices = [float(l.split()[1]) for l in lines[2:]]

    with open(p.dataset_dir + p.inflowfile) as f:
        lines = [l.strip() for l in f if l.strip()]
    inflows = [float(l.split()[1]) for l in lines[1:]]

    assert len(prices) == len(inflows), (len(prices), len(inflows))
    return prices, inflows, restprice


def regime_numbers(p):
    """rho and R, the two screening ratios (report section 'Verified premises')."""
    _, inflows, _ = load_series(p)
    T = len(inflows)
    inflow_Mm3 = sum(inflows) * p.dt_seconds / 1e6
    init_active_Mm3 = p.reservoir_init_fr * p.active_capacity_Mm3
    capacity_Mm3 = p.generator_max_discharge * p.dt_seconds * T / 1e6
    return {
        "T": T,
        "active_Mm3": p.active_capacity_Mm3,
        "init_active_Mm3": init_active_Mm3,
        "inflow_Mm3": inflow_Mm3,
        "turbine_capacity_Mm3": capacity_Mm3,
        "R": p.active_capacity_Mm3 / capacity_Mm3,
        "rho": (init_active_Mm3 + inflow_Mm3) / capacity_Mm3,
    }
