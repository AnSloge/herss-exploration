#!/usr/bin/env python
"""
Thin wrapper around the real HERSS simulator (via cppyy) for mini_utahps_daily.

Used only to VALIDATE the Python physics replica (replica.py) and to get the
ground-truth VF for the final DP-optimal and threshold-policy action sequences.
This is read-only use of the simulator: no changes to src/.

Repository state this was verified against: HERSS VERSION 3.1.03 / VERSION_DATE
20260611, upstream commit 029a2d5.

cppyy pitfalls hit and worked around here (neither is a HERSS behaviour):
  1. `Logger::instance().init(...)` must be called once before any Simulate(),
     mirroring py_src/pyherss.py, or LOG_WARN paths crash.
  2. Raw `double*` members surface as a `cppyy.LowLevelView` with unknown
     extent; indexing past position 0 needs an explicit `.reshape((T,))` first.
  3. A SECOND `.reshape((T,))`-based raw-pointer read, anywhere in the same
     Python process -- even for the identical field from a brand new, freshly
     built Herss instance -- reliably segfaults. Only the first such read in
     a process is safe. This looks like corruption in some cppyy-global
     LowLevelView/type-info bookkeeping, not anything tied to a specific
     field, node, or cached reference. Worked around by running each single
     field extraction (`evaluate_field`) in its own subprocess
     (`evaluate_field_subprocess`); only `evaluate_vf` (plain scalar return,
     no array reads) is safe to call repeatedly in-process, which is what the
     DP/threshold code paths use.
"""

import json
import os
import subprocess
import sys
import tempfile

import cppyy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(REPO_ROOT, "data", "mini_utahps_daily") + "/"
SO_PATH = os.path.join(REPO_ROOT, "src", "herss.so")
H_PATH = os.path.join(REPO_ROOT, "src", "herss.h")

_loaded = False
_logger_ready = False


def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    cppyy.load_library(SO_PATH)
    cppyy.include(H_PATH)
    _loaded = True


def _ensure_logger():
    global _logger_ready
    _ensure_loaded()
    if _logger_ready:
        return
    version = cppyy.gbl.VERSION
    version_date = cppyy.gbl.VERSION_DATE
    logfilename = f"herss_{version}_{version_date}.log"
    if not cppyy.gbl.Logger.instance().init(logfilename):
        raise RuntimeError(f"Could not open log file: {logfilename}")
    _logger_ready = True


def version_info():
    _ensure_loaded()
    return str(cppyy.gbl.VERSION), str(cppyy.gbl.VERSION_DATE)


def build_herss():
    """Fresh GlobalConfig/Dataset/Herss triple, ready to Simulate()."""
    _ensure_logger()

    gc = cppyy.gbl.GlobalConfig()
    gc.globalfile = DATASET_DIR + "global.txt"
    gc.readGlobalFile()
    gc.inputdir = DATASET_DIR
    gc.outputdir = DATASET_DIR + "output/"
    gc.SetDirectoriesAndFilenames()
    gc.Diagnose()
    gc.checkNrSteps()

    data = cppyy.gbl.Dataset(gc)
    data.readAllData()

    herss = cppyy.gbl.Herss(gc)
    herss.prepaireSimulation(data)
    herss.rs.DiagnoseRiversystemConfiguration()

    return gc, data, herss


def _run(actions, restprice=None, init_fr=None):
    gc, data, herss = build_herss()
    T = herss.stps
    if len(actions) != T:
        raise ValueError(f"expected {T} actions, got {len(actions)}")
    for t, a in enumerate(actions):
        herss.SetAction(1, 0, t, float(a))
    if init_fr is not None:
        herss.SetReservoir_Init_fr(0, float(init_fr))
    herss.Simulate()
    rp = restprice if restprice is not None else data.restprice
    vf = herss.rs.CalcVF(rp)
    return gc, data, herss, T, rp, vf


def evaluate_vf(actions, restprice=None, init_fr=None):
    """Cheap, safe: scalar VF only (no raw-array reads)."""
    _, _, _, _, _, vf = _run(actions, restprice, init_fr)
    return vf


def evaluate_field(actions, node_idx, field, restprice=None, init_fr=None):
    """
    Fresh HERSS run, single `double*` field read back as a length-T list.
    node_idx: 0 = HJELLE (reservoir), 1 = SVOLETJONN (powerstation).
    See module docstring point 3 for why this is one field per call.
    """
    _, _, herss, T, _, _ = _run(actions, restprice, init_fr)
    buf = getattr(herss.rs.nodes[node_idx].S, field)
    buf.reshape((T,))
    return [buf[t] for t in range(T)]


_FIELD_SPECS = {
    "res_masl": (0, "res_masl"),
    "res_fr": (0, "res_fr"),
    "res_Mm3": (0, "res_Mm3"),
    "overflow_m3s": (0, "overflow_m3s"),
    "res_cost_lrw": (0, "cost"),
    "power_MWh": (1, "Power"),
    "income": (1, "income"),
    "cost": (1, "cost"),
    "profit": (1, "profit"),
    "aggressive_cost": (1, "cost_aggressive_actions"),
    "startstop_cost": (1, "startStopCost"),
}


def evaluate_field_subprocess(actions, node_idx, field, restprice=None, init_fr=None):
    """Run a single field extraction in an isolated subprocess (see point 3)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"actions": actions, "restprice": restprice, "init_fr": init_fr}, f)
        actions_file = f.name
    try:
        out = subprocess.run(
            [sys.executable, os.path.abspath(__file__),
             "--field", field, "--node", str(node_idx), "--actions-file", actions_file],
            capture_output=True, text=True, check=True, cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    finally:
        os.unlink(actions_file)
    return json.loads(out.stdout)


def evaluate_full_trace(actions, restprice=None, init_fr=None):
    """
    Convenience wrapper for validation: one isolated subprocess run per
    field, returns VF plus all per-day traces needed to check the replica.
    """
    vf = evaluate_vf(actions, restprice, init_fr)
    result = {"vf": vf}
    for name, (node_idx, field) in _FIELD_SPECS.items():
        result[name] = evaluate_field_subprocess(actions, node_idx, field, restprice, init_fr)
    return result


def load_shipped_actions():
    actions_path = DATASET_DIR + "actions.txt"
    shipped = []
    with open(actions_path) as f:
        for line in f.readlines()[1:]:
            line = line.strip()
            if line:
                shipped.append(float(line.split()[1]))
    return shipped


if __name__ == "__main__":
    if "--field" in sys.argv:
        argv = sys.argv[1:]
        field = argv[argv.index("--field") + 1]
        node_idx = int(argv[argv.index("--node") + 1])
        actions_file = argv[argv.index("--actions-file") + 1]
        with open(actions_file) as f:
            payload = json.load(f)
        vals = evaluate_field(payload["actions"], node_idx, field, payload["restprice"], payload.get("init_fr"))
        print(json.dumps(vals))
    else:
        v, d = version_info()
        print(f"HERSS VERSION {v} / VERSION_DATE {d}")

        shipped = load_shipped_actions()
        vf = evaluate_vf(shipped)
        print("VF with shipped actions.txt =", vf, " (expect ~69135.22)")
