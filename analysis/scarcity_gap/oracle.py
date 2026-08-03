#!/usr/bin/env python
"""
Thin wrapper around the real HERSS simulator (via cppyy), parameterised over
instances. Read-only use of the simulator; nothing under src/ is touched.

Parameterised copy of analysis/mini_utahps_daily_dp/oracle.py.

Verified against HERSS VERSION 3.1.03 / VERSION_DATE 20260611, upstream commit
029a2d5.

cppyy pitfalls worked around here (neither is a HERSS behaviour):
  1. Logger::instance().init(...) must be called once before any Simulate(),
     mirroring py_src/pyherss.py, or the LOG_WARN paths crash.
  2. Raw `double*` members surface as cppyy.LowLevelView with unknown extent;
     indexing past position 0 needs an explicit .reshape((T,)) first, and a
     SECOND such read anywhere in the same process reliably segfaults -- even
     for the same field from a freshly built Herss instance. So each single
     field extraction runs in its own subprocess (evaluate_field_subprocess).
     Only evaluate_vf (scalar return, no array read) is safe to call
     repeatedly in-process, which is what the measurement code paths use.

Because a bad topology can make HERSS call std::exit, every subprocess call
carries a timeout.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SO_PATH = os.path.join(REPO, "src", "herss.so")
H_PATH = os.path.join(REPO, "src", "herss.h")
HERE = os.path.dirname(os.path.abspath(__file__))

SUBPROCESS_TIMEOUT = 300

_loaded = False
_logger_ready = False
_cache = {}


def _cppyy():
    import cppyy
    return cppyy


def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    cppyy = _cppyy()
    cppyy.load_library(SO_PATH)
    cppyy.include(H_PATH)
    _loaded = True


def _ensure_logger():
    global _logger_ready
    _ensure_loaded()
    if _logger_ready:
        return
    cppyy = _cppyy()
    logfilename = f"herss_{cppyy.gbl.VERSION}_{cppyy.gbl.VERSION_DATE}.log"
    if not cppyy.gbl.Logger.instance().init(logfilename):
        raise RuntimeError(f"Could not open log file: {logfilename}")
    _logger_ready = True


def version_info():
    _ensure_loaded()
    cppyy = _cppyy()
    return str(cppyy.gbl.VERSION), str(cppyy.gbl.VERSION_DATE)


def build_herss(dataset_dir, globalfile="global.txt"):
    """Fresh GlobalConfig/Dataset/Herss triple, ready to Simulate()."""
    _ensure_logger()
    cppyy = _cppyy()

    gc = cppyy.gbl.GlobalConfig()
    gc.globalfile = dataset_dir + globalfile
    gc.readGlobalFile()
    gc.inputdir = dataset_dir
    gc.outputdir = dataset_dir + "output/"
    gc.SetDirectoriesAndFilenames()
    gc.Diagnose()
    gc.checkNrSteps()

    data = cppyy.gbl.Dataset(gc)
    data.readAllData()

    herss = cppyy.gbl.Herss(gc)
    herss.prepaireSimulation(data)
    herss.rs.DiagnoseRiversystemConfiguration()

    return gc, data, herss


def _run(p, actions, restprice=None, init_fr=None):
    gc, data, herss = build_herss(p.dataset_dir, p.globalfile)
    T = herss.stps
    if len(actions) != T:
        raise ValueError(f"expected {T} actions, got {len(actions)}")
    for t, a in enumerate(actions):
        herss.SetAction(1, 0, t, float(a))
    if init_fr is not None:
        herss.SetReservoir_Init_fr(0, float(init_fr))
    herss.Simulate()
    rp = restprice if restprice is not None else data.restprice
    return gc, data, herss, T, rp, herss.rs.CalcVF(rp)


def evaluate_vf(p, actions, restprice=None, init_fr=None):
    """Cheap and safe: scalar VF only, no raw-array reads."""
    return _run(p, actions, restprice, init_fr)[5]


def evaluate_field(p, actions, node_idx, field, restprice=None, init_fr=None):
    """Fresh HERSS run, ONE double* field read back as a length-T list."""
    _, _, herss, T, _, _ = _run(p, actions, restprice, init_fr)
    buf = getattr(herss.rs.nodes[node_idx].S, field)
    buf.reshape((T,))
    return [buf[t] for t in range(T)]


FIELD_SPECS = {
    "res_masl": (0, "res_masl"),
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


def evaluate_field_subprocess(instance_key, actions, node_idx, field,
                              restprice=None, init_fr=None):
    """One field extraction in an isolated subprocess (see module docstring)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"instance": instance_key, "actions": list(actions),
                   "restprice": restprice, "init_fr": init_fr}, f)
        payload_file = f.name
    try:
        out = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--field", field,
             "--node", str(node_idx), "--payload", payload_file],
            capture_output=True, text=True, check=True, cwd=HERE,
            timeout=SUBPROCESS_TIMEOUT,
        )
    finally:
        os.unlink(payload_file)
    return json.loads(out.stdout)


def evaluate_vf_subprocess(instance_key, actions, restprice=None, init_fr=None):
    """VF via subprocess -- used when the caller already read an array field."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"instance": instance_key, "actions": list(actions),
                   "restprice": restprice, "init_fr": init_fr}, f)
        payload_file = f.name
    try:
        out = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vf", "--payload", payload_file],
            capture_output=True, text=True, check=True, cwd=HERE,
            timeout=SUBPROCESS_TIMEOUT,
        )
    finally:
        os.unlink(payload_file)
    return json.loads(out.stdout)


def evaluate_full_trace(instance_key, actions, restprice=None, init_fr=None):
    """VF plus every per-step trace needed to validate the replica."""
    result = {"vf": evaluate_vf_subprocess(instance_key, actions, restprice, init_fr)}
    for name, (node_idx, field) in FIELD_SPECS.items():
        result[name] = evaluate_field_subprocess(instance_key, actions, node_idx, field,
                                                 restprice, init_fr)
    return result


if __name__ == "__main__":
    from params import INSTANCES

    argv = sys.argv[1:]
    if "--payload" in argv:
        with open(argv[argv.index("--payload") + 1]) as f:
            payload = json.load(f)
        p = INSTANCES[payload["instance"]]
        if "--vf" in argv:
            print(json.dumps(evaluate_vf(p, payload["actions"], payload["restprice"],
                                         payload.get("init_fr"))))
        else:
            field = argv[argv.index("--field") + 1]
            node_idx = int(argv[argv.index("--node") + 1])
            print(json.dumps(evaluate_field(p, payload["actions"], node_idx, field,
                                            payload["restprice"], payload.get("init_fr"))))
    else:
        v, d = version_info()
        print(f"HERSS VERSION {v} / VERSION_DATE {d}")
