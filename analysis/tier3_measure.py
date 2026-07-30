#!/usr/bin/env python3
"""
Tier-3 feasibility measurements for the HERSS-as-oracle exploration.
Read-only w.r.t. the repo except it writes into each dataset's existing output/ dir
(only when the write path is exercised). Does NOT modify src/ or any input file.

Run:  ../.venv/bin/python tier3_measure.py    (from analysis/)
"""
import os, sys, time, statistics, glob
import cppyy

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(REPO, "src")
DATA = os.path.join(REPO, "data")

cppyy.load_library(os.path.join(SRC, "herss.so"))
cppyy.include(os.path.join(SRC, "herss.h"))
G = cppyy.gbl

VERSION = str(G.VERSION); VERSION_DATE = str(G.VERSION_DATE)
G.Logger.instance().init(f"herss_tier3_{VERSION}_{VERSION_DATE}.log")

GLOBALFILE = {
    "utahps_daily": "global_utahps_daily.txt",
    "utahps_daily_new_format": "global_utahps_daily.txt",
    "utahps_hourly": "global_utahps_hourly.txt",
}

def setup(ds):
    """Full setup replicating pyherss.py / C++ main(), returns (herss, data, gc)."""
    d = os.path.join(DATA, ds) + "/"
    gfile = GLOBALFILE.get(ds, "global.txt")
    gc = G.GlobalConfig()
    gc.globalfile = d + gfile
    gc.readGlobalFile()
    gc.inputdir = d
    gc.outputdir = d + "output/"
    gc.SetDirectoriesAndFilenames()
    gc.Diagnose()
    gc.checkNrSteps()
    data = G.Dataset(gc)
    data.readAllData()
    herss = G.Herss(gc)
    herss.prepaireSimulation(data)
    herss.rs.DiagnoseRiversystemConfiguration()
    return herss, data, gc

def hexf(x):
    return float(x).hex()

# ---------- 3.2 Determinism & state reset ----------
def determinism(ds):
    h, data, gc = setup(ds)
    rp = data.restprice
    h.Simulate(); v1 = h.rs.CalcVF(rp)
    h.Simulate(); v2 = h.rs.CalcVF(rp)
    same_repeat = (hexf(v1) == hexf(v2))
    return v1, v2, same_repeat

def state_reset_ABA():
    # mini_utahps_daily: powerstation node 1, gen 0. Perturb an action, restore, compare.
    ds = "mini_utahps_daily"
    h, data, gc = setup(ds)
    rp = data.restprice
    node, gen, t = 1, 0, 5
    a0 = h.GetAction(node, gen, t)
    h.SetAction(node, gen, t, a0)   # A (baseline value re-set explicitly)
    h.Simulate(); vA = h.rs.CalcVF(rp)
    h.SetAction(node, gen, t, 0.123 if a0 != 0.123 else 0.456)  # B
    h.Simulate(); vB = h.rs.CalcVF(rp)
    h.SetAction(node, gen, t, a0)   # back to A
    h.Simulate(); vA2 = h.rs.CalcVF(rp)
    return a0, vA, vB, vA2, (hexf(vA) == hexf(vA2))

# ---------- 3.4 CalcVF vs WriteRiverSystemData ----------
def vf_write_consistency(ds):
    h, data, gc = setup(ds)
    rp = data.restprice
    h.Simulate()
    v_calc = h.rs.CalcVF(rp)
    member_before = float(h.rs.valuefunction_Euro)
    h.rs.WriteRiverSystemData(rp)   # recomputes + overwrites member, writes file
    member_after = float(h.rs.valuefunction_Euro)
    return v_calc, member_before, member_after, (hexf(v_calc) == hexf(member_after))

# ---------- 3.3 Evaluation cost ----------
def eval_cost(ds, n=200):
    h, data, gc = setup(ds)
    rp = data.restprice
    # warmup
    h.Simulate(); h.rs.CalcVF(rp)
    # compute-only path
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        h.Simulate(); h.rs.CalcVF(rp)
        ts.append(time.perf_counter() - t0)
    # compute + full node-file write path
    tw = []
    for _ in range(max(20, n // 5)):
        t0 = time.perf_counter()
        h.Simulate(); h.rs.CalcVF(rp); h.WriteNodeOutput(); h.rs.WriteRiverSystemData(rp)
        tw.append(time.perf_counter() - t0)
    return {
        "n": n,
        "mean_ms": statistics.mean(ts) * 1e3,
        "std_ms": statistics.pstdev(ts) * 1e3,
        "evps": 1.0 / statistics.mean(ts),
        "write_mean_ms": statistics.mean(tw) * 1e3,
        "write_evps": 1.0 / statistics.mean(tw),
    }

if __name__ == "__main__":
    print(f"# HERSS Tier-3 measurements  (VERSION {VERSION} / {VERSION_DATE})")
    print(f"# upstream commit 029a2d5 ; python {sys.version.split()[0]} ; cppyy {cppyy.__version__}\n")

    det_sets = ["mini_utahps_daily", "mini_utahps_hourly", "res_casc_B", "utahps_daily", "utahps_hourly"]
    print("## 3.2 Determinism (Simulate twice, identical actions)")
    for ds in det_sets:
        v1, v2, ok = determinism(ds)
        print(f"  {ds:28s} v1={v1!r} v2={v2!r} bit_identical={ok}")

    print("\n## 3.2 State reset A->B->A (mini_utahps_daily, node1/gen0/t5)")
    a0, vA, vB, vA2, ok = state_reset_ABA()
    print(f"  a0={a0}  V(A)={vA!r}  V(B)={vB!r}  V(A again)={vA2!r}  A_reproduced={ok}")

    print("\n## 3.4 CalcVF vs WriteRiverSystemData member (same restprice)")
    for ds in ["mini_utahps_daily", "res_casc_A", "utahps_daily"]:
        vc, mb, ma, ok = vf_write_consistency(ds)
        print(f"  {ds:20s} CalcVF={vc!r} member_after_write={ma!r} identical={ok}")

    print("\n## 3.3 Evaluation cost (in-process Simulate+CalcVF)")
    for ds, n in [("res_casc_B", 500), ("mini_utahps_daily", 500),
                  ("mini_utahps_hourly", 500), ("utahps_hourly", 100)]:
        r = eval_cost(ds, n)
        print(f"  {ds:20s} n={r['n']:4d} compute: {r['mean_ms']:.3f}+/-{r['std_ms']:.3f} ms "
              f"({r['evps']:.0f} ev/s) | +writefiles: {r['write_mean_ms']:.3f} ms "
              f"({r['write_evps']:.0f} ev/s)")
    print("\nDONE")
