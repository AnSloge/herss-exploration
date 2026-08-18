#!/usr/bin/env python
"""
Thin wrapper around the real HERSS simulator (via cppyy) for the full uTAHPS
cascade. Read-only use of the simulator; nothing under src/ is touched.

Generalisation of analysis/cascade/oracle2.py, which maps a fixed set of named
variables ('hatch', 'g0', 'g1') onto res_casc_A's nodes. Here the variables are
one generator per PSTATION, derived from the parsed topology, so nothing is
hardcoded.

Herss::SetAction (herss.cpp:370-388) dispatches on node type: for a PSTATION it
writes generators[gen].action[t]. No action file has to be written.

Verified against HERSS VERSION 3.1.03 / VERSION_DATE 20260611, upstream commit
029a2d5.

WHAT THIS IS AND IS NOT FOR. The coordinate ascent in baselines3 evaluates tens
of thousands of candidates per iteration and needs to resume a trajectory from
the perturbed timestep rather than replay it; neither is possible through this
interface. The oracle is the CROSS-CHECK: every method's winner is re-evaluated
here, and every gap reported is computed on these values, never on replica
values.

cppyy pitfalls carried over from oracle2.py (neither is a HERSS behaviour):
  1. Logger::instance().init(...) must be called once before any Simulate(),
     mirroring py_src/pyherss.py, or the LOG_WARN paths crash.
  2. Raw `double*` members surface as cppyy.LowLevelView with unknown extent;
     indexing past position 0 needs an explicit .reshape((T,)) first, and a
     SECOND such read anywhere in the same process reliably segfaults. So each
     single field extraction runs in its own subprocess. Only evaluate_vf
     (scalar return, no array read) is safe to call repeatedly in-process.

     For per-step validation traces, read the CLI's node output files through
     nodefiles.py instead -- one run gives every field for every node, against
     one subprocess per field here.

Because a bad topology can make HERSS call std::exit, every subprocess call
carries a timeout.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SO_PATH = os.path.join(REPO, "src", "herss.so")
H_PATH = os.path.join(REPO, "src", "herss.h")
HERSS_EXE = os.path.join(REPO, "src", "herss.exe")

SUBPROCESS_TIMEOUT = 600

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


def build_herss(p):
    """Fresh GlobalConfig/Dataset/Herss triple, ready to Simulate()."""
    _ensure_logger()
    cppyy = _cppyy()

    gc = cppyy.gbl.GlobalConfig()
    gc.globalfile = p.dataset_dir + p.globalfile
    gc.readGlobalFile()
    gc.inputdir = p.dataset_dir
    gc.outputdir = p.dataset_dir + "output/"
    gc.SetDirectoriesAndFilenames()
    gc.Diagnose()
    gc.checkNrSteps()

    data = cppyy.gbl.Dataset(gc)
    data.readAllData()

    herss = cppyy.gbl.Herss(gc)
    herss.prepaireSimulation(data)
    herss.rs.DiagnoseRiversystemConfiguration()

    return gc, data, herss


def _apply(p, herss, actions, T):
    """
    Write one action series per station. p.horizon selects a sub-window; the
    steps outside it keep whatever the action file held, so a windowed run is
    only meaningful when the window is the whole horizon or the caller has
    accounted for the tail. run_full_cascade asserts on that.
    """
    t0 = p.horizon[0] if p.horizon else 0
    for s in p.stations:
        series = actions[f"g{s.idnr}"]
        if len(series) != T:
            raise ValueError(f"g{s.idnr}: expected {T} actions, got {len(series)}")
        for t, a in enumerate(series):
            herss.SetAction(s.idnr, 0, t0 + t, float(a))


def evaluate_vf(p, actions, restprice=None, init_fr=None):
    """Cheap and safe: scalar VF only, no raw-array reads."""
    gc, data, herss = build_herss(p)
    T = len(actions[f"g{p.stations[0].idnr}"])
    _apply(p, herss, actions, T)
    if init_fr:
        for idnr, fr in init_fr.items():
            herss.SetReservoir_Init_fr(int(idnr), float(fr))
    herss.Simulate()
    rp = restprice if restprice is not None else data.restprice
    return herss.rs.CalcVF(rp)


def evaluate_dt(p):
    """data.getDeltaT(t) for every timestep -- verifies the timestep, not assumes it."""
    _, data, herss = build_herss(p)
    return [int(data.getDeltaT(t)) for t in range(herss.stps)]


def write_action_file(p, actions, path):
    """
    An action file in the shipped format, for driving the CLI.

    Header is 'Date_NodeID' plus '<idnr>_0' per station, matching
    data/utahps_daily/actions_utahps.txt; the date column is copied from the
    inflow file so the two stay aligned.
    """
    with open(p.dataset_dir + p.inflowfile) as f:
        rows = [l.split() for l in f if l.strip()]
    dates = [r[0] for r in rows[1:]]
    if p.horizon:
        dates = dates[p.horizon[0]:p.horizon[1]]

    cols = [f"g{s.idnr}" for s in p.stations]
    T = len(actions[cols[0]])
    if len(dates) != T:
        raise ValueError(f"{len(dates)} dates against {T} actions")

    with open(path, "w") as f:
        f.write("Date_NodeID\t" + "\t".join(f"{s.idnr}_0" for s in p.stations) + "\n")
        for t in range(T):
            f.write(dates[t] + "\t"
                    + "\t".join(f"{actions[c][t]:.6f}" for c in cols) + "\n")


def run_cli(p, cwd=None):
    """
    Run the HERSS command-line binary, which writes the full per-step node
    output that nodefiles.py reads. Used by validate3_replica.
    """
    r = subprocess.run([HERSS_EXE, p.globalfile], cwd=cwd or p.dataset_dir,
                       capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"herss.exe failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


# ------------------------------------------------------------------ subprocess API

def _payload(actions, restprice, init_fr, horizon):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"actions": {k: list(v) for k, v in actions.items()},
                   "restprice": restprice, "init_fr": init_fr,
                   "horizon": horizon}, f)
        return f.name


def evaluate_vf_subprocess(actions, restprice=None, init_fr=None, horizon=None):
    """
    One VF in an isolated process. Slower than evaluate_vf but immune to any
    state a long-lived cppyy session might accumulate; used for the blocking
    determinism check.
    """
    payload = _payload(actions, restprice, init_fr, horizon)
    try:
        out = subprocess.run([sys.executable, os.path.abspath(__file__), "--vf",
                              "--payload", payload],
                             capture_output=True, text=True, check=True, cwd=HERE,
                             timeout=SUBPROCESS_TIMEOUT)
    finally:
        os.unlink(payload)
    return json.loads(out.stdout)


if __name__ == "__main__":
    import params3

    argv = sys.argv[1:]
    if "--payload" in argv:
        with open(argv[argv.index("--payload") + 1]) as f:
            pl = json.load(f)
        p = params3.get(horizon=tuple(pl["horizon"]) if pl["horizon"] else None)
        print(json.dumps(evaluate_vf(p, pl["actions"], pl["restprice"],
                                     pl.get("init_fr"))))
    else:
        v, d = version_info()
        print(f"HERSS VERSION {v} / VERSION_DATE {d}")
        p = params3.get()
        dts = evaluate_dt(p)
        print(f"T = {len(dts)}, dt distinct = {sorted(set(dts))}")
