# HERSS as an optimization benchmark — feasibility exploration

**Purpose.** This is an *exploration*, not a solution. It determines whether the HERSS simulator and
its shipped datasets can serve as the evaluation oracle for a master's thesis in optimization/OR
(action sequence → scalar value function `V`). No optimization problem is solved here; the deliverable
is evidence about whether a real optimization problem *exists* in these instances and whether the
oracle is usable.

**Provenance.** HERSS `VERSION 3.1.03 / VERSION_DATE 20260611`; upstream commit `029a2d5`; measurements
via the repo `.venv` (Python 3.13.11, cppyy 3.5.0) driving `src/herss.so`, and `src/herss.exe` on the
shipped datasets. Each claim is labelled **[measured]** (computed/executed here), **[read]** (from
source/config), or **[inferred]**. Code claims cite `file:line`.

**Build caveat.** The shipped `Makefile`'s effective `CFLAGS` is `-g` (debug, no `-O3`, no
`-march=native`) — its last assignment wins. All timings below are therefore **conservative**; an
optimized build would be materially faster. Per repo hygiene, `src/` (incl. `Makefile`) was not modified.

---

## Executive verdict

| Question | Finding | Verdict |
|---|---|---|
| Is head-dependence non-negligible? (make-or-break) | 13.4% on single-reservoir instances, up to 46.5% (EASTER) / 43.5% (SVEIGSHYL_I) | **Yes — thesis premise survives** |
| Does storage coupling bind? | Binds in `mini_utahps_daily` (R=0.87) and all uTAHPS reservoirs (R=0.07–0.68); does NOT bind in hourly-mini (R=13) | **Mixed — pick binding instances** |
| Is there discrete/commitment structure? | `POWSTAT_STARTSTOP=2.0` everywhere ≈ 0.1–3% of a step's revenue | **No — commitment axis is weak** |
| Is the instance degenerate (restprice out of range)? | restprice mid-distribution (19th–69th pct) everywhere | **No — selective operation** |
| Is the oracle deterministic & resettable? | Bit-identical repeats; A→B→A exact | **Yes** |
| Is the oracle fast enough? | ~16k ev/s (DP instance), ~21 ev/s (full-year hourly), compute-bound | **Yes** |
| Is rolling-horizon a valid decomposition? | Storage/production/terminal exact; only start/stop seam error (rel 1.4e-5) | **Yes, to high accuracy** |

**Overall: HERSS + these datasets are a viable oracle for the thesis.** The optimization content comes
from head-dependence, non-flat turbine curves, storage/spill coupling, cascade routing delay, and the
aggressive-action discontinuity — *not* from unit commitment. The instance selection matters: hourly-mini
instances are near-degenerate and must not be the headline benchmark.

---

## TIER 1 — does an optimization problem exist?

### 1.1 Head variation relative to gross head **[read; arithmetic checked]**

Model: `Hbrutto = (start_masl+end_masl)/2 − POWSTAT_MASL` (`powerstation.cpp:167`);
`Hnetto = Hbrutto − HEADLOSSCOEF·Q²` (quadratic loss, `powerstation.cpp:174/209`). No `DELTA_H`; level
capped at HRW for head (`reservoir.cpp:501-503,658-660`).

| Station | Tailwater | H@LRW | H@HRW | (H_HRW−H_LRW)/H_HRW | HEADLOSSCOEF |
|---|---|---|---|---|---|
| SVOLETJONN / PSTAT_B (mini, res_casc_A/C, uTAHPS n1) | 690 | 58 | 67 | **13.4%** | 0.3 |
| SVEIGSHYL_I (uTAHPS n6) | 581 | 39 | 69 | **43.5%** | 0.2 |
| SVEIGSHYL_II (uTAHPS n7) | 581 | 159 | 168 | **5.4%** | 0.145 |
| EASTER (uTAHPS n10) | 218 | 115 | 215 | **46.5%** | 0.145 |

The would-be killer ("~1–2%, negligible") is **refuted**. Head is a real non-linearity everywhere except
SVEIGSHYL_II; quadratic head loss compounds it.

### 1.2 Storage tightness **[measured]**

`R = active storage / (Q_max·dt·T)` = fraction of horizon full-capacity output sustainable from full.

| Reservoir (dataset) | Active Mm³ | maxQ/horizon Mm³ | **R** | Inflow Mm³ | Inflow/active | Regime |
|---|---|---|---|---|---|---|
| HJELLE (mini_utahps_daily, T=30) | 9.0 | 10.37 | **0.87** | 12.88 | 1.43 | **binds** |
| HJELLE (mini hourly/new/spillway, res_casc_C, T=48) | 9.0 | 0.69 | **13.0** | 0.56 | 0.06 | **decoupled (too easy)** |
| HJELLE (uTAHPS daily, T=365) | 9.0 | 126.1 | 0.07 | 92.3 | 10.3 | binds hard, spill likely |
| GRESSE (uTAHPS) | 61.44 | 189.2 | 0.33 | 57.3 | 0.93 | binds |
| TOPPSY (uTAHPS) | 126.64 | 186.1 | 0.68 | 75.2 | 0.59 | binds |
| KROKNESVATN (uTAHPS) | 199.27 | 309.1 | 0.65 | 161.3 | 0.81 | binds |

### 1.3 Discrete structure **[read; confirmed by measured totals]**

`POWSTAT_STARTSTOP=2.0` for every station in every dataset; `MAX_ADJUST=-9999` (inactive,
`powerstation.cpp:417-424`); `RES_PENALTY=300` is a reservoir keyword, not a commitment cost. Measured
full-horizon start/stop totals: 5 (mini daily), 6 (mini hourly), 22 (uTAHPS daily, 365×4), 42
(new_format) EUR — vs value functions of 25k–31M. **Commitment structure is negligible.** The
non-smoothness that remains is the aggressive-action cliff (§2.3) and the HRW spill kink.

### 1.4 Instance dimensions **[measured]**

| Dataset | res/pstat/chan | gens | action cols | T | dt | decision dim | note |
|---|---|---|---|---|---|---|---|
| mini_utahps_daily | 1/1/1 | 1 | 1 | 30 | 86400 | 30 | **DP reference** (storage binds) |
| mini_utahps_hourly | 1/1/1 | 1 | 1 | 48 | 3600 | 48 | decoupled |
| mini_utahps_new_inputformat | 1/1/1 | 1 | 1 | 48 | 3600 | 48 | decoupled; geometry+curve |
| mini_utahps_spillway | 1/1/1 | 1 | 1 | 48 | 3600 | 48 | decoupled; SPILLWAY |
| res_casc_A | 2/1/3 | 2 | 3 | 30 | 86400 | 90 | 2-res cascade + hatch, multi-gen |
| res_casc_B | 2/0/2 | 0 | 1 | 12 | 3600 | 12 | **no pstation → V=0** |
| res_casc_C | 1/1/1 | 1 | 1 | 48 | 3600 | 48 | decoupled |
| res_casc_D | 2/0/2 | 0 | 2 | 12 | 3600 | 24 | **no pstation → V=0** |
| utahps_daily | 4/4/4 | 4 | 4 | 365 | 86400 | 1460 | **medium benchmark** |
| utahps_daily_new_format | 4/4/4 | 5 | 5 | 365 | 86400 | 1825 | multi-gen n10 |
| utahps_hourly | 4/4/4 | 4 | 4 | 8760 | 3600 | 35040 | **large benchmark** |
| utahps_multires | 4/4/4 | 4 | 4 | 1560 | variable | 6240 | ships without output/ dir (see §3.6) |

Multi-generator: `res_casc_A`, `utahps_daily_new_format`. Active `OUTLET_HATCH` action: `res_casc_A`,
`res_casc_B`, `res_casc_D`. SPILLWAY: `mini_utahps_spillway`, `utahps_daily_new_format`(n0,3). Single
reservoir+generator: the four mini + `res_casc_C` (only `mini_utahps_daily` has binding storage).

### 1.5 Channel storage → objective **[read, cited]**

Channels contribute **zero** to income/cost/valued-terminal when QMIN inactive
(`channel.cpp:108,118,126-127`); the terminal term loops over PSTATION nodes only
(`riversystem.cpp:433,573`). **Every channel in every dataset has QMIN inactive**, and QMIN parsing
hard-errors if enabled (`channel.cpp:264`, WIP). Channel state still reshapes *downstream inflow timing*
via cascaded linear reservoirs (`channel.cpp:87,102-106`). **DP consequence:** in single-reservoir
instances the channel is the terminal, unvalued node → **droppable, DP state = reservoir storage (1-D)**.
In cascaded uTAHPS, channel timing feeds downstream and cannot be dropped.

---

## TIER 2 — objective landscape

### 2.1 Turbine efficiency **[read]** — non-flat, BEP below full load ⇒ partial loading is a real decision

| Curve (users) | Peak η | η @ full | Rel. loss @ full |
|---|---|---|---|
| S — SVOLETJONN/RES_B (mini_daily, res_casc_A/C, uTAHPS n1) | 93% @ Q≈2.8–3.5 | 88% @ Q=4 | 5.4% |
| U — UNIFORM_NORMALIZED (mini hourly/new/spillway, new_format) | 92% @ 0.5·Qmax | 82% @ Qmax | **10.9%** |
| I — SVEIGSHYL_I | 93% @ ~0.7 | 90% | 3.2% |
| II — SVEIGSHYL_II | 91% @ Q≈2.4 | 89% @ Q=6 | flat top, wide |
| E — EASTER | 93% | 90% | 3.2% |

Evaluated by piecewise-linear interpolation (`calcEfficiency`, `powerstation.cpp:68-106`) ⇒ objective
non-convex in Q; not bang-bang.

### 2.2 Price / restprice position **[measured]**

| Dataset | T | min | median | max | std | top/bot decile | restprice | pct |
|---|---|---|---|---|---|---|---|---|
| mini_utahps_daily | 30 | 10.0 | 38.2 | 99.1 | 28.2 | 8.9 | 33 | 50th |
| mini hourly (+new/spillway/res_casc_C) | 48 | 8.0 | 18.7 | 99.1 | 25.0 | 8.6 | 33 | 69th |
| res_casc_B / D | 12 | 10.0 | 26.2 | 52.9 | 12.4 | 5.3 | 33 | 67th |
| utahps_daily (+new_format) | 365 | 0.04 | 108.8 | 564.9 | 98.8 | 10.8 | 101 | 43rd |
| utahps_hourly | 8760 | 0.01 | 108.6 | 702.8 | 104.6 | 18.5 | 101 | 42nd |
| utahps_multires | 1560 | 0.07 | 202.8 | 673.7 | 142.7 | 12.4 | 101 | 19th |

restprice sits inside the distribution everywhere ⇒ non-degenerate, threshold policy is selective.

### 2.3 Aggressive-action discontinuity **[read + measured]**

Branch (`powerstation.cpp:785`): `if(Q_Mm3>up_res_Mm3){ cost=(Q_Mm3−up_res_Mm3)·1000; flow=0.0; }`
(`HERSS_AGGRESSIVE_ACTIONS_COST=1000`, `herss.h:99`; `up_res_Mm3` = active upstream vol,
`reservoir.cpp:509`). Hard step: production/outflow → 0 while cost jumps; auto_qmin release is also killed
(diagnostic `auto_qmin_m3s[t]` left stale). **[measured]** Under the shipped `actions.txt`,
`sum_aggressive_actions_cost = 0.000` for **all 11 runnable datasets** — the cliff is **latent**: the
reference policies never touch it, but any search increasing discharge can. ⇒ a clip-to-available
**repair operator** is needed for search feasibility, not for reproducing the shipped baselines.
(Fine-grained "within 10% of available" histogram not yet computed; see follow-ups.)

### 2.4 Exact-DP tractability **[read]**

`mini_utahps_daily`: state = reservoir active storage (channel droppable §1.5; start/stop negligible so
on/off state barely matters). ~500 storage × ~50 action × T=30 ≈ **750k single-step transitions** —
trivial. Transitions reproducible **outside** HERSS via ~9 functions (mass balance `reservoir.cpp:427-715`;
level↔vol `:276-291`; `CalcOverflow`; `GetTunnelFLow` `powerstation.cpp:746-793`; net head `:167,174`;
`calcEfficiency` `:68-106`; revenue `:192-203`; terminal `riversystem.cpp:436`). **Caveat:** head uses
the *average* of start/end-of-step level, and end level depends on the action ⇒ head is implicitly
action-dependent within a step; the replica must order pre-level → discharge → post-level → averaged head
→ power. HERSS exposes only a **full-horizon** `Simulate()`, so DP must use the replica — which must be
validated against HERSS (follow-up).

---

## TIER 3 — oracle usability (executed)

### 3.2 Determinism & state reset **[measured] — PASS**

Repeated `Simulate()` with identical actions is **bit-identical** on every dataset:

| Dataset | V (repeat 1 = repeat 2) |
|---|---|
| mini_utahps_daily | 69135.22354412361 |
| mini_utahps_hourly | 24890.618883979656 |
| res_casc_B | 0.0 (no pstation) |
| utahps_daily | 26428741.819164533 |
| utahps_hourly | 26518502.041039046 |

A→B→A perturbation (node1/gen0/t5, a0=0.61→0.123→0.61): V(A)=69135.22354412361, V(B)=68787.42447794124,
V(A again)=**69135.22354412361** — reproduced to the last bit. **The oracle is deterministic and exactly
resettable in-process** (confirms the manual's "Simulate() reinitialises state on every call").

### 3.3 Evaluation cost **[measured]**

In-process `Simulate()+CalcVF()`, debug build:

| Dataset | T | compute mean±std | evals/s | +writefiles | writes evals/s |
|---|---|---|---|---|---|
| res_casc_B | 12 | 0.024±0.017 ms | 41,930 | 0.730 ms | 1,369 |
| mini_utahps_daily | 30 | 0.063±0.027 ms | **15,995** | 1.003 ms | 997 |
| mini_utahps_hourly | 48 | 0.132±0.041 ms | 7,568 | 1.251 ms | 800 |
| utahps_hourly | 8760 | 46.8±12.1 ms | **21** | 307 ms | 3 |

`Simulate()` does **not** write files (`herss.cpp:755` `WriteNodeOutput` is separate). ⇒ compute-bound
without writes; **file I/O dominates** when enabled (6.5× on the big instance, 10–40× on small). **A search
loop must keep the oracle in-process and never write node files.** Even the full-year hourly instance
gives 21 ev/s (debug) — ample for a matheuristic; the DP-scale instance gives ~16k ev/s.

### 3.4 `CalcVF` vs `WriteRiverSystemData` **[measured] — consistent**

For equal `restprice`, the member `valuefunction_Euro` after `WriteRiverSystemData` equals `CalcVF`
bit-for-bit: mini_utahps_daily 69135.22354412361, res_casc_A 88996.50190987655, utahps_daily
26428741.819164533. (Source note: Write defines `tot_remaining_Mm3` differently, `riversystem.cpp:566-567`
vs `:418`, and reuses a stale `tot_active_remaining_Mm3` `:669`, but neither enters `V`.)

### 3.5 State chaining / rolling-horizon validity **[measured]**

`mini_utahps_daily`, split at t=15, part-1 `outstate`→part-2 `start_state`:

| Quantity | Monolithic | Chained (P1+P2) | Δ |
|---|---|---|---|
| production profit | 36465.224 | 36466.219 | **+0.995** |
| terminal water value | 32670.000 | 32670.000 | 0.000 |
| start/stop cost | 5.000 | 3.000 + 1.000 = 4.000 | −1.000 |
| **value function V** | 69135.224 | 69136.219 | **+0.995 (rel 1.4e-5)** |

**Storage, production, and terminal value chain exactly** (terminal identical to the cent). The **only**
discrepancy is a mispriced start/stop event at the seam (chain omits ~1 EUR), consistent with the
documented "multi-generator start/end state unimplemented" caveat and the pstation seam-state semantics.
⇒ **Rolling horizon is a valid decomposition here to relative 1e-5**, precisely because start/stop is
negligible. If start/stop were inflated to create commitment structure, the seam error would grow and
require explicit seam handling.

### 3.1 Test suite **[read] — blocked, not run**

`make test` needs the gtest source tree at `/usr/src/gtest` (`Makefile:28,95-99`), which is **absent**.
Install `libgtest-dev` (Debian installs sources to `/usr/src/googletest`/`/usr/src/gtest`) then
`make test`. Suite = 11 files / ~100 tests (line, arraycurve, reservoir, channel, riversystem, dataset,
globalconfig, powerstation, valuefunction, waterbalance, runtime). **Known naming bug [read]:**
`test_runtime.cpp:16` names the test `…Under350ms` but `:22` asserts `kMaxAvgSeconds = 0.75` and `:71`
`EXPECT_LT(avg, 0.75)` — the enforced threshold is **0.75 s**, not 350 ms.

### 3.6 Shipped-dataset packaging gap **[measured]**

`utahps_multires` simulates but cannot write output — it ships **without an `output/` directory**
(`Cannot open file ./output/riversystem_uTAHPS_output.txt`, `riversystem.cpp:542`). HERSS does not create
the dir. Fix: `mkdir data/utahps_multires/output`. Minor, but a reproducibility snag for the one
variable-resolution instance.

---

## What this rules out (assumptions contradicted or confirmed)

1. **RULED OUT — "head variation may be 1–2%, negligible."** 13.4% on the DP instance, 43–47% at
   SVEIGSHYL_I/EASTER. *This keeps the linearisation-gap thesis alive.*
2. **CONFIRMED WEAK — commitment structure.** Start/stop ≈ 0.1–3% of a step's revenue; totals 5–42 EUR
   vs V of 25k–31M. A commitment-binary-centric framing has almost nothing to bite on unless start/stop
   is inflated.
3. **RULED OUT — "restprice out of range ⇒ degenerate."** restprice is mid-distribution everywhere.
4. **PARTIALLY RULED OUT — "channel must be a DP state."** Droppable in single-reservoir instances;
   retained (timing) in cascades.
5. **NUANCED — "constant marginal water value ⇒ threshold rule ⇒ no thesis."** Marginal water value *is*
   exactly constant up to the HRW kink (`riversystem.cpp:436,474`). But where storage binds
   (`mini_utahps_daily`, all uTAHPS), the perturbations — head 13–47%, turbine BEP (5–11% swing),
   spill, cascade delay, aggressive cliff — are quantified and non-trivial. **The hourly-mini instances
   (R=13) are the genuine "too easy" cases and must not be headline benchmarks.**
6. **RULED OUT — "rolling horizon may not chain."** It chains to relative 1e-5; error confined to the
   negligible start/stop seam. Rolling horizon is a viable decomposition.

## Research risks surfaced

- **QMIN hard-disabled** (`channel.cpp:264`) — channel minimum-flow constraints cannot currently be
  exercised as constraints.
- **Two aggressive-action code paths** (`powerstation.cpp:785` vs `:145-154`); the aggressive branch
  leaves `auto_qmin_m3s[t]` diagnostic stale.
- **`WriteRiverSystemData` duplicates `CalcVF`** and diverges on `tot_remaining_Mm3` + a stale member
  (harmless to `V`, but a maintenance trap).
- **Test name/threshold mismatch** (0.75 s vs "350 ms"); **`utahps_multires` missing `output/`**.
- **Degenerate instances:** `res_casc_B`, `res_casc_D` have no power station ⇒ `V=0`, no objective
  signal; unusable as oracles.

## Recommended benchmark set (for later work — not built here)

- **Exact-DP reference:** `mini_utahps_daily` (1-D state, storage binds, head 13.4%).
- **Small cascade:** `res_casc_A` (2 reservoirs, hatch, 2 generators, daily).
- **Medium:** `utahps_daily` (4×4, 365 steps, strong head at EASTER/SVEIGSHYL_I).
- **Large / stress:** `utahps_hourly` (35k decision vars) and `utahps_multires` (after `mkdir output`).
- **Avoid as headline:** hourly-mini instances (decoupled), `res_casc_B/D` (no objective).

## Reproducibility

Build: `cd src && make` → `herss.exe`, `herss.so` (debug; `NO_LOG=1` and adding `-O3` would speed runs).
Oracle harness: `analysis/tier3_measure.py` (run `../.venv/bin/python tier3_measure.py` from `analysis/`).
Chaining test: `scratchpad/chain_test.py`. All runs stamp `VERSION 3.1.03 / 20260611`, commit `029a2d5`.
Follow-ups not yet run: gtest suite (needs `libgtest-dev`), near-cliff histogram (§2.3), external
single-step DP replica validated against HERSS (§2.4).
