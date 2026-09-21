# R1 fix prototype: how hard is tailwater tracking?

**Status:** throwaway prototype on branch `r1-fix-prototype`. **Not for merging. Not production-ready.**
The goal is to measure how large, how risky and how self-contained the root-cause fix for R1
(`R1_LOOP_REPORT.md`) is. Whether to adopt it, and who owns it, is for a human to decide with
the HERSS lead developer.

| | |
|---|---|
| Base commit | `b6962f1e9ae89c99c2f0d82e12277a14d21a2773` (branch `system-design`) |
| HERSS version | `4.0.00` / `20260814` (unchanged by the prototype) |
| Date | 2026-09-19 |
| Scripts | `fix_fullprec.py` (full-precision regression fingerprint), `fix_r1_verify.py` (R1, determinism, isolation) |
| Results | `fix_r1_results.json` |

Labels as in CLAUDE.md §4: **[fact]** = measured or read in source; **[interp]** = interpretation;
**[open]** = needs a decision from the lead developer.

**CLAUDE.md §5 note.** This branch modifies `src/`, which CLAUDE.md forbids for thesis work. The
repository owner authorised it explicitly, and only on this isolated branch. No result in this
report may be mixed with thesis results computed on the pinned upstream build.

---

## 1. Where the change has to go (Part 1)

**[fact] The head calculation.** It is a single line, `powerstation.cpp:167` (base numbering), in
`Powerstation::Simulate(size_t t)`:

```cpp
Hbrutto = ((this->start_of_stp_masl + this->end_of_stp_masl)/2.0 ) - this->powstat_masl;
```

`Hbrutto` feeds `Hnetto`, then power, then income and profit, all inside the same function.

**[fact] How the station learns the intake level.** The *upstream* reservoir pushes it.
`Reservoir::Simulate` writes `ptr_downstream_node_tunnel->start_of_stp_masl` (`reservoir.cpp:521`)
and `->end_of_stp_masl` (`reservoir.cpp:706`), clipped at HRW. This works because
`Herss::Simulate` runs nodes in **ascending idnr** order (`herss.cpp:729-745`). The intake
reservoir has a lower idnr than its station, so it has already finished timestep `t` when the
station runs.

**[fact] The downstream level is not available when the head is computed. This is the finding
that decides how big the change is.** A station's downstream reservoir must have a *higher* idnr.
Otherwise the station's `ptr_downstream_node->S->up_inflow[t] += total_Q` would land after that
reservoir had already consumed its inflow. So when `Powerstation::Simulate(t)` runs:

- the tailwater reservoir's `res_masl` still holds the level at the **end of `t-1`** (= start of `t`);
- its **end-of-`t`** level does not exist yet. It depends on this station's own discharge in step
  `t`, which is being computed right now.

The `(start + end)/2` convention therefore **cannot** be applied inside `Powerstation::Simulate`.
Some plumbing is required. HERSS already contains the pattern: the PUMP hits the same problem and
defers its head, power and cost to `Pump::CalcPowerAndCost(t)`, called after all nodes have run
(`herss.cpp:747-752`). The reservoirs push start and end levels into it through the reverse lists
`ptr_pumps_as_source/target` (`reservoir.cpp:508-509, 714-715`). The prototype copies that pattern.

## 2. What was implemented (Part 2)

Opt-in topology keyword, placed inside a `NODE PSTATION` block:

```
TAILWATER_IDNR <reservoir_idnr>     # absent or negative -> fixed POWSTAT_MASL, as before
```

**Mechanism.**
1. The tailwater reservoir pushes its start and end `res_masl` into the station. This is the same
   code path and the same timing as for pumps, and the levels are **not** clipped at HRW, the same
   as the pump.
2. `Powerstation::Simulate(t)` runs as today in the node loop. The flows, the routing to
   `DOWNLINK_IDNR` and the aggressive-action rule are unchanged. For an opted-in station the head
   used there is provisional: exactly today's fixed-datum value.
3. After the pump pass, `Herss::Simulate` **re-runs `Powerstation::Simulate(t)`** for opted-in
   stations only, with `tailwater_final_pass = true`. This time the tailwater is
   `(tw_start + tw_end)/2`, so head, power, income and profit are recomputed. The downstream push
   is guarded, so no water is routed twice.

**Why re-run the function instead of extracting the generator loop into a helper.** Re-running
leaves the ~75-line penstock and generator loop byte-for-byte untouched. That is the smallest diff,
and nothing in the default path moves. The cost is duplicated log warnings and extra runtime for
opted-in stations (§5). A version for production should probably split `Simulate` into a flow phase
and an energy phase, like `Pump`. That is a refactor, and the owner should make that call.

### Every file and line touched

| File | Hunk (new-file lines) | Change |
|---|---|---|
| `src/herss.h` | 173 | forward declaration `class Powerstation;` |
| `src/herss.h` | 695-696 | `Reservoir::ptr_stations_as_tailwater` (reverse list, like `ptr_pumps_as_*`) |
| `src/herss.h` | 808-815 | `Powerstation`: `tailwater_idnr`, `tailwater_in_use`, `tailwater_final_pass`, `tw_start_masl`, `tw_end_masl` |
| `src/powerstation.cpp` | 25-30 | constructor: initialise the 5 new members (`in_use = false`) |
| `src/powerstation.cpp` | 172-179 | head line: `tailwater_masl = powstat_masl`, replaced by the tracked average only when `in_use && final_pass` |
| `src/powerstation.cpp` | 294-295 | downstream push guarded with `&& !tailwater_final_pass` |
| `src/powerstation.cpp` | 429-437 | parser: `TAILWATER_IDNR` (negative = not in use) |
| `src/reservoir.cpp` | 508 | push `tw_start_masl` (next to the pump start push) |
| `src/reservoir.cpp` | 718 | push `tw_end_masl` (next to the pump end push) |
| `src/herss.cpp` | 413-424 | `SetPointers`: validate that the target is a RESERVOIR (`LOG_ERR` otherwise) and register the station |
| `src/herss.cpp` | 765-774 | `Simulate`: end-of-timestep re-run for opted-in stations |

**Total: 4 files, +62 / −5 lines.** About 20 of those are comments.

### Ordering and timing: what the lead developer needs to sign off **[open]**

1. **Deferred energy accounting.** For an opted-in station, head, power, income and profit for step
   `t` are final only *after all nodes and pumps* have run step `t`. Nothing reads them inside the
   node loop today; `CalcVF` runs after `Simulate`. **[fact, checked by grep]** Any future code that
   reads a station's `S->profit[t]` or `S->Power[t]` mid-timestep would see the provisional
   fixed-datum value. *Question:* is end-of-step station accounting acceptable, as it already is
   for pumps?
2. **The tailwater end level includes the station's own discharge.** The tailwater reservoir's end
   level for `t` already contains the water this station released in `t`. This is the same
   convention the pump uses for its target. It is what makes the pump pass and the turbine pass
   average *the same four surface values*, which is why R1 disappears (§4). *Question:* is this the
   intended physics, or should the tailwater be the start level only (an explicit lag, no
   re-run needed, but it does not close R1 exactly)?
3. **HRW clipping is asymmetric.** HERSS clips the station *intake* at HRW ("should never pay off
   to flood", `reservoir.cpp:523`). The pump does not clip, and the prototype tailwater does not
   clip either. Measured effect: only when U starts at `U_fr = 1.0`, the tracked `eta_rt` falls
   `0.5-5e-5` *below* `eta_prod`. That is conservative. *Question:* should the tailwater be clipped
   too?
4. **A tailwater below the turbine centreline.** Tracking gives *more* head than the fixed datum
   whenever the tailwater sits below `POWSTAT_MASL`. Measured on Fabelvassdraget DYPFALL:
   `H_turb` 186.7 → 193.7 m at `L_fr = 0`. That is right for reaction turbines (Francis/Kaplan,
   where the draft tube recovers head down to the tailwater). It is wrong for impulse turbines
   (Pelton), which cannot use head below the runner. `max(POWSTAT_MASL, tailwater)` would cover
   both, and it still bounds `eta_rt` by `eta_prod`, because the turbine head then never exceeds
   the pump head. *Question:* which one does HERSS intend?
5. **Terminal value is untouched.** `LOCAL_ENERGY_EQUIVALENT` is still a constant (CLAUDE.md §7).
   Tracking makes the in-horizon head more level-dependent, so the terminal-vs-in-horizon
   inconsistency changes. It is not removed. **[interp]**

## 3. Regression: existing behaviour unchanged (Part 3.1)

| Check | Result |
|---|---|
| CLI `herss.exe global.txt`, all 12 `data/*` datasets, base vs prototype binary, all output files byte-compared | **12/12 identical** (0 diff lines, stdout identical) |
| Full precision, in process: `repr(CalcVF)` + FNV-1a hash over the raw bytes of 32 per-timestep `Scenario` arrays of every node, base `.so` vs prototype `.so` | **12/12 bit-for-bit identical** |
| gtest, base vs prototype (built against conda gtest 1.11, one suite at a time) | **identical**: Pump 26/26, Line 26/26, GlobalConfig 10/10, Riversystem 6/6, ArrayCurve 5 pass + 1 fail, Dataset/Reservoir/Powerstation/ValueFunction/WaterBalance abort. Same as the known baseline (memory `herss-gtest-baseline`); none of it caused by this change |
| `TAILWATER_IDNR -9` on every station vs keyword absent (fabelvassdraget, same random actions) | **bit-for-bit identical** |
| `TAILWATER_IDNR` pointing at a CHANNEL | stops at load: exit 1, `Please check TAILWATER_IDNR in the topology file. (herss.cpp:420, SetPointers)` |

Notes: the text outputs round to a few decimals, so the full-precision check is the one that
counts. The two `src_tests/*/global.txt` fixtures fail identically on both builds from the CLI
(pre-existing relative-path issue). The gtest link must exclude `src/routing.cpp`, which the
Makefile does not build. It opens `inflow.txt` at static-init time and kills the test binary.
This is a new pre-existing trap.

**[interp] Is the isolation watertight?** Yes, by construction and by measurement. With the keyword
absent, `tailwater_in_use` is false, the head line subtracts `powstat_masl` exactly as before (same
operation, same operand), the reverse list stays empty, and the re-run loop skips every station.
The one path not exercised is an existing topology that *already* contains a line starting with
`TAILWATER_IDNR`. No shipped dataset does (grep).

## 4. R1 is fixed when opted in (Part 3.2)

Protocol as in R1 parts 2-5: pump a volume L→U at t=0, release the identical volume U→L at t=1,
everything else shut. `eta_rt = E_out/E_in` from HERSS's own `S->Power`. Only volume-matched cells
count. Before and after use the same prototype build, which is identical to the base build without
the keyword (§3). **[fact] The "fixed" column reproduces the recorded part-2 and part-3 values
exactly (max |Δeta_rt| = 0.0).**

### Synthetic loops: worst over a 12 × 11 grid of (U_fr, L_fr), 121 matched cells each

| Geometry (P = POWSTAT_MASL) | eta_prod | fixed-datum max | **tailwater max** | tailwater min |
|---|---|---|---|---|
| part-2 inst_loop, P = LRW(L) | 0.64000 | 0.7992 | **0.640000** | 0.639977 |
| part-2 deep tailrace, P below L | 0.64000 | 0.8788 | **0.640000** | 0.639977 |
| part-3 D = 30, R_L = 30 | 0.79521 | **1.5797** | **0.795211** | 0.795154 |
| high-head PSH | 0.79521 | 0.8186 | **0.795211** | 0.795207 |
| medium-head PSH | 0.79521 | 0.8834 | **0.795211** | 0.795202 |
| two lakes, deep drawdown | 0.79521 | **2.3386** | **0.795211** | 0.795154 |
| two lakes, small gap | 0.79521 | **6.4675** | **0.795211** | 0.795129 |

**[fact]** With tracking, `eta_rt` equals `eta_prod` at every level. It is never above it by more
than 1 ulp (in 3 geometries `0.7952112000000001` vs `0.7952112`, which is float rounding). The only
cells below `eta_prod` are the `U_fr = 1.0` row: the HRW-clip asymmetry, §2 item 3. **[interp]**
This is exactly what the mechanism predicts. The pump at t=0 and the turbine at t=1 average the
same four surface values `{U0, U0+ΔU}` and `{L0, L0−ΔL}`. So `H_turb = H_pump` in any geometry,
and the geometric amplifier `(U−P)/(U−L)` from R1 is identically 1.

Before and after along L's range (part-2 instance, U at fr 0.5):

| L_fr | 0.0 | 0.2 | 0.4 | 0.6 | 0.8 | 1.0 |
|---|---|---|---|---|---|---|
| H_turb fixed [m] | 110.00 | 110.00 | 110.00 | 110.00 | 110.00 | 110.00 |
| H_turb tailwater [m] | 110.01 | 106.01 | 102.01 | 98.01 | 94.01 | 90.01 |
| eta_rt fixed | 0.6400 | 0.6641 | 0.6902 | 0.7183 | 0.7489 | 0.7822 |
| **eta_rt tailwater** | **0.6400** | **0.6400** | **0.6400** | **0.6400** | **0.6400** | **0.6400** |

### Shipped pump fixture (`src_tests/pump_test`), eta_prod (peak) 0.6392

| POWSTAT_MASL | fixed max | tailwater max / min |
|---|---|---|
| 70.0 (as shipped) | 0.7425 (already above eta_prod) | 0.6299 / 0.6252 |
| 60.0 (= LRW(B)) | 0.9826 | 0.6299 / 0.6252 |

With tracking, the result no longer depends on `POWSTAT_MASL` at all, as expected.

### Fabelvassdraget (verbatim copy; TAILWATER_IDNR on TORDENFOSS→KLARVIK, HEIMFOSS→TROLLDAMMEN, DYPFALL→SALTVIKA)

Grid: a_pump ∈ {0.2,…,0.8} × U_fr ∈ {0, 0.1, 0.5, 0.9} × L_fr ∈ {0,…,1.0}, 192 matched cells per loop.

| Loop | eta_prod (peak) | fixed max | cells > 1.0 | **tailwater max** | cells > eta_prod |
|---|---|---|---|---|---|
| HEISVERKET (TROLLDAMMEN↔SKYFONNA via HEIMFOSS) | 0.78817 | **1.0256** | 4 | **0.7527** | **0** |
| OPPLOFT (SALTVIKA↔TROLLDAMMEN via DYPFALL) | 0.78817 | 0.7083 | 0 | **0.6999** | **0** |

HEISVERKET at the old worst cell (a_pump 0.5, U_fr 0, L across its range):

| L_fr | 0.0 | 0.5 | 0.8 | 0.9 | 0.95 | 1.0 |
|---|---|---|---|---|---|---|
| eta_rt fixed | 0.7544 | 0.8731 | 0.9597 | 0.9917 | **1.0084** | **1.0256** |
| **eta_rt tailwater** | 0.7459 | 0.7393 | 0.7345 | 0.7327 | 0.7317 | 0.7308 |

The remaining downward drift with L is head loss (`H_pump − H_turb ≈ 5.06 m` constant) acting on
a shrinking gross head. That is physical, and it is not R1.

**Head bookkeeping [fact].** For all three opted-in Fabelvassdraget stations, under random actions
over 72 steps, `S->Hbrutto[t]` equals `avg(clip_HRW(intake)) − avg(tailwater)` recomputed from
HERSS's own `res_masl` series with **residual 0.0** (t = 1..71).

## 5. Determinism, reset, cost (Part 3.3)

| Instance (tailwater tracking on) | 8 repeats bit-for-bit | A→B→A bit-for-bit |
|---|---|---|
| synthetic loop A0 | yes | yes (B verified to differ) |
| fabelvassdraget, 3 stations opted in | yes | yes (B verified to differ) |

Why reset holds **[fact]**: `tw_start/end_masl` are rewritten by the reservoir every step before
they are read, and `tailwater_final_pass` is restored to false after every re-run.

Runtime: fabelvassdraget, 72 steps, `Simulate` + `CalcVF` in process, best of 5 × 200 runs:
0.495 ms fixed → 0.565 ms with 3 of 4 stations opted in, **+14 %**. The cost is the duplicated
station pass. It is zero for datasets that do not opt in.

## 6. Python replica (Part 3.4, not implemented)

- **Pump replica (`analysis/pump_audit/replica_pump.py`).** It would need a matching change to stay
  valid on opted-in instances. Station head is computed at `replica_pump.py:293` against
  `nd.powstat_masl`, inside the node loop. What it would take: record tailwater start/end levels in
  the reservoir branch, the way `pump_src_start/end` already are, and move the station's
  head, power, income and profit into the existing second pass (the one mirroring
  `CalcPowerAndCost`). About 15-20 lines. Then re-verify against HERSS to ~1e-11 as in the pump
  audit.
- **DP state.** For DP on a tailwater-tracking instance, the tailwater reservoir's level must be
  part of the state, because it changes the station's head. In a closed pump loop it already is,
  since both reservoirs are state. For a plain station → reservoir cascade this adds one state
  dimension that the current single-reservoir DP does not have.
- **Other replicas** (`scarcity_gap`, `full_cascade`, `cascade`, `mini_utahps_daily_dp`) all
  subtract a fixed `powstat_masl`. They stay valid for any instance that does not opt in, which is
  every shipped dataset.

## 7. Verdict (Part 4)

**Size.** 4 files, +62/−5 lines. It did **not** stay within the parser plus one head function. It
also needed the reverse-pointer wiring (`herss.cpp` SetPointers, `reservoir.cpp`) and a new
end-of-timestep pass in the core loop `Herss::Simulate`. All of it copies the existing pump
pattern; nothing new is invented.

**Risk.**
- Default path: the regression suite caught nothing. Bit-for-bit identity holds at full precision
  on all shipped datasets, and the gtest results are identical.
- Opt-in path: the risks are semantic, not mechanical. They are the four **[open]** questions in
  §2: deferred accounting, own discharge in the tailwater, HRW-clip asymmetry, and Pelton vs
  reaction.
- Mechanical wrinkles: log warnings from an opted-in station are emitted twice per step, and there
  is a +14 % runtime cost.
- The prototype adds no new gtest. A production version should add one next to `test_pump.cpp`.

**Complexity rating: small-and-contained, with one design decision attached.** The code is small.
It is not trivial, because the timing forces a change to the simulation loop. That change is the
part that needs the lead developer's agreement, not the line count.

**Recommendation on placement.** The *code* is small enough to be a project-semester contribution.
The *semantics* are not the student's to decide. Where the tailwater is measured (raw or clipped,
tracked or `max(POWSTAT_MASL, ·)`), and whether station accounting may be end-of-step, are
modelling decisions about HERSS physics. CLAUDE.md §3 puts HERSS physics out of thesis scope.
Suggested route: hand this branch and report to the HERSS lead developer as a worked proposal with
evidence, and let upstream own the change. For the thesis, keep the declarable workaround from the
R1 report (`POWSTAT_MASL >= HRW(L)`). Only adopt tailwater tracking if upstream ships it; then
re-pin and re-verify.

**What this does not show.** It is not production-ready and should not be merged. It is not
checked on variable-timestep datasets, on multi-generator stations with separate penstocks in a
loop, or on a station whose `TAILWATER_IDNR` differs from its `DOWNLINK_IDNR`.
