"""Independent path: write each cell into a dataset copy, run build/src/herss.exe, read HERSS's
node output files and log; compare with the in-process harness for the same cell (protocol A)."""
import json, os, re, shutil, subprocess
from harness import Model

EXE = os.path.abspath("build/src/herss.exe")
HDR = "Date_NodeID\t4_0\t4_1\t15_0\t15_1\t17_0\t17_1\t13_0\t13_1\t13_2\t1\t0\t2\t3\t6\t10\t16"
CELLS = [  # name, variant, zero_inflow, a, fr_up, fr_low
    ("max_clean_noinflow", "fabel_clean", True, 0.5, 0.0, 1.0),
    ("max_base_inflow", "fabel_base", False, 0.5, 0.0, 0.998),
    ("interior_clean_noinflow", "fabel_clean", True, 0.5, 0.01, 0.99),
    ("datum221_same_state", "fabel_datum221", True, 0.5, 0.0, 1.0),
]

def action_row(date, a_pump, a_gen):
    v = {"13_0": a_gen, "13_1": a_gen, "13_2": a_gen, "0": a_pump}
    cols = HDR.split("\t")[1:]
    return date + "\t" + "\t".join(f"{v.get(c, 0.0):.4f}" for c in cols)

def read_table(path, header_prefix):
    lines = open(path).read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(header_prefix))
    names = lines[i].split()
    return [dict(zip(names, map(float, l.split()))) for l in lines[i + 1:] if l.strip()]

res = {}
for name, var, zi, a, fu, fl in CELLS:
    d = os.path.join("results", "cli", name)
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(var, d)
    shutil.rmtree(os.path.join(d, "output")); os.makedirs(os.path.join(d, "output"))
    dates = [l.split()[0] for l in open(os.path.join(d, "actions.txt")).read().splitlines()[1:]]
    open(os.path.join(d, "actions.txt"), "w").write(
        "\n".join([HDR, action_row(dates[0], a, a), action_row(dates[1], 0.0, 0.0)]) + "\n")
    if zi:
        L = open(os.path.join(d, "inflowseries.txt")).read().splitlines()
        L = [L[0]] + [l.split()[0] + "\t" + "\t".join("0.000" for _ in l.split()[1:]) for l in L[1:]]
        open(os.path.join(d, "inflowseries.txt"), "w").write("\n".join(L) + "\n")
    st = open(os.path.join(d, "start_state.txt")).read()
    st = re.sub(r"(NODE RESERVOIR 10 SKYFONNA) [0-9.]+", rf"\g<1> {fu}", st)
    st = re.sub(r"(NODE RESERVOIR 14 TROLLDAMMEN) [0-9.]+", rf"\g<1> {fl}", st)
    open(os.path.join(d, "start_state.txt"), "w").write(st)
    p = subprocess.run([EXE, "global.txt"], cwd=d, capture_output=True, text=True)
    log = [f for f in os.listdir(d) if f.endswith(".log")][0]
    logtxt = open(os.path.join(d, log)).read()
    pump = read_table(os.path.join(d, "output", "node0_HEISVERKET.txt"), "yyyy mm dd hh Pumped")
    st13 = read_table(os.path.join(d, "output", "node13_HEIMFOSS.txt"), "yyyy mm dd hh Up_Inflow")
    E_in_cli = pump[0]["Power_MW"] * 1.0          # dt = 3600 s -> MWh == MW
    E_out_cli = st13[0]["Power"]
    # in-process, same cell
    m = Model(var, logname=f"herss_cli_{name}.log")
    m.zero_all_other_actions()
    if zi: m.zero_inflow()
    m.set_levels(fu, fl); m.set_loop_actions([a, 0.0], [a, 0.0]); w = m.run(); r = m.read()
    res[name] = {"returncode": p.returncode, "log_WRN": logtxt.count("[WRN]"), "log_ERR": logtxt.count("[ERR]"),
                 "cli": {"pumped_m3s": pump[0]["Pumped_m3s"], "turb_m3s": st13[0]["tot_outflow"],
                         "E_in": E_in_cli, "E_out": E_out_cli, "eta_rt": E_out_cli / E_in_cli,
                         "Hnetto_s": st13[0]["Hnetto"], "Hbrutto_s": st13[0]["Hbrutto"]},
                 "inproc": {"E_in": r["E_in"], "E_out": r["E_out"], "eta_rt": r["eta_rt"], "warnings": w,
                            "Hn_s": r["Hn_s_0"], "Hb_s": r["Hb_s_0"]}}
    res[name]["abs_diff_eta"] = abs(res[name]["cli"]["eta_rt"] - r["eta_rt"])
json.dump(res, open("results/cli_crosscheck.json", "w"), indent=1)
print(json.dumps(res, indent=1))
