
# CLAUDE.md — herss-exploration

Instructions and context for any AI assistant working in this repository.

**Repository:** `AnSloge/herss-exploration` — a copy of upstream `berntmath/herss`
**Pinned upstream state:** `029a2d5298bddff55740c33a5971343df74824b7` (53 commits, all authored by Bernt Viggo Matheussen and Terje Sandø; no commits by the repository owner as of this file being written)
**Simulator:** HERSS — Hydraulic Economic River System Simulator, C++, MIT licensed, owned by Å Energi
**Manual:** `doc/herss.pdf`

---

## 1. What this repository is for

This is an **exploration repository for a master's thesis in optimization / Operations Research.** It is not a hydrology project, not a simulator-development project, and not a machine learning project.

HERSS is treated strictly as a **simulation and evaluation engine** — a black-box oracle that maps an action sequence to a scalar objective value. The academic contribution must come from:

- the optimization problem formulation
- decision variables, objective, and the classification of constraints as hard / soft / simulator-imposed
- algorithm design, including problem-specific components
- benchmark and instance design
- experimental analysis of solution quality, robustness, scalability, and limitations

If work in this repository starts drifting toward hydraulic modelling, hydrological calibration, or improving HERSS itself, that is a scope failure and should be flagged immediately.

## 2. Thesis framing (current working version — not yet final)

**Working title:** Simulator-based short-term hydropower scheduling — the cost of linearisation, and a matheuristic for closing the gap.

**Main research question:** How much economic value is lost when a linearised MILP model for short-term hydropower scheduling is evaluated in a non-linear simulator, and can a matheuristic with the simulator in the loop recover that loss within a realistic evaluation budget?

**Why this question and not "optimize an instance":** "Get an instance, write an algorithm, report good numbers" is a project, not a contribution. It lacks a reference point, a formulation that belongs to the author, and a question whose answer is unknown in advance. The linearisation gap is a *measurable quantity* — it is a result regardless of how well any algorithm performs.

**Sub-questions:**

1. **Formulation.** Which MILP formulation of the operating problem *as HERSS defines it* is tight enough to be useful, and which mechanisms cannot be represented? Channel routing through cascaded linear reservoirs is linear and MILP-friendly; start/stop introduces commitment binaries; head-dependent production and the aggressive-action discontinuity are what resist linearisation.
2. **Reference.** On single-reservoir instances, what does exact dynamic programming yield against the simulator, and what is the resulting empirical linearisation error?
3. **Algorithm.** Can a problem-specific scheme — successive linearisation over head, a repair operator for aggressive actions, fix-and-optimize on commitment variables — close the gap, and at what evaluation cost?
4. **Baselines.** How does it compare against a tuned price-threshold policy, against the `actions.txt` files shipped with the datasets, and against direct search in a reduced action space under an equal evaluation budget?
5. **Scaling and robustness.** How does performance vary with system size (`res_casc_A–D` → mini uTAHPS → full uTAHPS), horizon length, and choice of inflow/price window? Do results hold under rolling horizon with forecast error?

**Methodological caveat that must be stated correctly:** MILP optimum bounds the *linearised* model, not the true optimum. Any simulator-feasible solution is a lower bound on the true optimum. Squeezing the true optimum between them requires bounding the linearisation error, which cannot be done rigorously in general. It can be measured empirically with DP on small instances. State this precisely; imprecision here is the obvious point of attack.

## 3. Scope boundaries

**In scope:** optimization model formulation; a thin Python harness around HERSS; exact DP on small instances; MILP/LP planner; problem-specific heuristics and matheuristics; instance and benchmark design; controlled experiments; statistical reporting.

**Out of scope:** hydrological modelling or calibration; modifying HERSS physics; stochastic programming and scenario trees; ML surrogate models; software engineering work on HERSS beyond what is strictly required to call it.

## 4. Working rules for the assistant

- Be critical and precise. Do not agree with a proposal to be supportive. Do not present an idea as strong without explaining exactly why.
- Always distinguish **fact** (verified in source or documentation), **assumption**, **interpretation**, and **speculation**. Label them.
- Do not express more confidence than the evidence supports.
- Challenge the problem formulation, not only the proposed solution.
- Be sceptical of weak contributions, especially "compare several off-the-shelf metaheuristics."
- Before proposing a metaheuristic, answer: could a simpler exact, LP/MILP, DP, greedy, or local-search method solve this adequately?
- Treat bugs, undocumented behaviour, and incomplete features as **research risks**, not inconveniences.
- Do not refactor, rewrite, delete, or restructure files without an explicit stated reason and owner approval.
- Prefer reproducible, minimal, well-documented steps over large changes.
- Keep simulator validation separate from optimization development, in separate directories and separate commits.

## 5. Repository hygiene

**Do not modify `src/`.** It is upstream C++. Any change there makes results non-comparable with the pinned upstream state and destroys the ability to state which HERSS version a result refers to. If a change appears necessary, stop and raise it.

**Upstream separation.** The long-term structure should keep upstream HERSS pinned (submodule or recorded commit) and place all thesis code in a separate tree that only *calls* the simulator. HERSS is under active development; upstream changes must be adopted deliberately, never absorbed silently.

**`.gitignore` trap — highest-priority hygiene issue.** Line 26 is `data/*`. 173 files under `data/` are nonetheless tracked, because they were added before the rule existed. Consequences:

- Existing datasets are version controlled.
- **Any new instance or generated dataset placed under `data/` is silently untracked.** This is a direct reproducibility hazard for a thesis.
- Output files under `data/*/output/` *are* tracked, so every simulation run dirties the working tree and invites committing noise or discarding needed files.

Therefore: place all generated instances and all experiment results **outside `data/`**, under an explicitly configured path, and decide deliberately whether the shipped output files should be untracked.

**Version stamping.** Record the upstream commit hash and log `cppyy.gbl.VERSION` and `VERSION_DATE` in every experiment run. These variables exist and are already used for log filenames.

## 6. The evaluation oracle (verified in source)

Python access is via cppyy: `cppyy.load_library("../src/herss.so")` then `cppyy.include("../src/herss.h")`.

Relevant interface: `SetAction(node, gen, t, value)`, `GetAction`, `SetPrice(t, price, restprice)`, `SetInflowInNode(t, node, q)`, `SetReservoir_Init_fr(node, fr)`, `GetReservoirLevel_fr(node, t)`, `Simulate()`, `rs.CalcVF(restprice)`.

Decision variables: one action \(a \in [0,1]\) per generator per time step, plus one per active reservoir hatch. Discharge is \(Q = a \cdot Q_{\max}\).

Validation hooks worth using, given weak topology validation upstream: `gc.Diagnose()`, `gc.checkNrSteps()`, `herss.rs.DiagnoseRiversystemConfiguration()`.

The manual states that `Simulate()` reinitialises reservoir state internally on every call. **This is documentation, not verified behaviour — it must be tested (see §10).**

## 7. Verified source findings and their implications

**Objective function** (`src/riversystem.cpp:436, 474, 476`):

```
V = tot_profit_Euro + restprice * SUM over PSTATION nodes of
    ( local_energy_equivalent[n] * upstream_remaining_active_Mm3[n] * 1000 )
```

- The terminal term **is cascade-aware**: it sums over power stations, so water upstream of several stations is valued once per downstream station. This is correct in principle.
- Only *active* storage counts (LRW→HRW). Water above HRW is valued at zero — a correct incentive to avoid spill, but the objective is non-differentiable at HRW.
- `local_energy_equivalent` is a **constant read from the topology file** (`LOCAL_ENERGY_EQUIVALENT`, parsed at `src/powerstation.cpp:407`), in kWh/m³. It is *not* derived from actual head. In-horizon production uses head-dependent physics. **The terminal term and the in-horizon term therefore use inconsistent conversions**, producing a systematic bias whose sign depends on whether terminal levels sit above or below the level the constant was calibrated at. This must be stated explicitly in the thesis as a model limitation.
- The marginal value of water is **constant** — the terminal term is linear in terminal storage.

**The constant marginal water value is the central threat to the thesis.** With a constant marginal water value, a single deterministic price series, and perfect foresight, the optimum lies structurally close to a threshold rule: produce at the efficiency-optimal point when \(p_t \cdot e_n\) exceeds the opportunity cost of water, store otherwise. Everything that makes this a *hard* optimization problem is a perturbation of that rule: head dependence, non-concave efficiency curves, start/stop costs, volume and capacity limits, spill avoidance, and cascade coupling through routing delay. This is why §10, item 6 is the go/no-go measurement for the entire thesis.

**Aggressive-action penalty** (`src/powerstation.cpp:785–791`):

```cpp
if (Q_Mm3 > up_res_Mm3) {
    aggressive_actions_cost = (Q_Mm3 - up_res_Mm3) * HERSS_AGGRESSIVE_ACTIONS_COST;
    flow = 0.0;
}
```

with `HERSS_AGGRESSIVE_ACTIONS_COST 1000` (`src/herss.h:99`).

- The penalty *is* proportional to violation depth — better than the manual implies. The manual's claim that it provides "a strong gradient signal" is nonetheless misleading, because `flow = 0.0` puts a **step discontinuity** in the production term.
- The source comment states the intent plainly: "a minor penalty ... just so we dont get the same value in VF." It is designed to break plateaus in the value function, **not to enforce feasibility.** Whether 1000 EUR per Mm³ of overdraw exceeds the revenue obtainable by violating at high prices is an open question and must be computed (§8).
- Implication: a repair operator that clips actions to available volume dominates reliance on the penalty, and is a defensible problem-specific algorithmic contribution.

**Duplicated value-function computation.** `Riversystem::WriteRiverSystemData` (`src/riversystem.cpp:533`) **recomputes and overwrites** `valuefunction_Euro` at lines 576, 591, 593, duplicating the logic in `CalcVF`. Consequences: writing output has a side effect on object state, and if the two implementations ever drift, the value read depends on call order. Always read the value returned by `CalcVF()` directly; never rely on the member variable after an output write.

**`CalcVF_atEndOfStp`** (`src/riversystem.cpp:346`) returns `VF0 - profit_up_to_stp`, i.e. value-to-go under the realised action sequence. Potentially useful as a terminal valuation in rolling horizon, but note it requires a completed full-horizon simulation first, so it is **ex post** and not usable as a value-to-go estimator during optimization.

**Existing test suite.** `src_tests/` contains gtest tests including `test_valuefunction.cpp`, `test_waterbalance.cpp`, `test_riversystem.cpp`, `test_powerstation.cpp`, `test_channel.cpp`, `test_reservoir.cpp`, `test_runtime.cpp`. Run `make test` in `src/` before writing any new code — it is the fastest check that the baseline is intact, and the result is citable in the methods chapter.

**Runtime, partly answered upstream.** `src_tests/test_runtime.cpp` measures *full program* wall-clock time (process start, config read, dataset load, simulation, output writing, teardown) for the uTAHPS test config and asserts an average under 0.75 s. Note that the test *name* says `Under350ms` while the constant is `0.75` — a minor quality signal worth recording. Budget arithmetic: at 20 ms per evaluation, ~50 evaluations/second, ~2 million per day single-threaded. Against \(10^4\)–\(10^5\) decision variables that is nothing; against a reduced parameterisation of 50–500 parameters it is ample. **Decision-space reduction is therefore a precondition, not a later refinement.**

**Datasets on disk exceed what the manual documents:** `mini_utahps_daily`, `mini_utahps_hourly`, `mini_utahps_new_inputformat`, `mini_utahps_spillway`, `res_casc_A`, `res_casc_B`, `res_casc_C`, `res_casc_D`, `utahps_daily`, `utahps_daily_new_format`, `utahps_hourly`, `utahps_multires`. The `new_format` / `new_inputformat` names suggest an in-progress input-format migration. **Clarify with the HERSS lead developer which format is canonical before building tooling against either one.**

## 8. Open verification items, in priority order

1. Does `Simulate()` genuinely reset all state? (Determinism and A→B→A tests — see §10.)
2. Is `HERSS_AGGRESSIVE_ACTIONS_COST = 1000` large enough that an optimizer cannot profit from violating? Compute the implied EUR/Mm³ against realistic `price × local_energy_equivalent`.
3. Does `upstream_remaining_active_Mm3` accumulate correctly through the DAG — no double counting on branches, no omitted tributaries?
4. Do `CalcVF` and the duplicate logic in `WriteRiverSystemData` agree numerically on all shipped datasets?
5. Does the global water balance close to zero on every shipped dataset?
6. Is in-process `Simulate()` cost dominated by computation or by file I/O? Measure with `WRITE_NODEFILES` and the `PRINT_*` flags both on and off.

## 9. HERSS features that must not be used

Per `doc/herss.pdf` Chapter 5, these are unimplemented or not quality controlled. Treat them as unavailable, not as "nice to have":

- `MAX_ADJUST` — implemented, not quality controlled
- Channel `QMIN` — partially implemented; time-period parsing incomplete
- `FLOODLEVEL_PENALTY` — read from the topology file but never applied in simulation
- `OUTLET_AUTO_QMIN` — partially implemented, no validating test dataset
- Variable timestep **combined with** start/stop or adjustment costs — those calculations still assume a fixed hourly step. **This eliminates "different temporal resolutions" as an experiment axis whenever start/stop costs are in the model** — and start/stop costs are the main source of discrete structure.
- Multi-generator start/end state — not implemented; all generators are forced to the same state. Directly relevant to rolling horizon at horizon boundaries.

## 10. Gating measurements before committing to a final formulation

Run in order. Record all results in a dated log.

1. `make` in `src/`. Verify both `herss.exe` and `herss.so` are produced.
2. `make test`. Record what passes, fails, and is skipped.
3. Command-line run on `data/mini_utahps_hourly`. Read the log file, not just the terminal. Verify the water balance closes in `riversystem_*_output.txt`.
4. `pip install cppyy`; run `py_src/pyherss.py` block by block. Note that its paths are relative to `py_src/`.
5. **Determinism and reset.** Call `Simulate()` twice with identical actions; assert bit-identical `CalcVF`. Then A → B → A; assert the value for A is reproduced exactly. Then measure per-call wall-clock time with output writing on and off. *If reset leaks state, everything downstream is invalid.*
6. **The decisive test.** Write a single-reservoir instance, solve it by exact DP over discretised storage and actions (with the on/off state as one extra dimension for start/stop cost), and compare against a tuned price-threshold policy.
   - Gap below ~1 %: the formulation is **not yet a thesis.** Binding structure must be added — terminal storage constraint, ramping limits, multi-generator commitment — before committing.
   - Gap above ~3 %: there is a problem worth solving.

Also verify early that a stale `herss.so` cannot silently mismatch the included `herss.h`; add a version assertion to the harness.

## 11. Experiment standards

- Fixed random seeds, recorded per run.
- Equal evaluation budgets when comparing methods — never equal wall-clock time alone.
- Report objective value **and a separate feasibility table.** Almost every constraint in HERSS is penalised rather than enforced, so a method can win by buying violations cheaply. Reporting profit without violations would be a methodological flaw.
- State explicitly which constraints are treated as hard (enforced by repair in search operators) and which as soft.
- Report the number of simulator evaluations alongside every result.
- Every result must record: upstream commit hash, HERSS `VERSION`/`VERSION_DATE`, dataset, horizon, seed, and configuration flags.

## 12. Notation

| Symbol | Meaning |
|---|---|
| \(a_{n,g,t}\) | action for generator \(g\) at node \(n\), time \(t\); \(a \in [0,1]\) |
| \(Q\) | discharge [m³/s], \(Q = a \cdot Q_{\max}\) |
| \(e_n\) | `local_energy_equivalent` at station \(n\) [kWh/m³], constant from topology |
| \(V\) | value function [EUR] = total profit + value of remaining water |
| LRW / HRW | lowest / highest regulated water level |
| `restprice` | scalar end-of-horizon water value [currency/MWh] |
| \(T\) | number of time steps, determined by the row count of the price file |