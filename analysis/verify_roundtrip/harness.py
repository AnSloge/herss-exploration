"""
Independent round-trip harness for the HEISVERKET (pump 0) / HEIMFOSS (station 13) loop.

Written from src/ and py_src/pyherss.py only. Every energy, head and flow reported here
is read from HERSS's own per-timestep Scenario arrays (S->Power, S->Hbrutto, ...), via
by-value C++ accessors, never recomputed in Python.

Build: analysis/verify_roundtrip/build/src (git archive of HEAD src/, see run_meta.json).
"""
import os
import cppyy

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build", "src")

cppyy.load_library(os.path.join(BUILD, "herss.so"))
cppyy.include(os.path.join(BUILD, "herss.h"))

EXPECTED_VERSION = ("4.0.00", "20260814")
assert (str(cppyy.gbl.VERSION), str(cppyy.gbl.VERSION_DATE)) == EXPECTED_VERSION, \
    (str(cppyy.gbl.VERSION), str(cppyy.gbl.VERSION_DATE))

cppyy.cppdef(r"""
namespace vr {
double sc(Herss* h, int node, const std::string& f, int t) {
    Scenario* S = h->rs->nodes[node]->S;
    if (f == "Power")        return S->Power[t];
    if (f == "Hbrutto")      return S->Hbrutto[t];
    if (f == "Hnetto")       return S->Hnetto[t];
    if (f == "up_inflow")    return S->up_inflow[t];
    if (f == "inflow")       return S->inflow[t];
    if (f == "tot_outflow")  return S->tot_outflow[t];
    if (f == "overflow_m3s") return S->overflow_m3s[t];
    if (f == "auto_qmin_m3s")return S->auto_qmin_m3s[t];
    if (f == "hatchflow_m3s")return S->hatchflow_m3s[t];
    if (f == "tunnelflow_m3s")return S->tunnelflow_m3s[t];
    if (f == "pump_in_m3s")  return S->pump_in_m3s[t];
    if (f == "pump_out_m3s") return S->pump_out_m3s[t];
    if (f == "res_masl")     return S->res_masl[t];
    if (f == "res_Mm3")      return S->res_Mm3[t];
    if (f == "cost_aggr")    return S->cost_aggressive_actions[t];
    throw std::runtime_error("unknown field " + f);
}
double pumped_Mm3(Herss* h, int node, int t) {
    return static_cast<Pump*>(h->rs->nodes[node])->actual_pumped_Mm3[t];
}
double pump_max_discharge(Herss* h, int node) {
    return static_cast<Pump*>(h->rs->nodes[node])->max_discharge;
}
double init_masl(Herss* h, int node) {
    return h->rs->reservoirs[h->rs->nodes[node]->reservoir_idnr].reservoir_init_masl;
}
double init_Mm3(Herss* h, int node) {
    return h->rs->reservoirs[h->rs->nodes[node]->reservoir_idnr].reservoir_init_Mm3;
}
double powstat_masl(Herss* h, int node) {
    return static_cast<Powerstation*>(h->rs->nodes[node])->powstat_masl;
}
size_t warn_count() { return Logger::instance().getWarningCount(); }
}
""")
vr = cppyy.gbl.vr

# Node ids (data/fabelvassdraget/topology.txt)
PUMP, OPPLOFT = 0, 1
SKYFONNA, HEIMFOSS, TROLLDAMMEN = 10, 13, 14
OTHER_STATIONS = {4: 2, 15: 2, 17: 2}      # idnr: nr generators
HATCH_RES = [2, 3, 6, 10, 16]              # reservoirs with OUTLET_HATCH
RESERVOIRS = [2, 3, 6, 10, 14, 16]
N_GEN_HEIMFOSS = 3


def clamp(x):
    return min(1.0, max(0.0, float(x)))


class Model:
    """One HERSS instance for one dataset directory (init exactly once; Diagnose is not idempotent)."""

    def __init__(self, dataset_dir, logname="herss_verify.log"):
        d = os.path.join(dataset_dir, "")
        if not cppyy.gbl.Logger.instance().init(os.path.join(HERE, "results", logname)):
            raise RuntimeError("log init failed")
        gc = cppyy.gbl.GlobalConfig()
        gc.globalfile = d + "global.txt"
        gc.readGlobalFile()
        gc.inputdir = d
        gc.outputdir = d + "output/"
        gc.SetDirectoriesAndFilenames()
        self.diag_rc = {}
        self.diag_rc["gc.Diagnose"] = gc.Diagnose()
        self.diag_rc["gc.checkNrSteps"] = gc.checkNrSteps()
        data = cppyy.gbl.Dataset(gc)
        data.readAllData()
        h = cppyy.gbl.Herss(gc)
        h.prepaireSimulation(data)
        w0 = vr.warn_count()
        h.rs.DiagnoseRiversystemConfiguration()   # void; LOG_ERR would have exited
        self.diag_rc["DiagnoseRiversystemConfiguration_warnings"] = int(vr.warn_count() - w0)
        self.gc, self.data, self.h = gc, data, h
        self.T = int(h.stps)
        self.dataset_dir = dataset_dir

    # ---- inputs -------------------------------------------------------------
    def zero_all_other_actions(self):
        h = self.h
        for t in range(self.T):
            h.SetAction(OPPLOFT, 0, t, 0.0)
            for n, ng in OTHER_STATIONS.items():
                for g in range(ng):
                    h.SetAction(n, g, t, 0.0)
            for r in HATCH_RES:
                h.SetAction(r, 0, t, 0.0)

    def set_loop_actions(self, pump_a, gen_a):
        """pump_a, gen_a: per-timestep lists."""
        for t in range(self.T):
            self.h.SetAction(PUMP, 0, t, clamp(pump_a[t]))
            for g in range(N_GEN_HEIMFOSS):
                self.h.SetAction(HEIMFOSS, g, t, clamp(gen_a[t]))

    def zero_inflow(self):
        for t in range(self.T):
            for r in RESERVOIRS:
                self.h.SetInflowInNode(t, r, 0.0)

    def set_levels(self, fr_up, fr_low):
        self.h.SetReservoir_Init_fr(SKYFONNA, float(fr_up))
        self.h.SetReservoir_Init_fr(TROLLDAMMEN, float(fr_low))

    # ---- run + read ---------------------------------------------------------
    def run(self):
        w0 = vr.warn_count()
        self.h.Simulate()
        return int(vr.warn_count() - w0)

    def read(self):
        h, T = self.h, self.T
        s = lambda n, f, t: float(vr.sc(h, n, f, t))
        r = {"U0": float(vr.init_masl(h, SKYFONNA)), "L0": float(vr.init_masl(h, TROLLDAMMEN))}
        for t in range(T):
            r[f"E_in_{t}"] = -s(PUMP, "Power", t)              # MWh consumed (pump.cpp:321)
            r[f"E_out_{t}"] = s(HEIMFOSS, "Power", t)          # MWh produced (powerstation.cpp:302)
            r[f"pumped_Mm3_{t}"] = float(vr.pumped_Mm3(h, PUMP, t))
            r[f"pumped_m3s_{t}"] = s(PUMP, "tot_outflow", t)
            r[f"turb_m3s_{t}"] = s(HEIMFOSS, "tot_outflow", t)
            for n, tag in ((PUMP, "p"), (HEIMFOSS, "s")):
                r[f"Hb_{tag}_{t}"] = s(n, "Hbrutto", t)
                r[f"Hn_{tag}_{t}"] = s(n, "Hnetto", t)
            r[f"aggr_{t}"] = s(HEIMFOSS, "cost_aggr", t)
            for n, tag in ((SKYFONNA, "U"), (TROLLDAMMEN, "L")):
                r[f"{tag}_end_{t}"] = s(n, "res_masl", t)
                r[f"{tag}_overflow_{t}"] = s(n, "overflow_m3s", t)
                r[f"{tag}_inflow_{t}"] = s(n, "inflow", t)
                r[f"{tag}_upinflow_{t}"] = s(n, "up_inflow", t)
                r[f"{tag}_autoqmin_{t}"] = s(n, "auto_qmin_m3s", t)
                r[f"{tag}_hatch_{t}"] = s(n, "hatchflow_m3s", t)
                r[f"{tag}_tunnel_{t}"] = s(n, "tunnelflow_m3s", t)
        r["E_in"] = sum(r[f"E_in_{t}"] for t in range(T))
        r["E_out"] = sum(r[f"E_out_{t}"] for t in range(T))
        r["eta_rt"] = r["E_out"] / r["E_in"] if r["E_in"] > 0 else float("nan")
        r["V_pumped_m3s_sum"] = sum(r[f"pumped_m3s_{t}"] for t in range(T))
        r["V_turb_m3s_sum"] = sum(r[f"turb_m3s_{t}"] for t in range(T))
        return r
