"""
Thin cppyy harness around HERSS for the PUMP audit.

Read-only with respect to src/ and data/. Instances live under
analysis/pump_audit/inst_*/ . Run from analysis/pump_audit/.
"""
import os
import cppyy

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

cppyy.load_library(os.path.join(REPO, "src", "herss.so"))
cppyy.include(os.path.join(REPO, "src", "herss.h"))

VERSION = str(cppyy.gbl.VERSION)
VERSION_DATE = str(cppyy.gbl.VERSION_DATE)

# ---------------------------------------------------------------------------
# cppyy cannot hand back HERSS's raw `double*` scenario arrays reliably: the
# first field read works, the next one raises "attempt to access a
# null-pointer" (the LowLevelView outlives the temporary proxy it came from).
# So nothing raw crosses the boundary - these C++ shims return one double by
# value, indexed by node and timestep.
# ---------------------------------------------------------------------------
cppyy.cppdef(r"""
namespace pumpaudit {

inline Scenario* SC(Herss* h, size_t n) { return h->rs->nodes[n]->S; }

double sc(Herss* h, size_t n, const char* f, size_t t) {
    Scenario* s = SC(h, n);
    std::string k(f);
    if (k=="price")            return s->price[t];
    if (k=="inflow")           return s->inflow[t];
    if (k=="up_inflow")        return s->up_inflow[t];
    if (k=="tot_inflow")       return s->tot_inflow[t];
    if (k=="tot_outflow")      return s->tot_outflow[t];
    if (k=="tunnelflow_m3s")   return s->tunnelflow_m3s[t];
    if (k=="hatchflow_m3s")    return s->hatchflow_m3s[t];
    if (k=="overflow_m3s")     return s->overflow_m3s[t];
    if (k=="auto_qmin_m3s")    return s->auto_qmin_m3s[t];
    if (k=="pump_in_m3s")      return s->pump_in_m3s[t];
    if (k=="pump_out_m3s")     return s->pump_out_m3s[t];
    if (k=="res_Mm3")          return s->res_Mm3[t];
    if (k=="res_active_Mm3")   return s->res_active_Mm3[t];
    if (k=="res_masl")         return s->res_masl[t];
    if (k=="res_fr")           return s->res_fr[t];
    if (k=="profit")           return s->profit[t];
    if (k=="overflow_Mm3")     return s->overflow_Mm3[t];
    if (k=="income")           return s->income[t];
    if (k=="cost")             return s->cost[t];
    if (k=="startStopCost")    return s->startStopCost[t];
    if (k=="cost_lrw")         return s->cost_lrw[t];
    if (k=="adjust_cost")      return s->adjust_cost[t];
    if (k=="cost_aggressive_actions") return s->cost_aggressive_actions[t];
    if (k=="Hbrutto")          return s->Hbrutto[t];
    if (k=="Hnetto")           return s->Hnetto[t];
    if (k=="Power")            return s->Power[t];
    if (k=="EstimatedEEKV")    return s->EstimatedEEKV[t];
    if (k=="channel_storage_Mm3") return s->channel_storage_Mm3[t];
    return -987654321.0;   // unknown field sentinel
}

double sc_action(Herss* h, size_t n, size_t col, size_t t) {
    return SC(h, n)->action[t][col];
}

// --- pump-specific -------------------------------------------------------
inline Pump* PU(Herss* h, size_t n) { return static_cast<Pump*>(h->rs->nodes[n]); }

double pu(Herss* h, size_t n, const char* f, size_t t) {
    Pump* p = PU(h, n);
    std::string k(f);
    if (k=="actual_pumped_Mm3") return p->actual_pumped_Mm3[t];
    if (k=="pump_cost_euro")    return p->pump_cost_euro[t];
    if (k=="pump_power_MW")     return p->pump_power_MW[t];
    return -987654321.0;
}

double pu_par(Herss* h, size_t n, const char* f) {
    Pump* p = PU(h, n);
    std::string k(f);
    if (k=="pump_source_idnr")        return double(p->pump_source_idnr);
    if (k=="pump_target_idnr")        return double(p->pump_target_idnr);
    if (k=="pump_inlet_masl")         return p->pump_inlet_masl;
    if (k=="max_discharge")           return p->max_discharge;
    if (k=="headlosscoef")            return p->headlosscoef;
    if (k=="static_motor_efficiency") return p->static_motor_efficiency;
    if (k=="pump_startstop")          return p->pump_startstop;
    if (k=="init_Power")              return p->init_Power;
    if (k=="src_start_masl")          return p->src_start_masl;
    if (k=="src_end_masl")            return p->src_end_masl;
    if (k=="tgt_start_masl")          return p->tgt_start_masl;
    if (k=="tgt_end_masl")            return p->tgt_end_masl;
    return -987654321.0;
}

double pu_curve(Herss* h, size_t n, size_t i) {
    return PU(h, n)->uniform_normalized_curve[i];
}

double pu_eff(Herss* h, size_t n, double q) { return PU(h, n)->calcEfficiency(q); }

// --- reservoir-specific --------------------------------------------------
inline Reservoir* RE(Herss* h, size_t n) { return static_cast<Reservoir*>(h->rs->nodes[n]); }

double re_par(Herss* h, size_t n, const char* f) {
    Reservoir* r = RE(h, n);
    std::string k(f);
    if (k=="res_Mm3")              return r->res_Mm3;
    if (k=="res_masl")             return r->res_masl;
    if (k=="res_HRW")              return r->res_HRW;
    if (k=="res_LRW")              return r->res_LRW;
    if (k=="filling_at_lrw_Mm3")   return r->filling_at_lrw_Mm3;
    if (k=="filling_at_hrw_Mm3")   return r->filling_at_hrw_Mm3;
    if (k=="reservoir_init_fr")    return r->reservoir_init_fr;
    if (k=="reservoir_init_Mm3")   return r->reservoir_init_Mm3;
    if (k=="remaining_active_Mm3") return r->remaining_active_Mm3;
    if (k=="upstream_remaining_active_Mm3") return r->upstream_remaining_active_Mm3;
    return -987654321.0;
}

double masl_to_Mm3(Herss* h, size_t n, double masl) {
    return RE(h, n)->ac_res_masl_2_Mm3.x2y(masl);
}

double node_par(Herss* h, size_t n, const char* f) {
    Node* nd = h->rs->nodes[n];
    std::string k(f);
    if (k=="local_energy_equivalent")        return nd->local_energy_equivalent;
    if (k=="upstream_remaining_active_Mm3")  return nd->upstream_remaining_active_Mm3;
    if (k=="upstream_remaining_Mm3")         return nd->upstream_remaining_Mm3;
    if (k=="remaining_active_Mm3")           return nd->remaining_active_Mm3;
    if (k=="remaining_Mm3")                  return nd->remaining_Mm3;
    return -987654321.0;
}

}  // namespace pumpaudit
""")
PA = cppyy.gbl.pumpaudit

_log_started = False


def _start_log(path):
    global _log_started
    if not _log_started:
        cppyy.gbl.Logger.instance().init(path)
        _log_started = True


class PumpInstance:
    """One loaded HERSS dataset, re-simulatable in process."""

    def __init__(self, inputdir, logfile="pump_audit.log"):
        _start_log(logfile)
        self.inputdir = inputdir if inputdir.endswith("/") else inputdir + "/"
        gc = cppyy.gbl.GlobalConfig()
        gc.globalfile = self.inputdir + "global.txt"
        gc.readGlobalFile()
        gc.inputdir = self.inputdir
        gc.outputdir = self.inputdir + "output/"
        gc.SetDirectoriesAndFilenames()
        # REQUIRED: checkNrSteps() is what actually sets gc->stps. Skipping it
        # leaves stps at NOT_INIT and the next allocation eats all memory.
        gc.Diagnose()
        gc.checkNrSteps()
        self.gc = gc
        self.data = cppyy.gbl.Dataset(gc)
        self.data.readAllData()
        self.h = cppyy.gbl.Herss(gc)
        self.h.prepaireSimulation(self.data)
        self.stps = int(self.h.stps)
        self.nr_nodes = int(self.h.nr_nodes)
        self.restprice = float(self.data.restprice)
        self.dt = int(self.h.getDeltaT(0))
        self._node_cache = {}
        self._s_cache = {}
        self._pump_cache = {}

    # --- diagnostics ---------------------------------------------------
    # NOTE: gc.Diagnose() must NOT be called twice on the same GlobalConfig.
    # TopologyParser::loadFile() appends to `lines` without clearing, so a
    # second Diagnose() parses the topology twice and doubles every node count.
    # It is called exactly once, in __init__.
    def diagnose(self):
        self.h.rs.DiagnoseRiversystemConfiguration()

    # --- topology introspection ---------------------------------------
    def node_types(self):
        out = []
        for n in range(self.nr_nodes):
            nd = self.h.rs.nodes[n]
            out.append((n, str(nd.nodename), int(nd.nodetype)))
        return out

    def pump_idnrs(self):
        return [n for n, _, tp in self.node_types() if tp == 3]

    def reservoir_idnrs(self):
        return [n for n, _, tp in self.node_types() if tp == 0]

    def pstation_idnrs(self):
        return [n for n, _, tp in self.node_types() if tp == 1]

    # --- actions -------------------------------------------------------
    def set_action(self, node, gen, t, v):
        self.h.SetAction(node, gen, t, v)

    def get_action(self, node, gen, t):
        return float(self.h.GetAction(node, gen, t))

    # --- run -----------------------------------------------------------
    def run(self):
        self.h.Simulate()
        return float(self.h.rs.CalcVF(self.restprice))

    # --- per-timestep scalar reads (all via the C++ shim) --------------
    def sc(self, node, field, t):
        v = float(PA.sc(self.h, node, field, t))
        if v == -987654321.0:
            raise KeyError(field)
        return v

    def action_raw(self, node, col, t):
        return float(PA.sc_action(self.h, node, col, t))

    def cost(self, node, t):        return self.sc(node, "cost", t)
    def income(self, node, t):      return self.sc(node, "income", t)
    def profit(self, node, t):      return self.sc(node, "profit", t)
    def power(self, node, t):       return self.sc(node, "Power", t)
    def startstop(self, node, t):   return self.sc(node, "startStopCost", t)
    def hbrutto(self, node, t):     return self.sc(node, "Hbrutto", t)
    def hnetto(self, node, t):      return self.sc(node, "Hnetto", t)
    def res_Mm3(self, node, t):     return self.sc(node, "res_Mm3", t)
    def res_masl(self, node, t):    return self.sc(node, "res_masl", t)
    def res_fr(self, node, t):      return self.sc(node, "res_fr", t)
    def inflow(self, node, t):      return self.sc(node, "inflow", t)
    def up_inflow(self, node, t):   return self.sc(node, "up_inflow", t)
    def tot_inflow(self, node, t):  return self.sc(node, "tot_inflow", t)
    def tot_outflow(self, node, t): return self.sc(node, "tot_outflow", t)
    def pump_in(self, node, t):     return self.sc(node, "pump_in_m3s", t)
    def pump_out(self, node, t):    return self.sc(node, "pump_out_m3s", t)
    def overflow_m3s(self, node, t):return self.sc(node, "overflow_m3s", t)
    def tunnelflow(self, node, t):  return self.sc(node, "tunnelflow_m3s", t)
    def hatchflow(self, node, t):   return self.sc(node, "hatchflow_m3s", t)
    def price(self, t):             return float(self.h.GetPrice(t))

    # --- pump ----------------------------------------------------------
    def pumped_Mm3(self, n, t):     return float(PA.pu(self.h, n, "actual_pumped_Mm3", t))
    def pump_cost(self, n, t):      return float(PA.pu(self.h, n, "pump_cost_euro", t))
    def pump_power_MW(self, n, t):  return float(PA.pu(self.h, n, "pump_power_MW", t))
    def pump_par(self, n, f):       return float(PA.pu_par(self.h, n, f))
    def pump_eff(self, n, q):       return float(PA.pu_eff(self.h, n, q))

    def pump_params(self, n):
        keys = ["pump_source_idnr", "pump_target_idnr", "pump_inlet_masl",
                "max_discharge", "headlosscoef", "static_motor_efficiency",
                "pump_startstop", "init_Power"]
        d = {k: self.pump_par(n, k) for k in keys}
        d["curve"] = [float(PA.pu_curve(self.h, n, i)) for i in range(11)]
        return d

    # --- reservoir / node ----------------------------------------------
    def res_par(self, n, f):        return float(PA.re_par(self.h, n, f))
    def masl_to_Mm3(self, n, masl): return float(PA.masl_to_Mm3(self.h, n, masl))
    def node_par(self, n, f):       return float(PA.node_par(self.h, n, f))

    # --- aggregates ----------------------------------------------------
    def vf_parts(self):
        rs = self.h.rs
        return dict(
            tot_income=float(rs.tot_income_Euro),
            tot_cost=float(rs.tot_cost_Euro),
            tot_profit=float(rs.tot_profit_Euro),
            tot_remaining_MWh=float(rs.tot_remaining_MWh),
            tot_remaining_Euro=float(rs.tot_remaining_Euro),
            tot_active_remaining_Mm3=float(rs.tot_active_remaining_Mm3),
            vf=float(rs.valuefunction_Euro),
        )

    def global_water_balance(self):
        self.h.GlobalWaterBalance()
        rs = self.h.rs
        return dict(
            start=float(rs.start_water_Mm3),
            inflow=float(rs.inflow_volume_Mm3),
            end=float(rs.end_water_Mm3),
            out=float(rs.outgoing_Mm3),
            balance=float(rs.waterbalance),
        )
