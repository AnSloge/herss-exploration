#!/usr/bin/env python
"""
Instance-level validation, run before anything is built on top of the instances.

Checks, per instance:
  1. HERSS loads it: GlobalConfig.Diagnose(), checkNrSteps(),
     Riversystem::DiagnoseRiversystemConfiguration() all complete without
     LOG_ERR (which would std::exit the process -- hence the subprocess).
  2. The CLI run produces output and its log contains no ERROR/WARN lines.
  3. The global water balance from output/riversystem_*_output.txt closes to
     zero, with channel storage at start and end reported separately so the
     linear-reservoir transient can be read off.
  4. rho and R, recomputed from the instance's own files.

Upstream topology validation is weak (riversystem.cpp:58 silently rewrites node
ids to file positions), so an invalid slice can be accepted without complaint.
This script is the guard against that.
"""

import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(REPO, "src", "herss.exe")

from params import INSTANCES, regime_numbers  # noqa: E402


def cli_run(p):
    """Run the C++ CLI in the instance directory; return (ok, log_findings)."""
    d = p.dataset_dir
    r = subprocess.run([EXE, "global.txt"], cwd=d, capture_output=True, text=True, timeout=300)
    ok = (r.returncode == 0) and ("ended normally" in r.stdout)
    findings = []
    for fn in os.listdir(d):
        if fn.endswith(".log"):
            with open(os.path.join(d, fn)) as f:
                for line in f:
                    if re.search(r"\bERROR\b|\bWARN", line):
                        findings.append(line.strip())
    return ok, findings


def load_herss_in_subprocess(key):
    """Diagnose()/checkNrSteps()/DiagnoseRiversystemConfiguration() via oracle."""
    code = (
        "import json,sys;"
        "sys.path.insert(0,%r);"
        "from params import INSTANCES;"
        "import oracle;"
        "p=INSTANCES[%r];"
        "gc,data,h=oracle.build_herss(p.dataset_dir,p.globalfile);"
        "print(json.dumps({'stps':int(h.stps),'restprice':float(data.restprice),"
        "'nr_nodes':int(gc.nr_nodes),'nr_reservoirs':int(gc.nr_reservoirs),"
        "'nr_pstations':int(gc.nr_pstations),'nr_channels':int(gc.nr_channels)}))"
    ) % (HERE, key)
    r = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True,
                       text=True, timeout=600)
    if r.returncode != 0:
        return None, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1]), None


def water_balance(p):
    d = p.dataset_dir + "output/"
    fn = [f for f in os.listdir(d) if f.startswith("riversystem_") and f.endswith("_output.txt")]
    if not fn:
        return None
    with open(d + fn[0]) as f:
        txt = f.read()
    out = {}
    for k in ["start_water_Mm3", "inflow_volume_Mm3", "outflow_Mm3",
              "end_water_Mm3", "waterbalance"]:
        m = re.findall(rf"{k}\s*=\s*(-?[\d.]+)", txt)
        if m:
            out[k] = float(m[-1])
    # per-node remaining storage, to separate reservoir from channel
    for m in re.finditer(r"Node\s+(\d+)\s+(\S+)\s+Nodetype\s+\d+\s+(\S+)\s+(-?[\d.]+)", txt):
        out[f"remaining_{m.group(3).lower()}_{m.group(2)}"] = float(m.group(4))
    return out


def main():
    keys = sys.argv[1:] or ["hjelle", "gresse", "hjelle_e163"]
    all_ok = True
    report = {}

    for key in keys:
        p = INSTANCES[key]
        print(f"=== {p.name} ===")
        entry = {}

        ok, findings = cli_run(p)
        print(f"  [{'PASS' if ok and not findings else 'FAIL'}] CLI run; "
              f"{len(findings)} ERROR/WARN lines in log")
        for line in findings[:5]:
            print(f"        {line}")
        entry["cli_ok"] = bool(ok)
        entry["log_findings"] = findings
        all_ok &= ok and not findings

        info, err = load_herss_in_subprocess(key)
        loaded = info is not None
        print(f"  [{'PASS' if loaded else 'FAIL'}] Diagnose / checkNrSteps / "
              f"DiagnoseRiversystemConfiguration")
        if loaded:
            print(f"        T={info['stps']}, restprice={info['restprice']}, "
                  f"nodes={info['nr_nodes']} "
                  f"({info['nr_reservoirs']}R/{info['nr_pstations']}P/{info['nr_channels']}C)")
        else:
            print(f"        {err}")
        entry["herss_load"] = info
        all_ok &= loaded

        wb = water_balance(p)
        closes = wb is not None and abs(wb.get("waterbalance", 9e9)) < 1e-6
        print(f"  [{'PASS' if closes else 'FAIL'}] water balance = "
              f"{wb.get('waterbalance') if wb else 'n/a'}")
        if wb:
            print(f"        start {wb['start_water_Mm3']:.6f} + inflow "
                  f"{wb['inflow_volume_Mm3']:.6f} - outflow {wb['outflow_Mm3']:.6f} "
                  f"= end {wb['end_water_Mm3']:.6f}")
            for k, v in wb.items():
                if k.startswith("remaining_channel"):
                    print(f"        channel storage at end: {v:.6f} Mm3")
        entry["water_balance"] = wb
        all_ok &= closes

        reg = regime_numbers(p)
        entry["regime"] = reg
        print(f"  rho = {reg['rho']:.4f}   R = {reg['R']:.4f}   "
              f"(active {reg['active_Mm3']:.2f}, init {reg['init_active_Mm3']:.3f}, "
              f"inflow {reg['inflow_Mm3']:.3f}, capacity {reg['turbine_capacity_Mm3']:.3f} Mm3)")
        if reg["rho"] > 1.0:
            print("  !! rho > 1 -- NOT the scarcity regime. The slice did not do what it should.")
            all_ok = False

        report[key] = entry
        print()

    with open("validation_instance.json", "w") as f:
        json.dump(report, f, indent=2, default=float)
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
