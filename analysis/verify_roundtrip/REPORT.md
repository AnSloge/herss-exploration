# Independent verification: does a closed pump loop in HERSS create energy?

Date: 2026-09-28. Repo HEAD `7072a44` (branch `c5-part1`). HERSS source = last `src/` commit `0d3fc59`, built fresh from `git archive HEAD src` (no `TAILWATER_IDNR`, not `r1-fix-prototype`). HERSS `4.0.00` / `20260814`. `herss.so` sha256 `7c657f79…c9cd63`. Full provenance is in `run_meta.json`. Nothing in `src/` or `data/` was modified.

Labels: **[src]** = read in source, with file:line. **[meas]** = measured here. **[inf]** = inference or derivation.

## 0. Independence statement

- Before starting, my session memory index already contained one-line summaries of the earlier conclusions: "measured 1.0256", "eta_rt>1 iff …", "fix is POWSTAT_MASL >= HRW(lower)".
  - I could not un-see those. I did not open those memory files, `analysis/r1_loop/`, `analysis/pump_audit/`, or `pump_oracle.py` until §6.
- I read two infrastructure notes: the init order, and the cppyy array-read trap.
- The harness (`harness.py`) was written from `src/` and upstream `py_src/pyherss.py`.
- The measurement protocol was designed from source (§1–2) before any number was seen.
- The earlier reports were first opened **after all of §1–§5 below was written** (see §6).

## 1. The two head conventions (source)

| | Line | Elevations | Constant? |
|---|---|---|---|
| Station HEIMFOSS | `src/powerstation.cpp:167` `Hbrutto = ((start_of_stp_masl + end_of_stp_masl)/2.0) - powstat_masl;` | Upper reservoir level at start/end of step (set by SKYFONNA, `reservoir.cpp:521-524, 706-710`, **clamped to HRW**) minus `POWSTAT_MASL` | `powstat_masl` is a topology constant (`powerstation.cpp:412-413`), 195.0 m for HEIMFOSS (`data/fabelvassdraget/topology.txt:304`) |
| Station net head | `powerstation.cpp:174-175` `Hnetto = Hbrutto - headlosscoef*total_Q*total_Q` | — | — |
| Pump HEISVERKET | `src/pump.cpp:268-272` `Hbrutto = tgt_avg_masl - src_avg_masl; Hnetto = Hbrutto + headlosscoef*Q*Q` | Actual start/end levels of both SKYFONNA and TROLLDAMMEN (`reservoir.cpp:506-507, 715-716`), **no HRW clamp** | nothing constant |

**Same water body, different references [src]:**
- TROLLDAMMEN receives HEIMFOSS's discharge (`topology.txt:257`, `powerstation.cpp:281-283`) and is the pump's source (`topology.txt:16`).
- The pump measures lift from TROLLDAMMEN's actual surface.
- The station measures its drop to the fixed 195.0 m and never reads TROLLDAMMEN's level.
- TROLLDAMMEN's regulated range is 196–221 m (`topology.txt:316-317`), so 195.0 m sits below the whole operating range. The station is therefore always credited (L − 195) m more drop than the pump pays for.

The asymmetry described in the claim exists at source level.

There is a secondary asymmetry [src]: the station's upper level is clamped to HRW and the pump's is not. It only matters above HRW, which is outside every cell used here.

## 2. Measurement design

**Energy [src]:**
- E_in = −`S->Power[t]` of pump 0 (`pump.cpp:321`, MWh drawn from the grid, after pump and motor efficiency).
- E_out = `S->Power[t]` of HEIMFOSS (`powerstation.cpp:302`, MWh after turbine and generator efficiency).
- Both are HERSS's own per-step arrays, read through by-value C++ accessors (`harness.py`). Nothing is recomputed by hand.
- η_rt = ΣE_out/ΣE_in. Money is ignored.

**"The same water":**
- **Protocol A (primary):**
  - One step: pump at action a, and all three HEIMFOSS generators at a. Since 3 × 5 = 15 m³/s equals the pump maximum, the turbined flow equals the pumped flow.
  - Next step: everything off.
  - The loop moves no net water, so it is a literal closed cycle.
- **Protocol B:**
  - Pump at t=0 with the station off.
  - At t=1 the pump is off and the station runs at HERSS's reported *actual* pumped flow divided by 15 (a two-pass run).
- **Acceptance per cell:**
  - |pumped − turbined|/pumped < 1e-9 (the conversion macros are exact up to double round-off);
  - pumped = requested to 1e-9, i.e. the `PUMP_INLET_MASL` clip (`pump.cpp:222-223`) did not bind;
  - zero overflow in both reservoirs in both steps;
  - zero aggressive-action cost;
  - zero new logger warnings (`Logger::getWarningCount`);
  - bit-identical result on a second `Simulate()`.
- Cells that fail any check are excluded, not corrected.

**Isolation:**
- Actions are 0 for OPPLOFT (which feeds TROLLDAMMEN), DYPFALL (which draws from TROLLDAMMEN), TORDENFOSS, TIDEVERK, and all hatches.
- Contamination still present in the verbatim dataset [meas]:
  - natural inflow of 4.42 m³/s to SKYFONNA and 5.0 m³/s to TROLLDAMMEN;
  - about 7.1 m³/s of routed water into TROLLDAMMEN from channel start volumes (SAMLOPET, FONNBEKKEN);
  - 0.2 m³/s auto-qmin out of SKYFONNA.
- These can only act through the reservoir levels, which HERSS uses for both heads. They are removed in the `clean` + zero-inflow variant (§4.3).

**Grid:**
- Coarse: a ∈ {0.05…1.0}/0.05; SKYFONNA fill ∈ {0…0.95}/0.05 (288.0–307.0 m); TROLLDAMMEN fill ∈ {0…1.0}/0.05 (196.0–221.0 m). That is 8,400 cells per protocol.
- Refined around the maximum (see `run_meta.json`).

**Validation:**
- `gc.Diagnose()`, `gc.checkNrSteps()` and `DiagnoseRiversystemConfiguration()` ran without error or warning on every variant.
- The four reported cells were re-run through `herss.exe` with file inputs. The HERSS output files agree with the in-process values within print precision (|Δη| ≤ 8e-6). All four logs contain **0 WRN, 0 ERR** [meas] (`results/cli_crosscheck.json`).

## 3. Results on the HEISVERKET loop [meas]

**Component product from the topology curves:** η_prod(a) = η_turb(a)·0.96·η_pump(a)·0.97. The maximum is η_prod(0.5) = **0.78817**.

HERSS's numbers satisfy η_rt = η_prod(a)·Hnetto_station/Hnetto_pump on every valid protocol-A cell, to 7e-16. So the efficiencies are exactly the topology's, and the **only** thing that can push η_rt above η_prod is the head ratio.

**Maximum η_rt:**

| Case | η_rt | a | SKYFONNA U | TROLLDAMMEN L | E_in MWh | E_out MWh | Excess MWh |
|---|---|---|---|---|---|---|---|
| Clean, zero inflow, A (refined) | **1.025504** | 0.50 | 288.000 (= LRW) | 221.000 (= HRW) | 5.730631 | 5.876782 | **+0.146152** |
| Same, protocol B | 1.025395 | 0.50 | 288.000 | 221.000 | 5.731961 | 5.877527 | +0.145566 |
| Verbatim inputs incl. inflow, A (refined) | **1.024895** | 0.50 | 288.000 | 220.953 (fill 0.998) | 5.734440 | 5.877201 | +0.142761 |
| Strictly interior cell, clean, A | 1.021321 | 0.50 | 288.52 (fill 0.01) | 220.76 (fill 0.99) | 5.767475 | 5.890445 | +0.122970 |

**Heads at the maximum:**
- Station: Hbrutto 93.000 = 288 − 195; Hnetto 90.469.
- Pump: Hbrutto 67.000 = 288 − 221; Hnetto 69.531.
- The 26.0 m gap in gross head is exactly L − POWSTAT_MASL = 221 − 195.

**Cells above 1.0:**
- Coarse grid, clean + zero inflow: **34 of 15,540 valid cells**, all with a ∈ {0.45, 0.50, 0.55} and L at or near HRW.
- Refined corner box: 1,429 of 17,661.

A different, larger statistic matters more: η_rt > η_prod(a) in **71.6 %** of valid cells on the verbatim inputs and 72.8 % in the clean case. With the tailwater referenced to the actual lower level, that is impossible: turbine net head < U − L < pump net head.

**Correction to my own earlier number:** the coarse verbatim-input sweep reported a maximum of only 1.0084. That was a grid artefact. With inflow and routed water, a start fill of 1.0 overflows TROLLDAMMEN, so those cells were rejected, and the next grid point (0.95) is 1.19 m lower. Refining the fill between 0.90 and 1.0 in steps of 0.002 recovers 1.0249.

## 4. Mechanism tests

1. **Datum [meas].** In `fabel_datum221` the only change is HEIMFOSS `POWSTAT_MASL` 195.0 → 221.0 (TROLLDAMMEN HRW). Everything else is identical.
   - Maximum η_rt = **0.73337** over 15,200 valid cells.
   - **0** cells above 1.0, and **0** cells above η_prod(a).
   - At the exact state of the maximum: 0.73083, with station Hbrutto 66.9997 against pump Hbrutto 67.000.
   - The excess disappears completely, and η_rt falls below the component product everywhere. The datum is the mechanism.
2. **Noise [meas].**
   - The excess is 0.146 MWh on 5.73 MWh, i.e. 2.55 % relative. That is ≈ 1e14 times double-precision epsilon, and 26 m of head.
   - Every sweep cell reproduced bit-for-bit on a second `Simulate()`.
   - The CLI file path through float32 input parsing gives the same η to 3e-6.
3. **Inflow [meas].**
   - With natural inflow and routed channel water present (verbatim), the refined maximum is 1.024895.
   - With all natural inflow zeroed, channel start volumes zeroed and SKYFONNA auto-qmin disabled, it is 1.025504.
   - **97.6 % of the excess survives removing inflow.** Inflow slightly *reduces* the excess, because it raises TROLLDAMMEN during the step, which increases the pump's lift.
   - Inflow's main effect was indirect: it made the L = HRW corner spill, so a coarse grid missed it.
4. **Edge [meas + inf].**
   - Along a, the maximum is interior: 1.0255 at 0.50 against 1.0045 at 0.45 and 1.0090 at 0.55. The step-0.005 refinement also peaks at 0.500. This matches the kinks in both efficiency curves at Qn = 0.5.
   - Along the levels, the maximum **is on the edge** of the operating box: SKYFONNA at LRW and TROLLDAMMEN at HRW. This is expected, not an artefact [inf]. η_rt = η_prod·(U − 195 − kQ²)/(U − L + kQ²) increases as U falls and L rises. The edge is the physical regulation limit: below LRW the LRW penalty applies, and above HRW water spills.
   - The excess is not confined to the edge:
     - a strictly interior cell (fill 0.01 / 0.99) gives 1.0213;
     - the refinement has 1,429 cells above 1 on an open region;
     - on the verbatim inputs, 4 of the 6 coarse cells above 1 are strictly interior.

**Side findings, unrelated to the claim, recorded as research risks:**
- (a) With zero inflow and SKYFONNA starting exactly at LRW, HERSS flags an "aggressive action" and zeroes HEIMFOSS in 231 cells.
  - Cause [meas]: `(filling_at_lrw + pumped) − filling_at_lrw` rounds to below `pumped` by ~1e-16 Mm³, which trips `Q_Mm3 > up_res_Mm3` (`powerstation.cpp:805`).
  - I recomputed the comparison in C++; it reproduces each recorded cost exactly (1000 × excess).
  - Whether the station runs at U = LRW therefore depends on floating-point round-off.
  - These cells were excluded.
- (b) There is an HRW clamp on the station head but not on the pump head (§1).

## 5. Verdict

**Confirmed, with qualifications.**
- HERSS measures a turbine's drop down to a fixed elevation (`POWSTAT_MASL`) but a pump's lift between the two real water surfaces. In fabelvassdraget, HEIMFOSS's fixed elevation (195 m) is below the lowest regulated level of the reservoir it discharges into (TROLLDAMMEN, 196–221 m). So whenever water goes around the HEISVERKET → HEIMFOSS loop, the turbine is credited with more drop than the pump paid for.
- Measured independently: pumping 7.5 m³/s up and running the same 7.5 m³/s back down in the same hour costs 5.7306 MWh and returns 5.8768 MWh, a round trip of 1.0255. This is at the extreme corner of the operating range (upper reservoir at its minimum, lower at its maximum). With the dataset's own inflows it is 1.0249.
- Raising only the station's fixed elevation to the lower reservoir's top level removes the effect entirely. The round trip then never exceeds 0.733, below the machines' own efficiency product of 0.788.
- It is not rounding noise, it is not caused by inflow, and HERSS logs no warning while it happens.

**Qualifications:**
- (i) Outright energy creation (η_rt > 1) only happens in a small corner of the state space, at the efficiency-optimal flow. The broader and more important symptom is that η_rt exceeds the physically possible η_prod in about 72 % of all operating states.
- (ii) The effect needs two things together:
  - a **code** property: no tailwater coupling, and no check of `POWSTAT_MASL` against the downstream reservoir;
  - a **data** choice: this fictional dataset puts the datum below the lower reservoir's LRW.
- (iii) Profit depends on it too [src + inf]. A pump and a station running in the same hour pay and earn the same price (`pump.cpp:298`, `powerstation.cpp:210`). A simultaneous loop therefore earns price × excess, positive at any positive price, minus start/stop costs.
  - Arithmetic from the measurement: about 3.5 EUR/h at 24 EUR/MWh.
  - Against that, one start-and-stop cycle costs 2.5 EUR for the pump and 3 × 1.5 EUR for HEIMFOSS's three generators (`powerstation.cpp:275-276`, charged per generator). So the loop pays off after about two hours of continuous running.
  - This is an inference; I did not run an optimiser.

## 6. Comparison with the earlier reports

*(Written after reading them. §0–§5 above were fixed before this point. First opened: `analysis/r1_loop/R1_LOOP_REPORT.md`, `part5_fabelvassdraget.py` and `analysis/pump_audit/PUMP_AUDIT_REPORT.md`, at 2026-09-28T17:38 local, after `REPORT.md` §0–§5 had been saved.)*

**Their numbers reproduce [meas].**
- `R1_LOOP_REPORT.md` §5.2 reports HEISVERKET η_rt = **1.0256**, MWh in 5.7319, out 5.8788, at a_pump 0.50, SKYFONNA at LRW, TROLLDAMMEN at HRW. The protocol is sequential, identical to my protocol B, with no inflow override.
- My protocol B on that exact cell and inputs (`results/sweep_base.csv`: B, a 0.5, fill 0.0/1.0) gives **1.025628**, in 5.731874, out 5.878772. That agrees with every digit they print.

**But their headline cell fails my acceptance check [meas].**
- With the dataset's own inflow and routed channel water, TROLLDAMMEN **spills during that cycle**: 0.066 m³/s at t=0 and 0.667 m³/s at t=1.
- `part5_fabelvassdraget.py:roundtrip` checks volume match and log warnings, but not overflow, and does not isolate inflow.
- So the cell they report is not a clean closed loop. This is exactly the kind of shared protocol error this check was set up to find.
- **It does not change the conclusion.** The fully isolated cell (no spill, no inflow, no routed water, no auto-qmin) gives 1.025504 (A) / 1.025395 (B). The best spill-free cell with verbatim inputs gives 1.024895. The error moves η_rt by about 1e-4.
- **I trust my numbers** for the headline because every reported cell passes explicit spill, inflow, clip, aggressive-action, warning and determinism checks, and because the CLI file path confirms them. The earlier 1.0256 should be restated as "≈ 1.025, measured on a spill-free, inflow-free cell".

**Mechanism and fix agree.** R1_LOOP_REPORT's "guaranteed-safe" rule `POWSTAT_MASL ≥ HRW(lower)` is exactly my §4.1 test. On this dataset it gives 0 cells above η_prod, which confirms their claim for fabelvassdraget. I did not test their other geometries.

**Closed form [inf].**
- Their η_rt = η_prod·(U−P)/(U−L) was verified to 1.1e-16 on frictionless synthetic instances.
- On fabelvassdraget, with non-zero HEADLOSSCOEF, it is only an upper bound; they say so in §5.3.
- The exact identity on this dataset is with *net* heads, which I verified to 7e-16. Not a disagreement, but only the net-head form should be quoted as "exact".

**A real disagreement, and an important one: `PUMP_AUDIT_REPORT.md` R1 mitigation (lines 632-640) is wrong-signed.**
- It recommends "`POWSTAT_MASL ≤ LRW(source reservoir)` and ideally `POWSTAT_MASL = LRW(source)`". For a pump the source reservoir is the *lower* one.
- A datum at or below the lower reservoir's LRW is precisely what over-credits the turbine. That is fabelvassdraget's configuration (195 ≤ 196), and it produces η_rt > η_prod in ~72 % of states and η_rt > 1 at the corner (§3).
- R1_LOOP_REPORT later replaced this with `≥ HRW(lower)` (§1 item 3) but never explicitly withdrew the audit's version. **The audit's R1 mitigation must not be sent to the HERSS author as written.**

## 7. Is the measured loop actually closed? Runtime verification (added 2026-09-28, after §6)

Checked from HERSS's runtime state only, not from `topology.txt` (`verify_closed_loop.py`, `results/closed_loop_check.json`) [meas]:

- **Step length:** HERSS uses `getDeltaT(t)` = `S->dt` = 3600 s for pump 0 and nodes 10, 13 and 14. `Herss::dt` is an unused member (9999999) and must not be used.
- **T1, wiring as loaded:**
  - pump 0 `ptr_pump_source` = 14 and `ptr_pump_target` = 10;
  - SKYFONNA's tunnel outlet points to node 13;
  - HEIMFOSS `ptr_downstream_node` = 14.
  - Scanning every node's runtime outlet pointers: nothing feeds SKYFONNA except the pump. Nodes 9, 11 and 13 feed TROLLDAMMEN.
- **T2, water balance per reservoir and step**, with every in/out term HERSS records (inflow, up_inflow, pump in/out, tunnel, hatch, overflow, auto-qmin):
  - The residual is 0 (protocol A) or ≤ 1e-15 Mm³ (protocol B).
  - In the reported cells the only non-zero flows are: SKYFONNA pump_in 7.5 and tunnel 7.5; TROLLDAMMEN pump_out 7.5 and up_inflow 7.5.
  - TROLLDAMMEN's up_inflow minus HEIMFOSS's outflow is exactly 0, so channels 9 and 11 contribute nothing.
- **T3, closure:** in all three reported cells (A max, B max, A interior), both reservoirs end the cycle at *exactly* the start volume: SKYFONNA 5.811386394059 Mm³ and TROLLDAMMEN 80.981445420187 Mm³ at the max cell, with Δ = 0.
- **T4, knock-out** at fill 0.5/0.5, a = 0.5:

| Case | ΔSKYFONNA | ΔTROLLDAMMEN |
|---|---|---|
| none | 0 | 0 |
| pump only | +0.027 | −0.027 |
| station only | −0.027 | +0.027 |
| both | 0 | 0 |

  All values are in Mm³, with 0 overflow and 0 warnings. The pump moves water 14→10 and the station moves it 10→14. Together they cancel.
- **T5, head sources:** HERSS's pump Hbrutto (67.000) equals the average level of node 10 minus the average level of node 14, from the reservoir arrays. HERSS's station Hbrutto (93.000) equals the average level of node 10 minus 195. If the station used the same tailwater as the pump, its Hbrutto would also be 67.000.

So the headline cells are a volume-closed loop between exactly these two reservoirs. Qualification: HERSS models reservoirs as lumped volumes and does not track individual water parcels, so "the same water" means "the same volume, between the same two reservoirs". The verbatim-inflow cell (1.0249) is *not* strictly closed: natural and routed inflow also enter both reservoirs. Only the loop flows match there.

## Files

| File | Content |
|---|---|
| `harness.py` | cppyy harness, by-value accessors, init order, input setters |
| `sweep.py` | coarse sweep, protocols A and B, per-cell acceptance flags |
| `analyse.py` | decomposition check, interior/edge analysis, refinement (clean, zero inflow) |
| `refine_base.py` | refinement with verbatim inputs; aggressive-action round-off check |
| `cli_crosscheck.py` | `herss.exe` + output files for four cells |
| `fabel_base/`, `fabel_datum221/`, `fabel_clean/` | dataset copies (T = 2), with the diffs described in `run_meta.json` |
| `results/summary_*.json`, `results/analysis.json`, `results/refine_base.json`, `results/cli_crosscheck.json` | numbers quoted above |
| `results/sweep_*.csv`, `results/refine_*.csv` | every cell, including the rejected ones (~60 MB total; regenerate rather than commit) |
| `run_meta.json` | commit, binary hashes, version, grids |

Reproduce: from this directory, build as in `run_meta.json`, then run
`../../.venv/bin/python sweep.py fabel_base base`. Likewise run `fabel_datum221 datum221`, `fabel_base base_noinflow --zero-inflow`, `fabel_clean clean_noinflow --zero-inflow`, `fabel_clean clean`, and `fabel_datum221 datum221_noinflow --zero-inflow`. Then run `analyse.py`, `refine_base.py` and `cli_crosscheck.py`. The whole set takes under a minute.
