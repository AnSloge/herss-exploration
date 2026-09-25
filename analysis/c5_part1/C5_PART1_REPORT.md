# C5, part 1 of 2: can an R1-safe loop be *positioned* in the hard corner?

**Date:** 2026-09-21. **Branch:** `c5-part1`, created from `system-design` at base commit
`0e98d837ed046e0089c6c7a0a641bc314cd627a4`.
**HERSS:** `VERSION` 4.0.00 / `VERSION_DATE` 20260814. This is the **baseline** build: `src/` is
identical to the base commit, `herss.so` was rebuilt from it on this branch and contains no
`TAILWATER` symbols. The `r1-fix-prototype` branch was not used.
**Reproduce:** `bash analysis/c5_part1/run_all.sh` (~15 s). The run log is in `c5_run.log`.
Nothing under `src/` or `data/` was modified.

Labels: **[measured]** means run in HERSS in this work. **[source]** means read in code or in
committed reports. **[assessment]** means interpretation. No DP or B4 was run, and nothing in
this report is a claim about hardness.

---

## Bottom line

**Yes. An instance can be R1-safe by geometry and also sit in the Fase C hard corner.**
`c5_high` is the existence proof, and part 2 can measure its gap.

- **[measured] Positioning.** `rho` = 1.0000000039 and `R` = 0.0713470, both read back from the
  instance on disk. These are exactly the coordinates of the Fase C cell `syn_rho1_R1`, which is
  the peak of the Fase C `rho` edge (1.795 % B4 gap as a Fase C read-across). Neither pressure had
  to give way. Elevation and volume/throughput really are separate knob sets, because `rho` and
  `R` contain no elevation term.
- **[measured] R1-safety.** Across 2000 valid round-trip cells, the maximum `eta_rt` is
  **0.76871**, below `eta_prod` = 0.77941. **0 of 2000 cells fail, and 0 exceed 1.** The positive
  control, the same instance with the unsafe datum `POWSTAT_MASL = LRW(L)`, fails in **380 of
  2000** cells (max 0.81287). So the sweep can detect a breach.
- **[assessment] One caveat is serious.** It does not break the existence proof, but it limits
  how far Fase C carries over. `(rho, R)` is not the whole story. Fase C also held the head span
  fixed: 9 m of regulation against 62.5 m of gross head. A high-head L makes that ratio 5.6×
  smaller (0.0255 against 0.144), so head dependence is much weaker in `c5_high` than in any Fase
  C cell. The companion instance `c5_headkeep` removes that confound at the cost of a
  medium-head D. The next section explains why both instances exist.

---

## Part A: the instances

### Construction

Everything is built by `build_c5.py`. A single dict per variant writes both the HERSS files and
the replica parameters.

| node | | built from |
|---|---|---|
| 0 PUMP `pump_LU` | L → U, `MAX_DISCHARGE` 4.0, `HEADLOSSCOEF` 0.3, motor 0.97, pump-curve peak 90 %, `PUMP_INLET_MASL` = LRW(L) | new |
| 1 RESERVOIR U | reservoir curve, LRW/HRW 748/757, init_fr 0.7, inflow series | **`syn_rho1_R1` verbatim**: the Fase C scaling generator's output at `s_R` = 1, `rho` = 1 |
| 2 PSTATION `sta_UL` | turbine curve, Qmax 4.0, gen 0.96, head loss 0.3, min discharge 1.0, start/stop 2.0 | `syn_rho1_R1` verbatim; `DOWNLINK_IDNR` = L |
| 3 RESERVOIR L | 9 Mm³ active, linear over R_L; init_fr 0; no natural inflow; hatch and overflow to 4 | new |
| 4 CHANNEL | system outlet | new |

The inflow into U and the price file are byte-identical to `syn_rho1_R1`; the build checks this.
Adding the loop cannot change `rho`, because L starts empty and `PUMP_INLET_MASL = LRW(L)`. The
only water the pump can lift is water the turbine or U's spillway has already released into L.
`rho_system`, which also counts L's initial pumpable water and L's inflow, therefore equals `rho`
exactly **[measured]**.

### Three variants

| variant | role | L range (masl) | `POWSTAT_MASL` | used in |
|---|---|---|---|---|
| `c5_high` | **primary**, per the spec | 380–400 | 400 = HRW(L) | A–D |
| `c5_headkeep` | Fase C head kept: turbine side identical to `syn_rho1_R1` | 685–690 | 690 = HRW(L) | A–D |
| `c5_high_ctrl` | **positive control**: `c5_high` with the unsafe datum | 380–400 | 380 = LRW(L) | C only |

`c5_headkeep` exists because of the caveat above. Its turbine side (curve, head loss, datum 690,
`LOCAL_ENERGY_EQUIVALENT` 0.11) is identical to the Fase C cell. The only changes are the added
L and pump, and U's spillway and the station outfall now drain into L. If the pump is never
used, it is structurally closest to a measured Fase C cell (see the open decision under Part D).

### Back-computed numbers

All values are read back from the files on disk. Active volumes use HERSS's own ArrayCurve, the
same method as `params.py`. `rho` and `R` follow the Fase C definitions exactly
(`params.regime_numbers`).

| | `c5_high` | `c5_headkeep` |
|---|---|---|
| `D` = LRW(U) − HRW(L) | **348.0 m** | 58.0 m |
| `R_L` = HRW(L) − LRW(L) | 20.0 m | 5.0 m |
| `R_L/D` | **0.05747** | 0.08621 |
| `eta_prod` (0.90 · 0.97 · 0.93 · 0.96, peak product) | 0.779414 | 0.779414 |
| energy-creation threshold `(1 − eta_prod)/eta_prod` | 0.283015 | 0.283015 |
| `R_L/D` as a fraction of the threshold | 0.20 | 0.30 |
| datum rule `POWSTAT_MASL ≥ HRW(L)` | ✓ | ✓ |
| `HRW(L) < LRW(U)` (no negative pump head) | ✓ | ✓ |
| understatement bound `R_L/(D + R_L)` (cost of the datum rule) | 5.43 % | 7.94 % |
| `rho` | **1.0000000039** | 1.0000000039 |
| `R` = 9.0 / 126.144 | **0.0713470** | 0.0713470 |
| head span ratio (U regulated range / gross mid head) | **0.0255** | 0.144 (= Fase C) |
| `LOCAL_ENERGY_EQUIVALENT` | 0.6204¹ | 0.11 |

¹ **[assessment]** This is scaled with gross mid head (0.11 × 352.5/62.5), so the bias between
the terminal term and in-horizon production has the same ratio as in `syn_rho1_R1`. It affects
none of the part 1 numbers, which do not depend on the terminal term. It is provisional for
part 2.

With the datum at HRW(L), the threshold on `R_L/D` no longer matters for safety: the head ratio
is at most 1 for any `R_L/D`. It is still met with a wide margin, as the spec asked. What `R_L/D`
now governs is how much generated energy is understated, and that is 5.4 % for `c5_high`.

---

## Part B: validation [measured]

| check | `c5_high` | `c5_headkeep` |
|---|---|---|
| CLI (`herss.exe`, shipped actions): exit 0, ERROR/WARN lines in the log | 0 | 0 |
| `gc.Diagnose()`, `gc.checkNrSteps()`, `DiagnoseRiversystemConfiguration()` | pass | pass |
| water balance, worst \|balance\| over 13 sequences (up to 116 Mm³ pumped) | **2.6e-13** | **3.8e-13** |
| determinism, and A→B→A after a different sequence | bit-identical | bit-identical |
| replica vs HERSS, worst \|ΔVF\| over 13 sequences | **1.4e-08 EUR** | **6.3e-09 EUR** |

**The replica covers this topology.** `analysis/pump_audit/replica_pump.py` is written per node
class, and every class this loop uses is inside its stated scope. This is the first time it has
been validated on a 365-step instance with a realistic machine; before this it had been tested
only on the 8- and 24-step audit fixtures. All results are far inside the 0.05 EUR tolerance.
Part 2 can use it for DP without further porting.

**Warnings in the in-process runs.** They come from stress sequences, not from the configuration.
Every warning outside the CLI runs is one of three kinds, all expected:
- `PUMP_INLET_MASL` delivery limits: 2734 lines in validation, 300 in the sweep.
- Aggressive actions under random or "generate full" sequences: 130 pairs in validation, 0 in
  the sweep.
- The `POWSTAT_MIN_DISCHARGE` soft warning, which has no physical effect (`powerstation.cpp:160`).

**Terminal term, as a fact to carry into part 2.** With U and L both full, HERSS credits the
station with 9.0 Mm³ of upstream active volume. That is U only. Water in L is worth **0** at the
horizon end, and the pump contributes nothing to the terminal term. This agrees with the
replica's `terminal_value_Euro`.

---

## Part C: R1-safety [measured]

This is the protocol from `analysis/r1_loop` parts 2 and 5. The pump lifts a volume L→U at
t = 0, the station releases the **identical** volume U→L at t = 1, and everything else is shut.
`eta_rt` is energy out over energy in, both from HERSS's own `S->Power`. Volumes are matched on
the pump's *actual* lift, so cells where L is nearly empty are still exact round trips. A cell is
kept only if the volume mismatch is below 1e-6, U did not spill and no aggressive-action cost was
charged.

The sweep covers `L_fr` 0.00–1.00 in steps of 0.05 (L's whole range), `a_pump` 0.05–1.00 in steps
of 0.05, and `U_fr` ∈ {0, 0.25, 0.5, 0.75, 0.95}. That is 2100 cells per variant. The 100 cells
with `L_fr` = 0 lift nothing, because L sits at the pump inlet; they are counted as "no round
trip", not as passes. **0 cells were invalid.** All actions are clamped to [0,1] before
`SetAction`.

| | `c5_high` | `c5_headkeep` | `c5_high_ctrl` (unsafe datum) |
|---|---|---|---|
| valid cells | 2000 | 2000 | 2000 |
| **max `eta_rt`** | **0.768710** | **0.726029** | 0.812869 |
| at (a_pump, U_fr, L_fr) | (0.70, 0.95, 1.00) | (0.70, 0.95, 1.00) | (0.70, 0.00, 1.00) |
| `eta_prod` | 0.779414 | 0.779414 | 0.779414 |
| margin, `eta_prod` − max | **+0.0107** | +0.0534 | −0.0335 |
| **cells with `eta_rt > eta_prod`** | **0 / 2000** | **0 / 2000** | **380 / 2000** |
| cells with `eta_rt > 1` | 0 | 0 | 0 |
| frictionless closed-form cap | 0.7794 | 0.7794 | 0.8242 |
| max gross-head ratio H_turb/H_pump | 1.000054 | 1.000549 | 1.057487 |

**Result: every cell passes in both R1-safe instances.** The control shows the sweep is not
blind. Moving only the datum down by R_L produces 380 breaches, with a gross-head ratio of
1.0575, which matches `1 + R_L/D` = 1.0575. It still produces no energy creation, as predicted:
`R_L/D` is below the threshold.

`eta_rt` map for `c5_high` at `U_fr` = 0.95 (the argmax slice). It rises monotonically with L's
level, as the closed form predicts:

| a_pump \ L_fr | 0.05 | 0.25 | 0.50 | 0.75 | 1.00 |
|---|---|---|---|---|---|
| 0.25 | 0.3089 | 0.3122 | 0.3165 | 0.3208 | 0.3253 |
| 0.50 | 0.6425 | 0.6494 | 0.6582 | 0.6673 | 0.6766 |
| 0.75 | 0.7287 | 0.7365 | 0.7464 | 0.7567 | 0.7672 |
| 0.90 | 0.7108 | 0.7184 | 0.7281 | 0.7380 | 0.7482 |
| 1.00 | 0.6588 | 0.6657 | 0.6747 | 0.6839 | 0.6933 |

Maps for all three variants are in `r1_sweep_results.json`.

### What the safety margin actually rests on [assessment, checked by arithmetic]

The 0.0107 margin in `c5_high` does **not** come from the datum. At the argmax, both machines sit
at peak efficiency (pump 0.90 at 0.7·Qmax, turbine 0.93 at 2.8 m³/s). The gross-head ratio is
0.99935, which is essentially 1 because L is at HRW = P. What brings `eta_rt` below `eta_prod` is
friction. Head loss 0.3·Q² = 2.35 m is subtracted from the turbine head and added to the pump
head: net 354.37 m against 359.30 m. The decomposition is exact. `eta_rt` = `eta_prod` ×
(net-head ratio 0.98627) = 0.7687102650, which matches the measured value to about 1e-16. The
net-head ratio is friction 0.98690 × gross 0.99935. The datum rule guarantees a head ratio of at most 1. It does not guarantee a
margin. In a frictionless instance, the argmax would sit at `eta_prod` to within rounding.

### Two small findings from the edges of the sweep

1. **[measured] A gross-head ratio slightly above 1 is natural inflow, not geometry.** Its
   maximum is 1.000054 (`c5_high`, 5 cells) and 1.000549 (`c5_headkeep`, 33 cells), always at
   `L_fr` = 1 and small lifts. U receives 0.454 m³/s of natural inflow during the pump step, and
   that raises U's mean level in the turbine step. With U's inflow set to 0 at t = 0–1
   (`inflow_check.py`), the maximum falls to **0.99995** and **0.99993**. The extra energy
   belongs to the inflow; it is not created by the loop. None of these cells comes near
   `eta_prod`: the largest `eta_rt` among them is 0.479. In a frictionless instance at peak
   efficiency, though, inflow could push a round trip above `eta_prod` by roughly 1e-4. That is
   something to know, not a violation of R1.
2. **[measured] Rounding can trip the aggressive-action branch.** In the zero-inflow re-run, a
   release of exactly the lifted volume from U at LRW + lift overdraws by about **4e-14 Mm³**.
   That trips `powerstation.cpp:785-791`, which charges an aggressive-action cost and sets
   `flow = 0`, **zeroing the whole release**. It happened in 4 cells; releasing (1 − 1e-9) of the
   lift fixes it. **This matters for part 2:** a DP transition that drains U exactly to LRW can
   lose all its production to float noise. The DP's action grid should stop a tolerance short of
   the volume actually available, rather than exactly at it.

---

## Part D: positioning (not the gap)

The Fase C hard corner (`gap_fase_c.md` §11) is `R` ≲ 0.09 and `rho` in roughly the 0.5–1.0
band.

**[measured] Both instances land inside it, exactly on a measured cell.** `rho` = 1.000 and `R` =
0.0713 are the coordinates of `syn_rho1_R1`. `R` is 0.74 of the 1 % crossing `R*` ≈ 0.096 at
`rho` = 1.

Nearest Fase C cells. **These are read-across figures from pump-free instances, not measurements
of this instance.** Distance counts one `rho` step of 0.25 the same as one doubling of `R`.

| Fase C cell | kind | rho | R | B4 gap % | B2 gap % | distance |
|---|---|---|---|---|---|---|
| `syn_rho1_R1` | synthetic | 1.000 | 0.0713 | **1.795** | 4.439 | 0.000 |
| `syn_rho1_R1p25` | synthetic | 1.000 | 0.0892 | 1.106 | 4.086 | 0.32 |
| `syn_rho1_R1p5` | synthetic | 1.000 | 0.1070 | 0.845 | 3.428 | 0.59 |
| `hjelle_daily` | uTAHPS | 0.782 | 0.0713 | 1.075 | 5.121 | 0.87 |
| `syn_rho0p782_R1p25` | synthetic | 0.782 | 0.0892 | 0.601 | 4.118 | 0.93 |

**[assessment] Is it positioned to be hard?** On `(rho, R)`, yes, as well as it can be. It sits
on the peak of the `rho` edge, not on the shoulder where HJELLE sits. The read-across is weaker
than the matching coordinates suggest, for four reasons. They are listed so part 2 does not treat
the 1.795 % as a prediction:

1. **`rho = 1` is the band's upper edge.** Fase C marks the upper `rho` limit as unmeasured
   (§11). The gap drops from 1.795 % at 1.00 to 0.575 % at 1.25, so a `rho` just above 1 is not
   known to be safe ground.
2. **Head span (affects `c5_high` only).** Fase C isolated `R` at a *constant* head span, with a
   ratio of 0.144. `c5_high` has 0.0255, so head-dependent production is about 5.6× weaker. Fase
   C locates part of the low-`rho` difficulty in "scarcity and head dependence" (§8). How much of
   the 1.795 % survives a flatter head curve is unknown. `c5_headkeep` does not have this problem.
3. **The pump changes the spill mechanism (both variants).** In Fase C, U's spill leaves the
   system. Here it drains into L and can be pumped back at a round trip of up to 0.77. Fase C's
   leading interpretation of the peak at `rho` ≈ 1 is spill that *could be avoided by planning*
   (§8, an assessment, not a measurement). A pump makes spill partly recoverable. That could lower
   the gap, because spill mistakes become cheaper, or raise it, because there is one more
   decision to time. The sign is not known.
4. **A new decision and a new state.** L's level becomes a second state dimension, and pumping
   against the price is a new source of arbitrage value. Nothing in Fase C covers either.

**Open design decision for part 2, flagged and not made here:** U's spillway currently drains
into L, which is physically natural. Routing it to the outlet instead would restore Fase C's
spill semantics exactly. For `c5_headkeep` it would make "loop added, pump unused" coincide with
`syn_rho1_R1` in structure, which is the cleanest possible anchor. This is a question of
formulation, not of physics, so it is left for the owner to decide. It does not affect any part 1
number: the sweep had no U spill, and neither `rho` nor `R` involves the spill route.

---

## Verdict

| | `c5_high` (primary) | `c5_headkeep` |
|---|---|---|
| `D`, `R_L`, `R_L/D` | 348 m, 20 m, 0.0575 | 58 m, 5 m, 0.0862 |
| `rho`, `R` | 1.0000, 0.07135 | 1.0000, 0.07135 |
| `eta_prod`, threshold | 0.7794, 0.2830 | 0.7794, 0.2830 |
| **R1: max `eta_rt` vs `eta_prod`** | **0.7687 < 0.7794, 2000/2000 pass** | **0.7260 < 0.7794, 2000/2000 pass** |
| **Positioning** | inside the corner, on `syn_rho1_R1` (peak) | inside the corner, on `syn_rho1_R1` (peak) |
| read-across caveats | upper `rho` edge; head span 5.6× flatter; spill recoverable | upper `rho` edge; spill recoverable |

**It is possible.** The two pressures never conflicted. `R` and `rho` are ratios of volume and
throughput with no elevation term, while R1-safety depends only on elevations, so the loop can
be moved to any height without moving it on the `(rho, R)` plane. Nothing was traded off. The
real cost appears on a third axis the spec did not name: head span. Its answer is that you can
have high head with Fase C's `(rho, R)`, or Fase C's head span with medium head, but not both
without also scaling U's regulated range. Rescaling U's range would leave the Fase C construction.

The **gap has not been measured** for either instance. Whether either one is actually hard is
part 2, after the deterministic-versus-stochastic framing and the hardness metric are fixed.

## Artefacts

`build_c5.py` (builder and replica parameters), `validate_c5.py` → `validation_results.json`,
`r1_sweep.py` → `r1_sweep_results.json`, `inflow_check.py` → `inflow_check_results.json`,
`position.py` → `position_results.json`, `run_all.sh` → `c5_run.log`. The instance directories
are `c5_high/`, `c5_headkeep/` and `c5_high_ctrl/`; each contains the CLI log and outputs.
