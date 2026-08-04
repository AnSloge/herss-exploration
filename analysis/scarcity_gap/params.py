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

# analysis/instances/toppsy_daily/topology.txt  (verbatim from utahps_daily)
# Added 2026-08-03. Cascade node: in the full uTAHPS it also receives GRESSE's
# and HJELLE's outflow, so the slice's rho is a LOWER bound on the real one.
TOPPSY_DAILY = InstanceParams(
    name="toppsy_daily",
    dataset_dir=os.path.join(REPO, "analysis", "instances", "toppsy_daily") + "/",
    pricefile="pricefile.txt",
    inflowfile="inflowseries.txt",
    globalfile="global.txt",
    dt_seconds=86400,
    reservoir_init_fr=0.9,
    HRW=650.0, LRW=620.0, RES_PENALTY=300.0,
    reservoir_curve_masl=_a(610, 619, 620, 630, 640, 650, 660, 670, 680, 690),
    reservoir_curve_Mm3=_a(0.0, 265.00, 268.53, 308.33, 352.87, 395.17,
                           467.73, 538.94, 650.00, 1000.0),
    overflow_curve_masl=_a(650.0, 680.0, 690.0),
    overflow_curve_m3s=_a(0.0, 100.0, 500.0),
    generator_max_discharge=5.9,
    static_generator_efficiency=0.96,
    headlosscoef=0.2,
    powstat_masl=581.0,
    powstat_startstop=2.0,
    local_energy_equivalent=0.11,
    turbine_curve_q=_a(0.00, 1.48, 2.54, 3.36, 4.13, 4.72, 5.13, 5.43, 5.61, 5.90),
    turbine_curve_pct=_a(0.0, 50.0, 80.0, 90.0, 93.0, 93.0, 93.0, 92.0, 91.0, 90.0),
)

# analysis/instances/kroknesvatn_daily/topology.txt  (verbatim from utahps_daily)
# The deepest reservoir in the system: 100 m of regulated range against HJELLE's
# 9 m, and a four-point overflow curve.
KROKNESVATN_DAILY = InstanceParams(
    name="kroknesvatn_daily",
    dataset_dir=os.path.join(REPO, "analysis", "instances", "kroknesvatn_daily") + "/",
    pricefile="pricefile.txt",
    inflowfile="inflowseries.txt",
    globalfile="global.txt",
    dt_seconds=86400,
    reservoir_init_fr=0.66,
    HRW=433.0, LRW=333.0, RES_PENALTY=300.0,
    reservoir_curve_masl=_a(300, 333, 343, 353, 363, 373, 383, 393, 403, 413,
                            423, 433, 435, 440),
    reservoir_curve_Mm3=_a(0.0, 19.30, 31.08, 44.75, 60.14, 77.21, 96.01,
                           116.70, 139.28, 163.78, 190.23, 218.57, 300.0, 1000.0),
    overflow_curve_masl=_a(433.0, 434.0, 435.0, 440.0),
    overflow_curve_m3s=_a(0.0, 10.0, 100.0, 2000.0),
    generator_max_discharge=9.80,
    static_generator_efficiency=0.96,
    headlosscoef=0.145,
    powstat_masl=218.0,
    powstat_startstop=2.0,
    local_energy_equivalent=0.11,
    turbine_curve_q=_a(0.00, 2.45, 4.21, 5.59, 6.86, 7.84, 8.53, 9.02, 9.31, 9.80),
    turbine_curve_pct=_a(0.0, 50.0, 80.0, 90.0, 93.0, 93.0, 93.0, 92.0, 91.0, 90.0),
)

# ----------------------------------------------------- synthetic rho/R grid
#
# SYNTHETIC INSTANCES. These are NOT slices of uTAHPS and must never be mixed
# into conclusions about it. They exist for one purpose: rho and R move together
# in every real instance measured so far (HJELLE 0.78/0.07, GRESSE 0.56/0.32,
# TOPPSY 1.02/0.68, KROKNESVATN 0.95/0.64), so the mechanism behind the gap is
# not identified. This grid varies one at a time.
#
# R is scaled by scaling the whole reservoir curve, V'(masl) = s * V(masl), with
# LRW and HRW left at 748/757 masl. Head as a function of LEVEL is therefore
# unchanged; what changes is the volume per metre. Two consequences must be
# stated whenever these results are used:
#
#   - The construction is not physically realisable: a real reservoir holding
#     four times the volume would not have the same 9 m regulated range. So this
#     isolates R AT CONSTANT HEAD SPAN, which is a narrower claim than
#     "isolates R".
#   - Scaling the curve also scales the initial active storage at a fixed
#     init_fr, which would drag rho along with R -- exactly the confound being
#     removed. The inflow series is therefore rescaled to hold rho at its target:
#
#         rho = (init_fr * s * active_0 + k * inflow_0) / turbine_capacity
#     =>  k   = (rho_target * turbine_capacity - init_fr * s * active_0) / inflow_0
#
#     so each cell hits its rho exactly, independently of s.

_HJELLE_ACTIVE_0 = 9.0          # HRW - LRW filling on the unscaled curve [Mm3]
_HJELLE_INIT_FR = 0.7
_HJELLE_INFLOW_0_Mm3 = None     # filled lazily from the instance's own file
_HJELLE_CAPACITY_Mm3 = 4.0 * 86400 * 365 / 1e6


def hjelle_inflow_total_Mm3():
    global _HJELLE_INFLOW_0_Mm3
    if _HJELLE_INFLOW_0_Mm3 is None:
        _, inflows, _ = load_series(HJELLE_DAILY)
        _HJELLE_INFLOW_0_Mm3 = sum(inflows) * 86400 / 1e6
    return _HJELLE_INFLOW_0_Mm3


def synthetic_inflow_scale(rho_target, R_scale):
    """k such that the resulting instance has exactly rho = rho_target."""
    init_active = _HJELLE_INIT_FR * R_scale * _HJELLE_ACTIVE_0
    return (rho_target * _HJELLE_CAPACITY_Mm3 - init_active) / hjelle_inflow_total_Mm3()


def synthetic_slug(rho_target, R_scale):
    return f"syn_rho{rho_target:g}_R{R_scale:g}".replace(".", "p")


def make_synthetic_hjelle(rho_target, R_scale):
    """HJELLE with the reservoir curve scaled by R_scale and inflow rescaled."""
    slug = synthetic_slug(rho_target, R_scale)
    return InstanceParams(
        name=slug,
        dataset_dir=os.path.join(REPO, "analysis", "instances", slug) + "/",
        pricefile="pricefile.txt", inflowfile="inflowseries.txt",
        globalfile="global.txt",
        dt_seconds=86400,
        reservoir_init_fr=_HJELLE_INIT_FR,
        HRW=757.0, LRW=748.0, RES_PENALTY=300.0,
        reservoir_curve_masl=HJELLE_DAILY.reservoir_curve_masl.copy(),
        reservoir_curve_Mm3=HJELLE_DAILY.reservoir_curve_Mm3 * R_scale,
        overflow_curve_masl=HJELLE_DAILY.overflow_curve_masl.copy(),
        overflow_curve_m3s=HJELLE_DAILY.overflow_curve_m3s.copy(),
        generator_max_discharge=4.0,
        static_generator_efficiency=0.96,
        headlosscoef=0.3,
        powstat_masl=690.0,
        powstat_startstop=2.0,
        local_energy_equivalent=0.11,
        turbine_curve_q=HJELLE_DAILY.turbine_curve_q.copy(),
        turbine_curve_pct=HJELLE_DAILY.turbine_curve_pct.copy(),
    )


SYNTHETIC_RHO = (0.5, 0.75, 1.0, 1.25)
SYNTHETIC_R_SCALE = (0.5, 1.0, 2.0, 4.0)

# Priority order for a limited night: the R_scale = 1 row and the rho = 1 column
# first (they cross at one cell), then the diagonal.
SYNTHETIC_PRIORITY = (
    [(r, 1.0) for r in SYNTHETIC_RHO]
    + [(1.0, s) for s in SYNTHETIC_R_SCALE if s != 1.0]
    + [(r, s) for r, s in zip(SYNTHETIC_RHO, SYNTHETIC_R_SCALE)
       if s != 1.0 and r != 1.0]
)

INSTANCES = {
    "mini": MINI_UTAHPS_DAILY,
    "hjelle": HJELLE_DAILY,
    "gresse": GRESSE_DAILY,
    "hjelle_e163": HJELLE_DAILY_E163,
    "toppsy": TOPPSY_DAILY,
    "kroknesvatn": KROKNESVATN_DAILY,
}

for _r in SYNTHETIC_RHO:
    for _s in SYNTHETIC_R_SCALE:
        INSTANCES[synthetic_slug(_r, _s)] = make_synthetic_hjelle(_r, _s)


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
