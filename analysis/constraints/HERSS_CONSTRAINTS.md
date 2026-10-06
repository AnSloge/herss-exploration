# HERSS constraint inventory — system-wide, from source

**Purpose.** A complete list of the constraints in the HERSS-based scheduling problem, for a discussion
with an OR supervisor about what makes the problem hard. Every row cites `src/` file:line, or is marked
**[inference]** where the claim follows from reading the code but has not been run.

## 0. Provenance and conventions

- **Code state.** Repo HEAD `0e98d83` (branch `c5-part1`). `src/` was last changed by upstream
  commit `0d3fc59` (B. V. Matheussen, 2026-08-26). `VERSION "4.0.00"` and `VERSION_DATE "20260814"`
  are at `herss.h:49-50`.
- **Pin discrepancy (flag).** `src/` is **not** at the upstream commit pinned in `CLAUDE.md`
  (`029a2d5`). `git diff 029a2d5 HEAD -- src/` shows 1257 changed lines, and all of `pump.cpp` is new
  since that pin. Some line numbers in CLAUDE.md §7 are therefore stale. For example, the
  aggressive-action block is now at `powerstation.cpp:801-811`, not 785-791. This document cites
  the current lines.
- **What "abort" means.** `LOG_ERR(x)` calls `std::exit(EXIT_FAILURE)` in both build modes
  (`logger.h:85`, `logger.cpp:41`). Every `LOG_ERR` guard ends the process; nothing is reported back to
  a caller in the same process. `LOG_WARN` only writes to the log file.
- **Classification.** The brief asked for exactly one of three labels. Two more are needed to avoid
  misclassifying rules:
  - **[hard]**: violation aborts the process.
  - **[soft]**: violation adds a cost to V; the run continues.
  - **[simulator-imposed]**: dynamics or coupling, not a decision constraint.
  - **[simulator-imposed: clip]**: the simulator silently projects the realised flow onto what is
    physically available. There is no abort and no penalty; the action is simply not fully carried out.
  - **[not enforced]**: the rule is read or checked, but only a warning is logged. There is no cost and
    no clipping. Calling these "soft" would overstate them.
- **Order of calculation.** Node `n` has `idnr = n` (`riversystem.cpp:69, 76, 82, 88`). Within each
  time step, nodes are simulated in increasing idnr (`herss.cpp:737-745`). Pump power and cost are
  computed after all nodes have finished that step (`herss.cpp:750-752`). Each `Simulate()` call
  re-initialises reservoirs, channel storage and remaining-volume accumulators
  (`herss.cpp:714-727`).
- **Objective.**
  `V = Σ_{n,t} income − Σ_{n,t} cost + restprice · Σ_{n∈PSTATION} e_n · upstream_remaining_active_Mm3[n] · 1000`
  (`riversystem.cpp:462, 495, 502`). Every penalty below enters V through the per-node `S->cost[t]`
  summed at `:495`. `WriteRiverSystemData` holds a duplicate calculation (`:602, :613, :619`).
  `DISCOUNT_RATE` is initialised (`globalconfig.cpp:48-49`) but never used anywhere else in `src/`, so
  V is **undiscounted**.

## 1. Constraint table

### A. RESERVOIR (`reservoir.cpp`)

| constraint | type | what it enforces | source | if violated |
|---|---|---|---|---|
| Lowest regulated level (LRW) | [soft] | keeps the level at or above LRW | `reservoir.cpp:699-703`; enters V via `S->cost[t]` `:760` | cost = `RES_PENALTY · dt/3600 · (LRW − masl)`, linear in depth below LRW, charged per step. All shipped topologies use `RES_PENALTY 300`. **The station tunnel cannot cause this.** The tunnel is processed first (`:512-559`) and cannot draw below LRW (see B, aggressive action). Only the hatch, OUTLET_AUTO_QMIN or a **pump** (C) can take a reservoir below LRW. |
| Highest regulated level (HRW) / flooding | [simulator-imposed] | overflow via overflow curve or spillway `Q = C·L·h^1.5` | `CalcOverflow` `:151-271`; spillway `:233-259`; routed downstream `:685` | Excess water flows to the overflow node. It is not destroyed, but it is lost from V wherever it bypasses a station. **No explicit penalty.** A spillway set below HRW drains down to the spillway level (`:239-243`). |
| `FLOODLEVEL_PENALTY` | [not enforced] | — | parsed `:847-848`; no other use in `src/` | nothing happens (agrees with manual ch. 5) |
| Terminal value capped at HRW | [simulator-imposed] | only active storage LRW→HRW is valued | `:719-732` | water above HRW is worth 0 in V → V has a kink at HRW |
| Head passed to the station capped at HRW | [simulator-imposed] | station head never uses a level above HRW ("should never pay off to flood") | start `:521-525`, end `:706-710` | extra head above HRW gives no extra power. **Pumps do not get this cap:** they read the raw level (`:506-507`, `:715-716`). **[inference]** Lifting water above HRW costs the pump energy but earns the turbine nothing. |
| Start-of-step level is last step's end level | [simulator-imposed] | — | level update after inflow is commented out `:501-502`; used `:521` | the head at the start of the step ignores this step's inflow and any pump draw that already happened |
| Top of reservoir curve | [hard] | volume must stay within the curve | `ValidateReservoirLevelMm3` `:441-449`, called `:499, :565, :607, :645, :652, :693` | abort. Geometry reservoirs: level below the bottom (`:276-279`) or a negative volume (`:287-289`) abort. |
| Hatch action | [hard] | `a ∈ [0,1]` | `:577-581` | abort outside [0,1] (±1e-6) |
| Hatch flow | [simulator-imposed: clip] | `Q = minQ + a·(maxQ − minQ)`, only while level > hatch_masl | `:583-600` | clipped to the volume above hatch_masl. `minQ_hatch` is a **forced** release whatever the action. |
| `OUTLET_AUTO_QMIN` (seasonal forced release) | [simulator-imposed: clip] | releases the seasonal minimum flow | `:617-646` | clipped to the volume above the outlet masl (`:630-632`); a shortfall only logs a warning (`:635-640`). **Its penalty is hard-coded to 0** (`:1071`), so a shortfall does not change V. |
| Reservoir water balance | [hard]† | start + in − out − end = 0 (tolerance 1e-4 Mm³) | `CheckWaterBalance` `:1303-1346` | abort |

† The reservoir and global balance checks are called by the CLI after the run (`main.cpp:103-104`).
They run in-process only if the harness calls `CheckWaterBalance()`/`GlobalWaterBalance()`.

### B. POWERSTATION (`powerstation.cpp`)

| constraint | type | what it enforces | source | if violated |
|---|---|---|---|---|
| Generator action | [hard] | `a_{n,g,t} ∈ [0,1]` (unsigned) | `powerstation.cpp:136-139`; negative also at `:774-777` | abort |
| Discharge map / `GENERATOR_MAX_DISCHARGE` | [hard] (via the action bound) | `Q_g = a_g · Qmax_g` | parse `:508-513, :546-551`; map `:132` (Simulate), `:790` (tunnel) | `Q > Qmax·1.000001` aborts (`:75-78`); cannot happen when a ≤ 1 |
| **Aggressive action** (drawing more than the usable volume) | [soft] + action override | tunnel withdrawal ≤ usable volume above LRW | `GetTunnelFLow` `:801-811`; usable volume `up_res_Mm3 = max(0, res − V_LRW)` `reservoir.cpp:531`; constant `herss.h:99` | If `Q·dt > up_res`: **the whole flow is set to 0** (not clipped) and the cost is `(Q·dt − up_res) · 1000 EUR/Mm³`. The production term therefore has a step discontinuity. The cost is not scaled by dt. The code comment calls it "a minor penalty … just so we dont get the same value in VF" (`:804`). It is a plateau-breaker, not a feasibility guarantee. |
| Second zeroing in Simulate | [simulator-imposed] | station flow ≤ tunnel inflow | `:143-154` | if the requested flow exceeds `up_inflow`, all generators are set to 0 (this follows the override above) |
| `POWSTAT_MIN_DISCHARGE` | [not enforced] | — | parse `:417-418`; check `:157-165` | warning only; power is still computed for `0 < Q < Qmin`. The code comment says "soft constrain" (`:158-159`), but no cost exists. |
| `POWSTAT_STARTSTOP` | [soft] | cost of switching on or off | `:255-278`; into cost `:297`, profit `:300` | `powstat_startstop/2` per generator per on↔off change (on means `a > 0.01`). At t=0 **every** generator takes its previous state from one scalar `init_Power` (`:267`). Shipped values are 1.5–3.0 EUR, so the cost is negligible. |
| Head | [simulator-imposed] | `H_brutto = (h_start + h_end)/2 − POWSTAT_MASL` | `:167` | `h_end` depends on this step's own release, so head is an **implicit** function of the decision |
| Head loss | [simulator-imposed] | `H_netto = H_brutto − k·Q²` (shared: total Q; separate: per generator) | shared `:173-175`; separate `:216-217` | — |
| Turbine efficiency curve | [simulator-imposed] | `P = η(Q) · ρ g H_netto Q · η_gen` | `calcEfficiency` `:68-106`; power `:199-203, :241-245` | η(Q) is a table lookup, non-concave in general (HERSS uses its own 1000-point pre-sampled lookup, `arraycurve.h:36`, not plain linear interpolation) |
| Negative net head | [not enforced] | — | `:177-182`, `:220-225` | warning only; power becomes negative, so income is negative at positive prices (acts like a penalty, but is not labelled one) |
| Station flow balance | [hard] | station inflow = station outflow each step (tolerance 0.001 m³/s) | `:316-324` | abort. **[inference]** This is reached if the station's `AUTO_QMIN` exceeds the action flow: the tunnel then delivers `auto_qmin` (`:796-799`) but the station only passes the action flow. It is also reached if any hatch or overflow outlet points at a station (`reservoir.cpp:601, :685` add to its `up_inflow`). No shipped dataset uses station `AUTO_QMIN` (all 28 occurrences are `-9999`). |
| `MAX_ADJUST` | [hard] (feature blocked) | — | `:437-444` | any value > −1 aborts ("WORK IN PROGRESS") |
| `LOCAL_ENERGY_EQUIVALENT` e_n | terminal-value parameter | converts remaining water to MWh | parse `:427-428`; use `riversystem.cpp:462` | a constant from the topology file, not derived from head. It is inconsistent with the head-dependent physics used inside the horizon (see CLAUDE.md §7). Only `e_n ≥ 0` is validated (`:57-64`). |

### C. PUMP (`pump.cpp`) — exists only in pumped-storage topologies

| constraint | type | what it enforces | source | if violated |
|---|---|---|---|---|
| Pump action | [hard] | `a ∈ [0,1]`, **unsigned** (same as the turbine), `Q = a · MAX_DISCHARGE` | `pump.cpp:204-211` | abort outside [0,1]; `Q > Qmax` aborts (`:173-176`) |
| `MAX_DISCHARGE` | [hard] (configuration) | `0 < Qmax` | `:106-110` | abort. **There is no minimum pump discharge.** |
| `PUMP_INLET_MASL` | [simulator-imposed: clip] | pumping only draws water above the inlet | `:214-232` | pumped volume clipped to `max(0, V_src − V_inlet)`; warning only, no penalty. The check uses the source volume **as it stands when the pump runs**. The pump idnr is below its source, so this is the end-of-previous-step volume, before this step's inflow. |
| **Negative pump head** | [hard] | `H_netto = (h̄_tgt − h̄_src) + k·Q² ≥ 0`, with h̄ = start/end average | `:268-282`; called for every pump at every step `herss.cpp:750-752` (only guard `:260` is `t < stps`) | abort. **This fires even when a = 0** (then `H_netto = H_brutto`). It is a condition on reservoir *levels*: the average target level must never be below the average source level. It is not a condition on the action. |
| Pump efficiency | [simulator-imposed] | `P = ρ g H_netto Q / (η_pump(Q) · η_motor)` | `:284-295`; η lookup `:166-194` | η ≤ 0 with Q > 0 aborts (`:286-290`) |
| Pumping energy cost | objective term | `cost = P · dt/3600 · price_t` | `:297-298`; into V via `S->cost` `:318` | — |
| `PUMP_STARTSTOP` | [soft] | switching cost | `:300-320` | `pump_startstop/2` per on↔off change. It uses the **requested** action (`a > 0.01`), so a pump clipped to zero flow still counts as running. |
| Pumping into a full target | [simulator-imposed] | — | target filled `:239`, before the target's own `Simulate` spills it (`reservoir.cpp:675-686`) | the pumped water spills in the same step and the pumping energy is wasted; no penalty. On a curve-defined target, going past the top of the curve aborts (`reservoir.cpp:499`). |
| Draining the source | [simulator-imposed: clip] + [soft] | — | `:222` | if `PUMP_INLET_MASL < LRW`, the pump can take the source below LRW and the LRW penalty (A) applies. **Pumping is one way the LRW penalty becomes reachable.** |
| Topology rules | [hard] | source and target are RESERVOIRs, distinct, not the pump itself, and **both have higher idnr than the pump** | `:58-104` (also `herss.cpp:391-398`) | abort |
| Pump water balance | — | none | `:342-344` returns 0 | pumped volume is checked only indirectly, through the reservoirs' `pump_in`/`pump_out` (`reservoir.cpp:754, :764`) |

### D. CHANNEL and system-wide

| constraint | type | what it enforces | source | if violated |
|---|---|---|---|---|
| Routing delay | [simulator-imposed] | N cascaded linear reservoirs, total time constant K hours, each `k = K/N` | `cascadedreservoirs.cpp:97-113`; bounds `channel.cpp:36-45`, `cascadedreservoirs.cpp:34` (1 ≤ N ≤ 10, 0 ≤ K ≤ 240) | the exact exponential solution for constant inflow over a step. It is **linear** in the inflow sequence and couples time steps |
| Channel water balance | [hard] | per step (tolerance 1e-4 m³) | `channel.cpp:98-104` | abort (checked inside `Simulate`, so also in-process) |
| Channel storage at horizon end | [simulator-imposed] | — | `channel.cpp:137` (`remaining_active_Mm3 = 0`) | water still in transit at T is worth 0 in V. Releases near the horizon end are penalised implicitly. |
| Channel `QMIN` (seasonal minimum flow) | [soft] | channel outflow ≥ seasonal minimum | check `channel.cpp:116-127`; parse `:272-318` | **step penalty**: a fixed `penalty_cost · dt/3600` whenever outflow < requirement − 1e-3 m³/s, whatever the size of the shortfall. The source's "not quality controlled" abort is commented out (`:281`). |
| Global water balance | [hard]† | start + inflow − end − outlet outflow = 0 (tolerance 1e-4 Mm³) | `Herss::GlobalWaterBalance` `herss.cpp:782-829` | abort. The outlet is taken to be the node with the **highest idnr** (`:805`). |
| Node ordering (upstream idnr < downstream idnr) | [hard] for pumps only | calculation order | pumps `pump.cpp:94-104`. For all other outlets, `SetPointers` checks only `idnr < nr_nodes` (`herss.cpp:363-381`); there is no ordering check. | **[inference]** If an outlet points to a lower idnr, the water is added to `up_inflow[t]` after that node has already run step t, so it is never simulated. The single upstream-to-downstream pass that totals remaining water (`herss.cpp:761-770`) and the terminal term that uses it then undercount. The likely outcome is a global-balance abort (CLI) or a silently wrong V (in-process). |
| Input ranges | — | none | price/inflow checked only under `HERSS_DEBUG_ALL` (`reservoir.cpp:471-486`, which is `false`, `herss.h:83`) | negative prices are accepted |
| Coupling within a step | [simulator-imposed] | see §2 | — | — |

## 2. What makes it hard — synthesis

**Where the difficulty comes from.** The hard, non-convex parts are the ones the simulator imposes, not the explicit constraints:

- **Head depends on the decision itself.** Station head uses the average of the start- and end-of-step levels (`powerstation.cpp:167`), and the end level depends on the release being decided.
- **Efficiency is not concave.** The efficiency curve η(Q) is a non-concave table lookup.
- **Head loss is quadratic.** Net head falls by k·Q².
- **The aggressive-action rule is discontinuous.** Overdrawing the usable volume sets the whole flow to zero (`powerstation.cpp:810`), not the excess.

Routing delay couples stations across time steps, but it is linear (`cascadedreservoirs.cpp:106`), so it causes no trouble for a MILP.

**Pumped storage adds a coupling inside each time step.** It is not sequential:

- The pump has a lower idnr than its reservoirs, so it runs first (`pump.cpp:94-104`).
- Water it lifts is already counted in the target's usable volume for that step's turbine draw (`reservoir.cpp:531`).
- The pump head and the station head both use end-of-step levels (`pump.cpp:268-271`, `reservoir.cpp:706-716`). Each therefore depends on the other's flow in the same step.
- Only the pump's own availability check uses the previous step's volume.

**Safety guards a sensible instance never hits:** action bounds, the top of the reservoir curve, configuration validation, the flow-balance checks, and `MAX_ADJUST`. The pump negative-head abort belongs here too, but it is a condition on reservoir *levels*. The instance generator must guarantee it, because the optimizer cannot avoid it by choosing actions.

**Most operating constraints are soft or clipped, not hard.** The soft ones are:

- the LRW penalty;
- start/stop costs, about 2 EUR per switch in the shipped data;
- the channel QMIN step penalty;
- the aggressive-action penalty, 1000 EUR/Mm³, which is a plateau-breaker by the code's own comment.

Three rules are not enforced at all: `POWSTAT_MIN_DISCHARGE`, `FLOODLEVEL_PENALTY`, and a shortfall on `OUTLET_AUTO_QMIN`. A method can therefore improve V by buying violations cheaply or by landing in unpenalised infeasibility. **Feasibility must be reported in its own table, separate from V.**

## 3. Present only when pumping is present

Pump-specific items:

- the pump action and discharge bounds;
- the `PUMP_INLET_MASL` clip;
- the negative-head abort, a condition on reservoir levels;
- the pump start/stop cost and the pumping energy cost in V;
- the ordering rule "pump idnr < source and target idnr";
- the same-step coupling between pumping and generation.

Pumping also makes the LRW penalty reachable, through the source reservoir. A generation-only system reaches it only through a hatch or `OUTLET_AUTO_QMIN`.

## 4. Open items (not run; would turn [inference] rows into facts)

1. A station with `AUTO_QMIN` > action flow: does it abort at `powerstation.cpp:316-324`?
2. A pump with `a = 0` and crossed levels (average target level below average source level): does it abort at `pump.cpp:276-282`?
3. An outlet pointing to a lower idnr: is the result a global-balance abort, or a silently wrong V in-process?
4. The HRW head-cap asymmetry between pump and turbine: what is its size in a pumped-storage instance?
