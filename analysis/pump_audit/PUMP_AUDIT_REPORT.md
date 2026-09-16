# Audit of the HERSS `PUMP` node: is it usable as an evaluation oracle?

**Date:** 2026-09-16
**Repository commit at start and end of audit:** `7c3d31efe94ef5fa04f89fb5f76ec04882f34aae` (branch `system-design`)
**HERSS `VERSION` / `VERSION_DATE`:** `4.0.00` / `20260814`
**Pump feature commit:** `d29a86b` "Add QMIN and pump station support" (Terje Sandø), merged via PR #20 `feature/qmin-pump-pr`
**Working tree:** nothing under `src/` or `data/` was modified. All artefacts are under `analysis/pump_audit/`.

---

## Bottom-line verdict

**Usable as an evaluation oracle — with four listed caveats, three of which must be
encoded as instance-generation constraints before any automated river-system design
search is pointed at a pumping topology.**

The core machinery is sound and, on the evidence here, better than expected:

- Mass conservation is **exact** — `|balance| = 0.000e+00 Mm³` at every timestep at both
  reservoirs, and the water leaving the source equals the water arriving at the target to
  the last bit (the pump moves one variable into another, so this is exact by construction).
- Energy and cost accounting are **exact** against a closed-form reference —
  `|cost_model − cost_ref| = 0.000e+00 EUR`, and the sign is right: pumping at a positive
  price lowers `V`.
- Determinism is **bit-for-bit** over 8 identical runs, on the value function and on a
  SHA-256 fingerprint of every per-timestep output of every node.
- State reset across A → B → A → B → A in one process is **bit-for-bit exact**.
- A Python replica of the pump timestep now reproduces HERSS to **7.3e-12 EUR worst
  |ΔVF| over 24 action sequences**, with **every per-timestep field matching to 0.0**.
- The shipped regression suite `src_tests/test_pump.cpp` passes **26/26** — notably, it is the
  only substantial part of the HERSS test suite that currently runs clean (§2.1).

The caveats are about *what the model means*, not about whether it computes it reliably:

1. **The pump and the turbine do not use the same head datum.** A pump lifts from the
   source reservoir's *water level*; a turbine drops to a *fixed* `POWSTAT_MASL`. Round-trip
   efficiency is therefore not the product of the component efficiencies — it drifts with the
   lower reservoir's level, measured here from 0.5926 to 0.6956 for a system whose components
   multiply to exactly 0.6400. A deliberately (but legally) mis-specified topology reached a
   round-trip efficiency of **3.198 — net energy creation**. See §3.3 and risk **R1**.
2. **Nothing validates that the target reservoir stays above the source.** When net head goes
   negative, HERSS calls `LOG_ERR`, which is `std::exit(EXIT_FAILURE)` — the *whole process*
   dies mid-simulation, taking an in-process optimizer with it. Same for an out-of-range action.
   See risks **R2**, **R3**.
3. **Pumping is not limited by the target reservoir's capacity.** Water pumped into a full
   reservoir is paid for and then spilled, and spilled water is valued at zero. Physically
   defensible, but it is an unbounded value sink an optimizer can fall into. See risk **R5**.
4. **Start/stop cost keys off the *action*, not the actual pumped volume**, with a hard
   threshold at `a > 0.01`. A pump whose source is empty is still charged a start cost for
   moving 0.0 Mm³; and any action in `(0, 0.01]` pumps real water while paying no commitment
   cost at all. See risks **R6**, **R7**.

None of these is a *correctness* defect in the pump's own arithmetic. They are boundary
conditions that HERSS does not enforce, and a topology generator that does not know about
them will produce instances that either abort the process or quietly reward nonsense.

**Recommendation:** proceed with pumping as an oracle. Encode R1–R3 as hard constraints in
any instance generator (see §7 for the exact rules), wrap `Simulate()` in a subprocess or
clamp actions before calling, and use the validated replica in `replica_pump.py` for exact-DP
work on small instances.

---

## 1. What was added, and where

### 1.1 Files

| File | Change |
|---|---|
| `src/pump.cpp` | **New**, 590 lines. The whole node type. |
| `src/herss.h` | `NodeType::PUMP`, `class Pump: public Node` (:861–929), `Scenario::pump_in_m3s` / `pump_out_m3s` (:431–432), `Reservoir::ptr_pumps_as_source` / `ptr_pumps_as_target` (:691–693), `nr_pumps` on `GlobalConfig` and `Riversystem` |
| `src/globalconfig.cpp` | counts `PUMP` nodes in `Diagnose` and `DiagnoseTopologyFile`; one action column per pump |
| `src/riversystem.cpp` | allocates `Pump *pumps`, wires them into `nodes[]`, calls `ValidatePumpSettings`, reports `Sum_Pump_Consumption_MWh`, includes `PUMP` in the start/stop cost total |
| `src/herss.cpp` | parses `NODE PUMP`, resolves source/target pointers, registers the reverse `ptr_pumps_as_*` links, maps the action column, handles `PUMP` in `SetAction`/`GetAction`, and runs the **second pass** `CalcPowerAndCost` after every node has stepped (:747–752) |
| `src/reservoir.cpp` | zeroes `pump_in_m3s`/`pump_out_m3s` in `InitReservoir` (:303–306); records start (:506–507) and end (:715–716) levels into connected pumps; folds pumped water into `tot_inflow` (:754) and `tot_outflow` (:764); writes `pump_in`/`pump_out` columns to the node file |
| `src/scenario.cpp` | allocates/zeroes/frees the two new arrays |
| `src_tests/test_pump.cpp` | **New**, 435 lines of gtest (unit + integration) |
| `src_tests/pump_test/`, `data/mini_pump_test/` | two fixture datasets |
| `doc/herss.tex` | new §`subsec:pump` and scattered updates |

### 1.2 Decision variable

One action per `PUMP` node per timestep, `a ∈ [0, 1]`, dimensionless.
Pumped discharge is `Q = a · MAX_DISCHARGE` [m³/s]. `SetAction(pump_idnr, gen_idnr, t, a)`
accepts a `gen_idnr` but **ignores it** — a pump is a single unit in v1 (`herss.cpp:469–472`).
The action file column is named by the pump's bare idnr (e.g. `0`), not `0_0`.

Range is enforced at `pump.cpp:206–210` with a `±1e-6` tolerance; outside it, the process exits.

### 1.3 How water moves

`Pump::Simulate` (`pump.cpp:190–243`), which runs at the pump's own position in the
ascending-idnr node loop:

```
req_Mm3        = max(0, a) * MAX_DISCHARGE  ->  Mm3 over dt
fill_at_inlet  = source.masl2Mm3(PUMP_INLET_MASL)
available_Mm3  = max(0, source.res_Mm3 - fill_at_inlet)
actual_Mm3     = min(req_Mm3, available_Mm3)

source.res_Mm3          -= actual_Mm3        # :235
source.S->pump_out_m3s  += actual_m3s        # :236
target.res_Mm3          += actual_Mm3        # :239
target.S->pump_in_m3s   += actual_m3s        # :240
```

The pump mutates the two reservoirs' volumes **directly**, which is why
`Pump::ValidatePumpSettings` requires `pump.idnr < source.idnr` and `pump.idnr < target.idnr`:
the withdrawal and the injection must be in place before either reservoir runs in the same
timestep.

**Consequence that matters for formulation:** the pump sees the source volume as it stood at
the **end of the previous timestep** — before this step's local inflow and before this step's
turbine tailwater. Pumping and generating in the same timestep do not see each other.
Verified empirically (§3.4).

### 1.4 Water balance at both reservoirs

`Reservoir::Simulate` folds the pumped flows into its reported totals:

```
S->tot_inflow[t]  = (local + upstream) [m3/s] + S->pump_in_m3s[t]      # reservoir.cpp:754
S->tot_outflow[t] = (hatch+tunnel+overflow+autoqmin)   + S->pump_out_m3s[t]  # :764
```

so `Reservoir::CheckWaterBalance` closes without any pump-specific term.
`Pump::GetStartWater_Mm3` / `GetEndWater_Mm3` return 0.0 and `Pump::CheckWaterBalance` is a
**no-op returning 0** — there is no per-node balance check for a pump. Mass conservation is
by construction; this audit verifies it empirically instead (§3.1).

### 1.5 Energy cost and where it enters V

`Pump::CalcPowerAndCost` (`pump.cpp:249–329`) runs in a **second pass over pumps after every
node has stepped** (`herss.cpp:747–752`), so both reservoirs' end-of-step levels are final:

```
src_avg  = (src_start_masl + src_end_masl)/2         # :268
tgt_avg  = (tgt_start_masl + tgt_end_masl)/2
Hbrutto  = tgt_avg - src_avg                         # :271  target MINUS source
Hnetto   = Hbrutto + HEADLOSSCOEF * Q^2              # :272  ADDED, not subtracted
P_hyd_MW = 1000 * GRAVITY * Hnetto * Q / 1e6         # :292
power_MW = P_hyd_MW / (eta_pump(Q) * STATIC_MOTOR_EFFICIENCY)   # :294  DIVIDED
energy_MWh = power_MW * dt / 3600
cost       = energy_MWh * price[t]
S->cost[t] = cost + startstopCost                    # :318
S->Power[t] = -energy_MWh                            # :321  negative = consumption
```

`Riversystem::CalcVF` sums `S->cost[t]` over **all** nodes, so the pump's cost enters `V`
through `tot_cost_Euro` and nothing else. `S->income[t]` is forced to `0.0`. A pump has
`remaining_active_Mm3 = 0` and no `ptr_downstream_node`, so it contributes **nothing** to the
terminal water-value term; a pump changes `V`'s terminal part only through the volumes it
leaves in the two reservoirs. Verified: the ΔV decomposition closes to **2.7e-11 EUR** (§3.2).

Sign conventions are the mirror image of a power station, correctly:

| | Power station | Pump |
|---|---|---|
| head loss | `Hnetto = Hbrutto − k·Q²` | `Hnetto = Hbrutto + k·Q²` |
| efficiency | multiplies | divides |
| `S->Power[t]` | `+MWh` | `−MWh` |
| datum | `POWSTAT_MASL` (fixed) | source reservoir **water level** |

### 1.6 Efficiency

Head-**independent**; a function of discharge only.
Two curve forms, both giving `η_pump(Q)` as a fraction:

- `UNIFORM_NORMALIZED_CURVE 11` — 11 points on `Qn = Q/MAX_DISCHARGE ∈ [0,1]`, evaluated by a
  plain index-and-lerp in `Pump::calcEfficiency` (`pump.cpp:182–190`). **This does not go
  through `ArrayCurve`**, so it never gets `ArrayCurve`'s `xdiff`/`ydiff` sanity checks — a
  perfectly flat pump curve is accepted where a flat `TURBINE_CURVE` is a fatal error.
- `PUMP_CURVE <n>` — arbitrary `(Q, η%)` points through `ArrayCurve`. Parsed
  (`pump.cpp:557–583`) but **absent from the manual's topology-syntax block** and unused by
  both shipped fixtures; **untested by this audit**.

A hard zero below `Q < 1e-6` m³/s, matching the power station.

The total efficiency is `η_pump(Q) · STATIC_MOTOR_EFFICIENCY`, both constants w.r.t. head.

### 1.7 Start/stop

`pump.cpp:300–316`, a faithful copy of `Powerstation::Simulate:257–278`: a transition of
`(action > 0.01)` between `t−1` and `t` costs `PUMP_STARTSTOP / 2`. At `t = 0` the previous
state comes from the state file via `init_Power > 0.01`. Consistent with the rest of HERSS.

### 1.8 Agreement with the manual

`doc/herss.tex` §`subsec:pump` (:1114–1185) is accurate on everything it covers:
the head equation, the `+k·Q²` sign, the `P = ρg·H·Q / (η_pump·η_motor)` form, the numbering
requirement, and the `/2` start/stop split. The `NODE PUMP … MWh` state-file row is documented
at :1489. Documentation quality here is better than the HERSS average.

**Undocumented, found in this audit:**

| # | Behaviour | Where |
|---|---|---|
| D1 | The pump's head datum differs from the power station's, so round-trip efficiency ≠ product of component efficiencies | §3.3 |
| D2 | Negative net head is a **fatal process exit**, not a warning; no topology rule is stated that would prevent it | §4.5 |
| D3 | An out-of-range action is a **fatal process exit** | §4.1 |
| D4 | Pumping is not clipped by the target reservoir's capacity | §4.4 |
| D5 | Start/stop is charged on the action even when `actual_pumped = 0` | §4.3 |
| D6 | `PUMP_CURVE` is parsed but missing from the documented syntax block; the uniform-curve path bypasses `ArrayCurve` validation | §1.6 |
| D7 | `Pump::Simulate` unconditionally zeroes its own `S->inflow[t]` and `S->income[t]`, so a pump node silently cannot carry local inflow | `pump.cpp:242–244` |

**Inconsistency with existing conventions:** none found in the pump's own arithmetic. The
sign, `/2` start/stop, `1e-6` efficiency cutoff, `±1e-6` action tolerance and
`start/end level averaging` all match the power station exactly.

**Fixture drift (minor, hygiene):** `data/mini_pump_test/` and `src_tests/pump_test/` have
diverged — different idnr numbering (`data/` uses 6 nodes 0–5, `src_tests/` uses 5 nodes 0–4),
different `PUMP_INLET_MASL` (59.5 vs 61.0), different `SHARED_PENSTOCK`. The header comment in
`data/mini_pump_test/global.txt` describes the `src_tests/` numbering, not its own.
`src_tests/pump_test/global.txt` says "Kept in sync manually" — it is not.

---

## 2. How this was tested

Three purpose-built instances under `analysis/pump_audit/`, plus a copy of the shipped gtest
fixture. All curves in `inst_min` are exactly linear (1.0 Mm³ per metre) and its pump curve is
flat at 80 % with `η_motor = 1.0` and `HEADLOSSCOEF = 0`, so every number has a closed form.

| Instance | Purpose |
|---|---|
| `inst_fixture/` | verbatim copy of `src_tests/pump_test/` (8 daily steps, real curves, start/stop 100) |
| `inst_min/` | 24 hourly steps, linear curves, flat efficiency, `POWSTAT_MASL` = source reservoir's start level |
| `inst_energygen/` | `inst_min` with reservoir_B at 90–100 masl against `POWSTAT_MASL` 55 — a legal but inconsistent tailwater datum |
| `inst_invhead/` | `inst_min` with the pump's target *below* its source |

Scripts (all runnable from `analysis/pump_audit/` with `../../.venv/bin/python`):

| Script | Covers | Output |
|---|---|---|
| `pump_oracle.py` | cppyy harness + C++ accessor shim | — |
| `part2_physics.py` | §3.1, §3.2 | `part2_results.json` |
| `part2_head.py` | §3.3, §3.4 | `part2_head_results.json` |
| `part3_determinism.py` | §4 (determinism/reset/responsiveness/diagnostics) | `part3_results.json` |
| `part4_edge.py` + `_probe.py` | §5 edge cases | `part4_results.json` |
| `replica_pump.py`, `params_pump.py`, `part5_replica.py` | §6 replica | `part5_replica_results.json` |

### 2.1 The shipped gtest suite — it does run, and the pump passes 26/26

`make test` fails on this machine because the Makefile hardcodes `GTEST_DIR = /usr/src/gtest`
and builds gtest from source, which is not installed. But prebuilt **gtest 1.11** shared
libraries *are* present under `/home/andslo/miniconda3/lib`, so the suite can be built against
those instead. Compiled into the scratchpad (nothing written under `src/`), run with cwd =
`src/` so the fixtures' relative paths resolve:

```bash
# objects built into a scratch dir from src/*.cpp (minus main.cpp) and src_tests/*.cpp
g++ -I<repo>/src -I$CONDA_PREFIX/include -pthread -c src_tests/test_pump.cpp -o t_test_pump.o
g++ -pthread -o test_runner <herss objs> <test objs> \
    -L$CONDA_PREFIX/lib -lgtest -lgtest_main -Wl,-rpath,$CONDA_PREFIX/lib
cd src && ./test_runner --gtest_filter='Pump*'
```

Result:

```
[==========] 26 tests from 2 test suites ran. (19 ms total)
[  PASSED  ] 26 tests.
```

17 `PumpUnitTest` + 9 `PumpIntegrationTest`, including the death tests for every
`ValidatePumpSettings` branch, `PumpingMovesWaterAndIncreasesRemainingValueExactly`,
`StartStopCostIsChargedOnEveryTransition`, `FirstTimestepStartStopUsesTheStartState`,
`StateFileRoundTripsThePumpOperatingState`, `ReservoirTotalFlowsIncludePumpedWater` and
`PumpFlowSeriesAreResetBetweenSimulations`. **The pump's shipped regression tests are green.**

**The rest of the baseline is not.** Suite by suite (`--gtest_filter` per suite, since a
`LOG_ERR` anywhere kills the whole binary):

| suite | result |
|---|---|
| **`Pump*`** | **26 passed** |
| `Line*` | 26 passed |
| `GlobalConfig*` | 10 passed |
| `Riversystem*` | 6 passed |
| `ArrayCurve*` | 5 passed, **1 FAILED** — `ArrayCurveTest.X2YReturnsErrorOnOutOfBoundsInput` |
| `Dataset*` | **aborts** — `src_tests/utahps_test/inflow.txt` column count no longer matches the topology |
| `Reservoir*` | **aborts** — `arraycurve.cpp:139` `x2y` error |
| `Powerstation*`, `ValueFunction*`, `WaterBalance*` | **abort** — `src_tests/utahps_test/global.txt` uses keyword `OUTPUTFILE`, which `readGlobalFile` no longer recognises → `std::exit` |
| `test_channel.cpp` | **does not compile** — references `Channel::traveltime` and `Channel::decay`, neither of which exists in `src/channel.cpp` any more |

That is pre-existing drift between `src/` and the shared `src_tests/utahps_test/` fixture, and
is **unrelated to the pump** — but it means the pump suite is currently the only substantial
part of the HERSS regression suite that runs clean end to end. Per CLAUDE.md §10 item 2, this
is the recorded state of `make test` at commit `7c3d31e`.

**Evaluation cost** (in-process `Simulate()` + `CalcVF()`, `WRITE_NODEFILES 0`):
`inst_fixture` (8 steps, 5 nodes) **23.3 µs** ≈ 43 000 eval/s;
`inst_min` (24 steps, 5 nodes) **70.8 µs** ≈ 14 000 eval/s. Pumping adds no measurable
overhead; the cost is in the per-step node loop.

---

## 3. Part 2 — physics and accounting

### 3.1 Water balance closes — exactly

`inst_min`, pump at `a = 1.0` for `t = 0…7`, turbine and hatch shut, zero inflow, so the pump
is the **only** thing moving water in the system.

| Quantity | Worst value over 24 timesteps |
|---|---|
| `\|balance\|` at reservoir_A (target) | **0.000e+00 Mm³** |
| `\|balance\|` at reservoir_B (source) | **0.000e+00 Mm³** |
| `\|A gained − B lost\|` | **0.000e+00 Mm³** |
| `\|total system volume − initial\|` | **0.000e+00 Mm³** |
| `Herss::GlobalWaterBalance` | `start 30.0, inflow 0.0, end 30.0, out 0.0, balance 0.0` |

Per-timestep balance was computed from the model's *own* `tot_inflow`/`tot_outflow`, so this
also confirms that the `pump_in_m3s` / `pump_out_m3s` terms are folded into those totals
correctly. Every step moved `0.007200000 Mm³` (2.0 m³/s × 3600 s), to the digit.

**No losses are modelled anywhere in the pump path.** What leaves the source arrives at the
target exactly. Any real conveyance loss must be modelled outside the pump.

On the shipped fixture (`inst_fixture`, with inflow, hatch, turbine and overflow all active)
the global balance closes to `8.44e-15 Mm³`.

### 3.2 Energy accounting is correct, and the sign is right

Same run. Reference computed independently in Python from the documented formula.

| Quantity | Worst over 24 timesteps |
|---|---|
| `\|MWh_model − MWh_ref\|` | **0.000e+00 MWh** |
| `\|cost_model − cost_ref\|` | **0.000e+00 EUR** |
| `S->income[t]` at a pump | `0.0` at every `t` |

Sample (`t = 0`): `Q = 2.000`, `Hbrutto = Hnetto = 50.007200`, `η = 0.8000`,
`MWh = 1.2260078`, `cost = 61.30039 EUR` at `price = 50.0`.

**Sign and magnitude of the effect on V:**

```
V with pump off                  = 21800.000000 EUR
V with pump on (t = 0..7)        = 21560.238637 EUR
dV                               =  -239.761363 EUR      <- pumping at a positive price LOWERS V
  energy cost charged            =   490.897363 EUR  (9.817947 MWh)
  terminal value of water moved  =   251.136000 EUR  (0.0576 Mm3 x 0.109 kWh/m3 x 40 EUR/MWh)
  residual                       =    -2.66e-11  EUR
```

The decomposition closes to floating-point noise: the *only* two channels through which a pump
changes `V` are its own `S->cost[t]` and the terminal value of the water it relocated. `V` is
monotonically non-increasing in the pump action at a positive price (verified over 21 action
levels, §4.3).

On `inst_fixture` with `PUMP_STARTSTOP = 100`, the start/stop component is also correct: the
shipped pump action sequence `1,1,0,0,1,0,1,0` (against `init_Power = 0.0`) makes 6 transitions,
6 × 50 = **300 EUR**, matching `sum_startstopcost_Euro = 300.000` in the riversystem output file.

### 3.3 Head handling — the one real modelling problem

**The averaging convention is consistent with the power station.** Both use
`(level_start + level_end)/2`, and the pump's version correctly includes the effect of its own
withdrawal/injection on both reservoirs within the step. Head-loss signs are correctly mirrored
(`+k·Q²` vs `−k·Q²`), confirmed numerically on `inst_fixture`:
`Hbrutto = 35.048228`, `Hnetto = 35.248228`, `k = 0.05`, `Q = 2` → `+0.200000`. ✔

**The datum is not consistent.** A pump lifts from the source reservoir's *water surface*; a
turbine drops to a *fixed* `POWSTAT_MASL` regardless of where the receiving reservoir's surface
actually is. Measured on `inst_min` — components multiply to exactly
`0.80 (pump) × 1.00 (motor) × 0.80 (turbine) × 1.00 (gen) = 0.6400` — by pumping one full step
up at `t=0` and releasing the identical volume at `t=1`:

| source reservoir level | H_pump | H_turbine | ratio | MWh in | MWh out | **round-trip η** |
|---|---|---|---|---|---|---|
| 51.0 masl (−4 m vs datum) | 54.0072 | 50.0036 | 0.9259 | 1.32407 | 0.78459 | **0.5926** |
| 53.0 masl (−2 m) | 52.0072 | 50.0036 | 0.9615 | 1.27504 | 0.78459 | **0.6153** |
| **55.0 masl (= `POWSTAT_MASL`)** | 50.0072 | 50.0036 | 0.9999 | 1.22601 | 0.78459 | **0.6400** ✔ |
| 57.0 masl (+2 m) | 48.0072 | 50.0036 | 1.0416 | 1.17697 | 0.78459 | **0.6666** |
| 59.0 masl (+4 m) | 46.0072 | 50.0036 | 1.0869 | 1.12794 | 0.78459 | **0.6956** |

Volume up and volume down were identical (`0.00720000 Mm³` both ways), so this is purely the
head discrepancy. The round-trip efficiency is only the product of the component efficiencies
at the single level where the lower reservoir's surface coincides with `POWSTAT_MASL`; away
from it the model silently gains or loses up to 9 % here, and the error grows with
`(level_source − POWSTAT_MASL) / H`.

**And it can create energy.** Pushed to a legal-but-inconsistent extreme
(`inst_energygen`: source reservoir at 90–100 masl, `POWSTAT_MASL` declared at 55.0):

```
H_pump    = 10.0072 m      MWh in  = 0.245343
H_turbine = 50.0036 m      MWh out = 0.784588
round-trip efficiency = 3.198        <-- ENERGY CREATED
```

HERSS accepts this topology without a single warning. `ValidatePumpSettings`,
`ValidatePowerstationSettings`, `gc.Diagnose()` and `DiagnoseRiversystemConfiguration()` all pass.

**Is this a pump bug?** Strictly, no — the fixed-tailwater convention is pre-existing HERSS
behaviour for power stations, and the pump's own formula is the physically correct one. But
pumped storage is the first mechanism in HERSS that makes the two conventions meet in a closed
loop, so the inconsistency only becomes *reachable* now. It is exactly the kind of thing an
automated topology search would find and exploit.

**Note:** the shipped fixture is itself in the mild version of this regime —
`reservoir_B` has `HRW 75.0` against `POWSTAT_MASL 70.0`, so whenever B sits above 70 masl the
turbine recovers more head than the pump paid for.

### 3.4 Intra-timestep ordering (verified)

Pumping and generating in the same timestep: the pump (idnr 0) runs before the power station
(idnr 2) and before the source reservoir (idnr 3). Confirmed that
`src_start_masl == src_end_masl == 55.0` and `tgt_start_masl == tgt_end_masl == 105.0` when
equal volumes move both ways in one step — i.e. the pump drew from the volume B held at the
**end of the previous step**, and the turbine's tailwater for that step arrived afterwards.
This is a real semantic an optimizer or MILP formulation must reproduce, and it is what the
replica in §6 implements.

---

## 4. Part 3 — determinism and state reset

This is the part that decides whether the thing is an oracle at all. **Everything passes,
bit-for-bit.** Each check compares raw IEEE-754 bit patterns, not tolerances. The
"fingerprint" is a SHA-256 over the bits of 17 per-timestep fields × every node × every
timestep, plus the pump's `actual_pumped_Mm3`, `pump_cost_euro` and `pump_power_MW`.

### 4.1 Determinism — 8 identical runs

```
run 0..7: VF = 44556.73394315452   bits=b95a767c97c1e540   fp=755d85a2b44201d5...
VF bit-identical across 8 runs    : True
full output fingerprint identical : True
```

One distinct bit pattern across all 8 runs.

### 4.2 State reset — A → B → A → B → A in one process

`A` = `inst_fixture` (8 daily steps, pump + turbine + hatch active),
`B` = `inst_min` (24 hourly steps).

```
A (1st) VF = 44556.73394315452   bits=b95a767c97c1e540
B       VF = 21654.389404089616  bits=7521ffeb9825d540
A (2nd) VF = 44556.73394315452   bits=b95a767c97c1e540
B (2nd) VF = 21654.389404089616  bits=7521ffeb9825d540
A (3rd) VF = 44556.73394315452   bits=b95a767c97c1e540

A reproduced exactly after B : True   (value AND full fingerprint)
B reproduced exactly         : True
```

The pump-specific reset hazard was checked explicitly: `pump_in_m3s` / `pump_out_m3s` are
written with `+=` in `Pump::Simulate`, so they would accumulate across runs if not cleared.
They **are** cleared — `Reservoir::InitReservoir` zeroes both arrays (`reservoir.cpp:303–306`)
and `Herss::Simulate` calls `InitReservoir` for every reservoir before the timestep loop.
Over 4 consecutive `Simulate()` calls, `pump_in_m3s[0..7]` was `[2.0]*8` every time. ✔

`Herss::Simulate()` does **not** reset the pump object itself, but it does not need to:
`actual_pumped_Mm3`, `pump_cost_euro` and `pump_power_MW` are fully overwritten at every
timestep, and `src_start_masl`/`src_end_masl`/`tgt_*` are rewritten by the reservoirs each step
before `CalcPowerAndCost` reads them.

### 4.3 Action responsiveness

`inst_min`, probing `t ∈ {0, 5, 11, 23}` × `a ∈ {0.25, 0.5, 0.75, 1.0}`, against the analytic
prediction `ΔV = terminal_gain − cost`:

| a | moved [Mm³] | cost [EUR] | ΔV measured | ΔV predicted | residual |
|---|---|---|---|---|---|
| 0.25 | 0.001800 | 15.3234 | −7.47544 | −7.47544 | −3.5e-12 |
| 0.50 | 0.003600 | 30.6480 | −14.95199 | −14.95199 | +1.9e-12 |
| 0.75 | 0.005400 | 45.9736 | −22.42964 | −22.42964 | −1.9e-12 |
| 1.00 | 0.007200 | 61.3004 | −29.90839 | −29.90839 | −4.3e-12 |

Identical at every probed timestep (as expected: flat price, zero inflow, nothing else running).
Direction and magnitude both correct.

**Return to baseline is exact:** after restoring `a = 0` everywhere,
`V = 21800.0`, `bits = 00000000004ad540`, **bit-identical to the original baseline**.

`V` is non-increasing in the pump action over 21 levels `a = 0.00 … 1.00`: **True**.

### 4.4 Diagnostics

| Instance | `gc.Diagnose()` | `gc.checkNrSteps()` | `rs.DiagnoseRiversystemConfiguration()` | global balance |
|---|---|---|---|---|
| `inst_fixture` | OK | OK | OK | 8.44e-15 Mm³ |
| `inst_min` | OK | OK | OK | 0.00e+00 Mm³ |
| `inst_energygen` | OK | OK | OK | 0.00e+00 Mm³ |

All three run clean on pumping instances, with no warnings in the log file.

Two *harness* hazards were found while doing this, both pre-existing HERSS behaviour rather
than pump-specific, and both capable of wasting a lot of debugging time — see risks **R8**, **R9**.

---

## 5. Edge cases relevant to oracle use

### 5.1 Out-of-range action → process exit

| action | outcome |
|---|---|
| `1.0000005` (inside the `1e-6` tolerance) | survives, clipped to `MAX_DISCHARGE` |
| `1.000002` | **process terminated**, exit 1 |
| `1.5` | **process terminated**, exit 1 |
| `−0.1` | **process terminated**, exit 1 |

`pump.cpp:210` → `LOG_ERR` → `Logger::error` → `std::exit(EXIT_FAILURE)` (`logger.cpp:37–42`).
There is no exception, no return code — the process is gone, and with it an in-process
Python optimizer.

### 5.2 Source runs dry — safe, and correctly priced

`inst_min` with reservoir_B holding only 0.01 Mm³ above `PUMP_INLET_MASL`, pump held at `a = 1.0`:

```
 t  action   pumped_Mm3      B_Mm3        MWh       cost
 0    1.00   0.00720000  10.002800   1.348346   67.41729
 1    1.00   0.00280000  10.000000   0.524452   26.22260     <- clipped to what is there
 2    1.00   0.00000000  10.000000   0.000000    0.00000     <- dry, no cost
 3..5 1.00   0.00000000  10.000000   0.000000    0.00000
```

Correct: the volume is clipped, never negative, the reservoir stops exactly at the inlet level,
and the **cost tracks the actual volume, not the requested one**. A `LOG_WARN` is emitted (log
file only). The action is *not* clipped, so `V` is flat in `a` across that region — a plateau
for any gradient-style search, but physically right.

### 5.3 Start/stop charged for pumping nothing

Same setup on `inst_fixture` (`PUMP_STARTSTOP = 100`), source completely dry:

```
 t  action   pumped_Mm3      MWh      cost  startstop
 0    1.00   0.00000000   0.0000   50.0000      50.00     <- paid to "start" a pump that moved 0 m3
 1..7 1.00   0.00000000   0.0000    0.0000       0.00
```

`Pump::CalcPowerAndCost:300–316` keys off `S->action`, never off `actual_pumped_Mm3`.

### 5.4 The `0.01` commitment threshold

The transition test is `(action > 0.01)`, so an action in `(0, 0.01]` pumps real water and pays
**no** start/stop at all. Measured on `inst_fixture` with an on/off/on/off pattern:

| action | pumped [Mm³] | MWh | start/stop total | cost total |
|---|---|---|---|---|
| 0.0099 | 0.00684288 | 16.917 | **0.00** | 528.61 |
| 0.0100 | 0.00691200 | 16.917 | **0.00** | 528.61 |
| 0.0101 | 0.00698112 | 16.917 | **400.00** | 928.61 |
| 1.0000 | 0.69120000 | 88.894 | 400.00 | 3174.10 |

The loophole is real but **not economically attractive in this fixture**: the shipped efficiency
curve starts at 0 % and reaches only 2 % at `Qn = 0.005`, so pumping at `a = 0.01` costs
≈ 76 500 MWh/Mm³ against ≈ 129 MWh/Mm³ at `a = 1.0` — 16.7× worse per unit of water, far more
than the 400 EUR of avoided commitment cost. **It would be attractive under a flat or
near-flat pump efficiency curve**, which HERSS accepts without complaint (§1.6).
This threshold is the pre-existing power-station convention, not a pump-specific choice.

### 5.5 Pumping into a full reservoir

`inst_min` with both reservoirs at HRW, pump held at `a = 1.0` for 24 steps: every step pumps
`0.007200 Mm³`, is charged ≈ 61.3 EUR, and the water goes straight out over reservoir_A's
overflow curve (total overflow 16.66 m³/s-steps).

```
both reservoirs at HRW, pump OFF   V = 43600.0000
both reservoirs at HRW, pump FULL  V = 42124.5611
dV                                   = -1475.4389 EUR
energy cost charged                  =  1475.4389 EUR
```

`dV` equals the energy cost to the last decimal: **100 % of the pumped water was spilled and
recovered exactly zero value.** No clipping, no warning, no error.

### 5.6 Negative net head → process exit

`inst_invhead` (pump's target below its source), first timestep:

```
ERROR: [ERR] Check your topology file - PUMP node 0 (pump_AB) must lift water
to a higher reservoir. (pump.cpp:280, CalcPowerAndCost)
exit code 1  -- PROCESS TERMINATED
```

Critically this is a **runtime** check inside `CalcPowerAndCost`, not a load-time validation.
A topology whose reservoir ranges overlap will load cleanly, pass all three diagnostics, run
for an arbitrary number of timesteps, and then kill the process the moment the levels cross.

---

## 6. Part 4 — Python replica

Parts 1–3 pass, so the replica was built. `analysis/pump_audit/replica_pump.py` (+
`params_pump.py`, reusing the existing `arraycurve.py` port) implements one full HERSS timestep
for the pump topology class: `RESERVOIR` (curve-based, tunnel outlet, hatch outlet, overflow
curve, LRW penalty, both aggressive-action guards), `PSTATION`, `PUMP` (both phases), `CHANNEL`
(cascade of linear reservoirs), and `CalcVF`'s chain-aware terminal term.

Validated against real HERSS on **24 action sequences** — structured (all-off, full, half,
alternating, pump-and-generate, the shipped fixture's own sequence) and 6 seeded random
sequences per instance, on both `inst_min` (24 hourly steps) and `inst_fixture` (8 daily steps):

| | value |
|---|---|
| sequences compared | 24 |
| **worst \|ΔVF\|** | **7.276e-12 EUR** (tolerance 0.05) |
| **worst per-timestep field discrepancy** | **0.000e+00** |
| verdict | **PASS** |

The per-timestep comparison covers, for every node and every timestep:
`pumped_Mm3`, pump `Power`, pump `cost`, pump `Hbrutto`/`Hnetto`, reservoir `res_Mm3` /
`res_masl` / `overflow_m3s` / `tunnelflow_m3s` / `hatchflow_m3s`, and station `Power` /
`income` / `Hbrutto` / `Hnetto` — all matching to **0.0**, i.e. bit-exact, not merely within
tolerance.

**Pumping is therefore available for exact-DP work on small instances.** The replica's module
docstring records the three things a reimplementation would otherwise get wrong (execution
order, the two-phase power computation, and the head datum).

**Limits of the replica as validated:** single pump, single generator per station,
`UNIFORM_NORMALIZED_CURVE` only, reservoir *curves* (not `RESERVOIR_GEOMETRY`), no
`OUTLET_AUTO_QMIN` / `AUTO_QMIN` / `MAX_ADJUST` / channel `QMIN` / `FAST_OVERFLOW` /
`USE_SPILLWAY`. It raises rather than silently diverging where HERSS would `LOG_ERR`.

---

## 7. Research risks

Ordered by how much damage they can do to a river-system design study.

**R1 — Pump and turbine use different head data; round-trip efficiency is not a system
constant.** Measured drift 0.5926 → 0.6956 on a system whose components multiply to 0.6400;
a legal topology reached **3.198 (net energy creation)**. Neither load-time validation nor
any of the three diagnostics catches it. *Mitigation:* constrain every generated topology so
that for each pump, the receiving station's `POWSTAT_MASL` equals the source reservoir's
level datum — in practice `POWSTAT_MASL ≤ LRW(source reservoir)` and ideally
`POWSTAT_MASL = LRW(source)`; and report the empirical round-trip efficiency for every
instance as an instance statistic. Note the shipped fixture violates this
(`HRW(reservoir_B) = 75 > POWSTAT_MASL = 70`).

**R2 — Negative net head terminates the process at runtime.** A topology can load, pass all
diagnostics, and die at timestep *n*. *Mitigation:* require `HRW(source) < LRW(target)` for
every pump at instance-generation time. Neither HERSS nor the manual states this rule.

**R3 — Out-of-range actions terminate the process.** `a ∉ [−1e-6, 1+1e-6]` → `std::exit`.
*Mitigation:* clamp every action before calling `SetAction`, and run the oracle behind a
subprocess boundary if any search can emit unclamped values.

**R4 — `LOG_ERR` is `std::exit` everywhere, not an exception.** This is HERSS-wide, but the
pump adds three new call sites reachable from ordinary search behaviour (§5.1, §5.6, plus
`η_pump ≤ 0` with `Q > 1e-6`, reachable with a pump curve that is zero over a low-flow range).

**R5 — Pumping is not bounded by the target reservoir's capacity.** Water pumped into a full
reservoir is paid for and immediately spilled at zero value. Unbounded, silent value sink.

**R6 — Start/stop is charged on the action, not on actual flow.** A pump whose source is below
`PUMP_INLET_MASL` still pays a start cost for moving 0.0 Mm³ (§5.3).

**R7 — The `a > 0.01` commitment threshold is a commitment-cost loophole.** Harmless under the
shipped efficiency curve, potentially free start/stop avoidance under a flat one, which HERSS
accepts because the uniform pump curve bypasses `ArrayCurve` validation (§5.4, §1.6).

**R8 — `gc.Diagnose()` is not idempotent.** `TopologyParser::loadFile` (`topoparser.cpp:30–47`)
does `lines.push_back(...)` **without clearing `lines` first**. A second `Diagnose()` on the
same `GlobalConfig` parses the topology twice and doubles every node count — this audit's first
harness hit `nr_reservoirs = 4` on a 2-reservoir system. Pre-existing, HERSS-wide.

**R9 — `Simulate()` segfaults if `DiagnoseRiversystemConfiguration()` was never called**, on any
topology containing a `CHANNEL`. `Channel::casc_reservoirs` is allocated **only** inside
`Channel::ValidateChannelSettings` (`channel.cpp:53–59`), which is reached only from
`Riversystem::DiagnoseRiversystemConfiguration`. Skip it and `Channel::SetStartState`
(`channel.cpp:340`) dereferences a null pointer. Pre-existing, HERSS-wide, and undocumented:
the diagnostics are not optional, they are part of initialisation.

**R10 — Input files are parsed at `float32` precision.** `dataset.cpp:223, 305, 348, 378` use
`stof`, not `stod`, for actions, inflows, prices and `restprice`, storing into `double`. A
run driven from `actions.txt` and an "identical" run driven through `SetAction` give
*different* value functions: on `inst_fixture`, `44556.73394256545` (file, hatch action
`0.30000001192092896`) vs `44556.73394315452` (API, `0.3`), a difference of `5.89e-07 EUR`.
Tiny here; systematic, and it will be larger on longer horizons. Pre-existing, HERSS-wide.
*Mitigation:* drive everything through the API, or round to float32 before comparing.

**R11 — the shipped regression baseline is broken, though not by the pump.** `make test` cannot
run at all (`GTEST_DIR = /usr/src/gtest` is hardcoded and absent); built against miniconda's
gtest 1.11 instead, `Pump*` passes **26/26**, but `test_channel.cpp` no longer compiles,
`ArrayCurveTest.X2YReturnsErrorOnOutOfBoundsInput` fails, and five suites abort on the stale
`src_tests/utahps_test/` fixture (§2.1). Consequence for this thesis: there is currently **no
usable green baseline** to diff future HERSS upgrades against, and `LOG_ERR`'s `std::exit`
means one broken fixture takes the entire test binary with it. Worth raising with the HERSS
lead developer; do not fix it here.

**R12 — `PUMP_CURVE` (the non-uniform efficiency curve) is untested.** Parsed at
`pump.cpp:557–583`, used by neither fixture, missing from the manual's syntax block, and not
exercised here. Do not use it without testing it first.

**R13 — Multiple pumps, and pumps sharing a reservoir, are untested.** The accumulator design
(`pump_in_m3s += / pump_out_m3s +=`) suggests it is intended to work, and each pump has its own
action column keyed by idnr, but no fixture exercises it and this audit did not.

**R14 — Fixture drift.** `data/mini_pump_test/` and `src_tests/pump_test/` have diverged in
numbering, `PUMP_INLET_MASL` and `SHARED_PENSTOCK` despite a comment claiming they are kept in
sync; `data/mini_pump_test/global.txt`'s header describes the other one's topology. Also note
CLAUDE.md §5: `data/*` is gitignored, so new instances placed there are silently untracked —
which is why everything in this audit lives under `analysis/`.

### Open questions

- Is the fixed-tailwater convention (`POWSTAT_MASL`) intended to be used with pumped storage at
  all, or should a power station discharging into a reservoir take that reservoir's level? This
  is a question for the HERSS lead developer, not something to resolve by changing `src/`.
- Should `PUMP_INLET_MASL` clipping also clip the *action*, so that `V` is not flat in `a`
  across the dry region? Current behaviour is physically right but creates search plateaus.
- Is a pump expected to be blocked by the target reservoir's capacity, or is unbounded
  pump-then-spill the intended semantics?
- Should the numbering requirement `pump.idnr < source.idnr, target.idnr` be accompanied by an
  elevation requirement `HRW(source) < LRW(target)`, enforced in `ValidatePumpSettings`?

---

## 8. Reproducing this

```bash
cd src && make                      # herss.exe + herss.so, HERSS 4.0.00 / 20260814
cd ../analysis/pump_audit
../../.venv/bin/python part2_physics.py       # water balance + energy accounting
../../.venv/bin/python part2_head.py          # head convention + round trip
../../.venv/bin/python part3_determinism.py   # determinism, reset, responsiveness, diagnostics
../../.venv/bin/python part4_edge.py          # edge cases (spawns subprocesses that exit)
../../.venv/bin/python part5_replica.py       # replica validation
```

Each writes a `part*_results.json` alongside itself. Nothing under `src/` or `data/` is touched.

To rebuild and run the shipped gtest suite without `/usr/src/gtest`, see §2.1 — build the
objects into a scratch directory, link against `$CONDA_PREFIX/lib/libgtest.so`, and run the
binary with cwd = `src/`.
