#!/usr/bin/env python
"""
Thin wrapper around the real HERSS simulator (via cppyy) for multi-variable
instances. Read-only use of the simulator; nothing under src/ is touched.

Generalisation of analysis/scarcity_gap/oracle.py. That module hardcodes
SetAction(1, 0, t, a) because its instances have exactly one decision variable.
res_casc_A has three per timestep -- the RES_A hatch plus two generators at
PSTAT_B -- so actions are passed as a dict of named variables and mapped to
(node_idnr, gen_idnr) pairs here.

Herss::SetAction (herss.cpp:370-388) dispatches on node type: for a PSTATION it
writes generators[gen].action[t], for a RESERVOIR it writes S->action[t][node]
and requires outlet_hatch_in_use. So both variable kinds go through the same
call and no action file has to be written.

Verified against HERSS VERSION 3.1.03 / VERSION_DATE 20260611, upstream commit
029a2d5.

cppyy pitfalls carried over from oracle.py (neither is a HERSS behaviour):
  1. Logger::instance().init(...) must be called once before any Simulate(),
     mirroring py_src/pyherss.py, or the LOG_WARN paths crash.
  2. Raw `double*` members surface as cppyy.LowLevelView with unknown extent;
     indexing past position 0 needs an explicit .reshape((T,)) first, and a
     SECOND such read anywhere in the same process reliably segfaults. So each
     single field extraction runs in its own subprocess. Only evaluate_vf
     (scalar return, no array read) is safe to call repeatedly in-process.

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


def action_targets(p):
    """
    Map variable name -> (node_idnr, gen_idnr) for a CascadeParams instance.

    'hatch'  the RES_A outlet hatch  (gen_idnr ignored by SetAction's RESERVOIR
             branch, but must be a valid size_t)
    'g0'/'g1'  the two PSTAT_B generators
    """
    targets = {"hatch": (p.upper.idnr, 0)}
    for g in range(p.station.n_generators):
        targets[f"g{g}"] = (p.station.idnr, g)
    return targets


def _run(p, actions, restprice=None, init_fr=None):
    """
    actions: {"hatch": [...], "g0": [...], "g1": [...]}, each length T.
    init_fr: optional {reservoir_idnr: fraction} override.
    """
    gc, data, herss = build_herss(p.dataset_dir, p.globalfile)
    T = herss.stps
    targets = action_targets(p)

    missing = set(targets) - set(actions)
    if missing:
        raise ValueError(f"missing action series for {sorted(missing)}")
    for name, series in actions.items():
        if name not in targets:
            raise ValueError(f"unknown action variable {name!r}")
        if len(series) != T:
            raise ValueError(f"{name}: expected {T} actions, got {len(series)}")
        node, gen = targets[name]
        for t, a in enumerate(series):
            herss.SetAction(node, gen, t, float(a))

    if init_fr:
        for idnr, fr in init_fr.items():
            herss.SetReservoir_Init_fr(int(idnr), float(fr))

    herss.Simulate()
    rp = restprice if restprice is not None else data.restprice
    return gc, data, herss, T, rp, herss.rs.CalcVF(rp)


def evaluate_vf(p, actions, restprice=None, init_fr=None):
    """Cheap and safe: scalar VF only, no raw-array reads."""
    return _run(p, actions, restprice, init_fr)[5]


def evaluate_dt(p):
    """data.getDeltaT(t) for every timestep -- verifies the timestep, not assumes it."""
    _, data, herss = build_herss(p.dataset_dir, p.globalfile)
    return [int(data.getDeltaT(t)) for t in range(herss.stps)]


def evaluate_field(p, actions, node_idx, field, restprice=None, init_fr=None):
    """Fresh HERSS run, ONE double* field read back as a length-T list."""
    _, _, herss, T, _, _ = _run(p, actions, restprice, init_fr)
    buf = getattr(herss.rs.nodes[node_idx].S, field)
    buf.reshape((T,))
    return [buf[t] for t in range(T)]


# node index -> field, for res_casc_A (0 RES_A, 1 RES_B, 4 PSTAT_B)
FIELD_SPECS = {
    "res_Mm3_upper":     (0, "res_Mm3"),
    "res_masl_upper":    (0, "res_masl"),
    "overflow_Mm3_upper": (0, "overflow_Mm3"),
    "hatchflow_m3s":     (0, "hatchflow_m3s"),
    "lrw_cost_upper":    (0, "cost"),
    "res_Mm3_lower":     (1, "res_Mm3"),
    "res_masl_lower":    (1, "res_masl"),
    "res_active_Mm3_lower": (1, "res_active_Mm3"),
    "res_active_Mm3_upper": (0, "res_active_Mm3"),
    "overflow_Mm3_lower": (1, "overflow_Mm3"),
    "tunnelflow_m3s":    (1, "tunnelflow_m3s"),
    "lrw_cost_lower":    (1, "cost"),
    "power_MWh":         (4, "Power"),
    "income":            (4, "income"),
    "cost":              (4, "cost"),
    "profit":            (4, "profit"),
    "aggressive_cost":   (4, "cost_aggressive_actions"),
    "startstop_cost":    (4, "startStopCost"),
    "Hnetto":            (4, "Hnetto"),
    "Hbrutto":           (4, "Hbrutto"),
}


def _payload(instance_key, actions, restprice, init_fr):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"instance": instance_key,
                   "actions": {k: list(v) for k, v in actions.items()},
                   "restprice": restprice, "init_fr": init_fr}, f)
        return f.name


def _call(args, payload_file):
    try:
        out = subprocess.run([sys.executable, os.path.abspath(__file__)] + args
                             + ["--payload", payload_file],
                             capture_output=True, text=True, check=True, cwd=HERE,
                             timeout=SUBPROCESS_TIMEOUT)
    finally:
        os.unlink(payload_file)
    return json.loads(out.stdout)


def evaluate_vf_subprocess(instance_key, actions, restprice=None, init_fr=None):
    return _call(["--vf"], _payload(instance_key, actions, restprice, init_fr))


def evaluate_field_subprocess(instance_key, actions, node_idx, field,
                              restprice=None, init_fr=None):
    """One field extraction in an isolated subprocess (see module docstring)."""
    return _call(["--field", field, "--node", str(node_idx)],
                 _payload(instance_key, actions, restprice, init_fr))


def evaluate_full_trace(instance_key, actions, restprice=None, init_fr=None,
                        fields=None):
    """VF plus every per-step trace needed to validate the replica."""
    specs = FIELD_SPECS if fields is None else {k: FIELD_SPECS[k] for k in fields}
    result = {"vf": evaluate_vf_subprocess(instance_key, actions, restprice, init_fr)}
    for name, (node_idx, field) in specs.items():
        result[name] = evaluate_field_subprocess(instance_key, actions, node_idx,
                                                 field, restprice, init_fr)
    return result


if __name__ == "__main__":
    from params2 import INSTANCES

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
        p = INSTANCES["res_casc_A"]
        dts = evaluate_dt(p)
        print(f"T = {len(dts)}, dt distinct = {sorted(set(dts))}")
