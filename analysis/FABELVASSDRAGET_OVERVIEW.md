# `data/fabelvassdraget` — dataset overview

Purpose of this note: a self-contained description of the `fabelvassdraget` dataset for
sessions that don't have the pump-related analysis history in context. Everything under
"Facts" is read directly from the files in `data/fabelvassdraget/` (checked 2026-09-28) or
from prior verified analysis in `analysis/pump_audit/` and `analysis/r1_loop/`, which are
cited explicitly. Everything under "Interpretation" is this author's reading and is labelled
as such.

**Do not confuse this with the other shipped datasets.** It is the only large system built to
exercise the `PUMP` node, and it is where the pump/head-datum defect (`R1`, see below) was
actually found — not a synthetic instance constructed to provoke it.

---

## 1. What it is (fact)

- **Provenance.** `topology.txt` and `global.txt` header comments: authored by Terje Sandø,
  "pump-station work, July 2026," `global.txt` adds "in collab with Claude." Explicitly
  labelled **fictional** — "invented names, not modelled on any real river system" — unlike
  the other shipped datasets, whose provenance is not stated in-file (this repo's docs don't
  say uTAHPS or res_casc are real either; the difference is that fabelvassdraget says outright
  that it *isn't*).
- **Stated purpose** (`topology.txt` header): "a large, richly-connected stress test for the
  new PUMP node type, exercising `RESERVOIR_GEOMETRY` (not `RESERVOIR_CURVE`), `SPILLWAY`
  (not `OVERFLOW_CURVE`), `UNIFORM_NORMALIZED_CURVE` (not `TURBINE_CURVE`/`PUMP_CURVE`),
  multiple generators per powerstation, seasonal `OUTLET_AUTO_QMIN` together with a downstream
  `CHANNEL QMIN` shifted +2 days."
- **Scale.** 19 nodes, 72 hours, hourly resolution (`global.txt`, `actions.txt` row count).
  `VERSION 4.0.00`, `VERSION_DATE 20260814` (log file
  `herss_4.0.00_20260814.log`).
- **Files present:** `topology.txt`, `global.txt`, `start_state.txt`, `inflowseries.txt`,
  `pricefile.txt`, `actions.txt`, a shipped `output/` directory from a completed run, and a
  stray `.topology.txt.swp` (an untracked vim swap file — worth deleting, not a data file).

## 2. Topology (fact, read from `topology.txt`)

19 nodes: 2 `PUMP`, 6 `RESERVOIR`, 4 `PSTATION`, 7 `CHANNEL`.

```
DUGGTJERN(2)──hatch/spillway──> DUGGBEKKEN(5,chan) ─┐
SKYTRONA(3)──tunnel──> TORDENFOSS(4,PSTA,2gen) ──────┼─> KLARVIK(6)
SKYTRONA(3)──hatch/spillway──> SKYRENNA(7,chan) ────┐│
KLARVIK(6)──hatch/spillway──> KLARELVA(8,chan) ─────┼┴> SAMLOPET(9,chan) ─┐
                                                                          │
SKYFONNA(10)──tunnel──> HEIMFOSS(13,PSTA,3gen) ──────────────────────────┼─> TROLLDAMMEN(14)
SKYFONNA(10)──hatch/spillway──> FONNBEKKEN(11,chan) ─────────────────────┘
SKYFONNA(10)──auto_qmin──> SALTBEKKEN(12,chan) ──────────────────────────> SALTVIKA(16)

TROLLDAMMEN(14)──tunnel──> DYPFALL(15,PSTA,2gen) ─────────────────────────> SALTVIKA(16)

SALTVIKA(16)──tunnel──> TIDEVERK(17,PSTA,2gen) ──> MUNNINGEN(18,chan) ──> sea (-9)

# the two closed pump loops, against the gravity flow above:
HEISVERKET(0,PUMP):  TROLLDAMMEN(14) --pump--> SKYFONNA(10)   [reverses HEIMFOSS/FONNBEKKEN]
OPPLOFT(1,PUMP):     SALTVIKA(16)    --pump--> TROLLDAMMEN(14) [reverses DYPFALL]
```

`TROLLDAMMEN` is the confluence node: fed by two channels (`SAMLOPET`, `FONNBEKKEN`), one
power-station tailrace (`HEIMFOSS`), and one pump (`OPPLOFT` target), and itself feeds one
power station (`DYPFALL`) and one pump (`HEISVERKET` source). No other reservoir in the system
has that many roles at once. Reservoir head ranges (`HRW`/`LRW`, masl): DUGGTJERN 1110–1125,
SKYTRONA 970–1030, KLARVIK 195–211, SKYFONNA 288–308, TROLLDAMMEN 196–221, SALTVIKA 13–23 —
i.e. a full alpine-to-sea drop in one topology.

## 3. How it differs from every other shipped HERSS dataset (fact, cross-checked against `data/*/topology.txt`)

| dimension | fabelvassdraget | rest of `data/` |
|---|---|---|
| `PUMP` nodes | 2 (`HEISVERKET`, `OPPLOFT`), forming 2 closed loops | none, except the unrelated minimal fixture `data/mini_pump_test/` (1 pump, 8 nodes, no loop) |
| Reservoir shape | `RESERVOIR_GEOMETRY` (`WIDTH_M`/`LENGTH_M`/`THETA`/`BOTTOM_MASL`) on all 6 reservoirs | `RESERVOIR_CURVE` (tabulated) on `res_casc_A/B/D`, `mini_utahps_daily/hourly`; `RESERVOIR_GEOMETRY` only on the newer `mini_utahps_new_inputformat`/`qmin`/`spillway` and `res_casc_C` |
| Overflow | `SPILLWAY` (physical weir: discharge coefficient, crest length, crest level) | `OVERFLOW_CURVE` (tabulated) everywhere except `mini_utahps_spillway` |
| Generator/pump efficiency | `UNIFORM_NORMALIZED_CURVE` (one normalized 0–1×Qmax curve, in %, applied uniformly) on every machine, pumps included | `TURBINE_CURVE` on the `res_casc`/`utahps` family; `UNIFORM_NORMALIZED_CURVE` also appears on `mini_utahps_spillway` and `mini_pump_test` |
| Generators per station | 2 or 3, `SHARED_PENSTOCK TRUE` (`TORDENFOSS`, `DYPFALL`, `TIDEVERK` = 2; `HEIMFOSS` = 3) | mostly `NR_GENERATORS 1`; `res_casc_A` has 2 |
| `OUTLET_AUTO_QMIN` × downstream `CHANNEL QMIN`, deliberately offset | yes, and the offset is exactly +2 days in both places it applies (see §4) | not combined this way elsewhere in `data/` |
| `LOCAL_ENERGY_EQUIVALENT` spread | 1.9448 (`TORDENFOSS`, high alpine head) down to 0.0417 kWh/m³ (`TIDEVERK`, near-sea-level) — a ~47× spread inside one system | single-basin datasets typically span a narrower head range |
| Horizon | 72 h @ 1 h | daily-resolution datasets run much longer; the other hourly set (`mini_utahps_hourly`) is a single basin, no pumps |

The practical upshot: **fabelvassdraget is the only dataset in this repo where a pumped-storage
round trip is even representable**, and therefore the only one where the pump/head-datum
defect below is observable at all. Every unidirectional cascade (`res_casc_*`, `utahps_*`,
`mini_utahps_*`) is structurally immune to it, not because it was fixed, but because those
datasets have no pump to exploit it with.

## 4. The `OUTLET_AUTO_QMIN` / `CHANNEL QMIN` +2-day offset (fact)

Verified by direct comparison of dates in `topology.txt`:

- `DUGGTJERN` (`RESERVOIR 2`) `OUTLET_AUTO_QMIN` periods: `01.05`–`30.09` and `01.10`–`30.04`.
  Its downstream channel `DUGGBEKKEN` (`CHANNEL 5`) `QMIN` periods: `03.05`–`02.10` and
  `03.10`–`02.05` — each boundary shifted **+2 days** later.
- `SALTVIKA` (`RESERVOIR 16`) `OUTLET_AUTO_QMIN` periods: `29.04`–`28.09` and `29.09`–`28.04`.
  Its downstream channel `MUNNINGEN` (`CHANNEL 18`) `QMIN` periods: `01.05`–`30.09` and
  `01.10`–`30.04` — again **+2 days**.

This matches the stated intent in both `topology.txt` and `global.txt`: the channel's
seasonal minimum-flow window is deliberately lagged behind the reservoir's, "to account for
the asymptotic lag of cascaded-linear-reservoir routing." It is a deliberately realistic
touch, not an inconsistency — but per CLAUDE.md §9, `OUTLET_AUTO_QMIN` is only partially
implemented and channel `QMIN` time-period parsing is incomplete, so this pairing sits
directly on two of the features flagged as not quality-controlled. **Interpretation:** if this
dataset is ever used for anything beyond stress-testing the pump node, both QMIN mechanisms
should be verified numerically before trusting their cost accounting, not just their parsing.

Also present on every reservoir: `FLOODLEVEL_PENALTY 300`. Per CLAUDE.md §9 this parameter is
read from the topology file but **never applied in simulation** — so it sits in every
`NODE RESERVOIR` block in this file but is inert. Worth knowing if anyone reads the topology
file and assumes it does something.

## 5. The pump loops and the known defect (fact, citing prior analysis — not re-derived here)

Two closed loops exist, both against the direction of gravity flow:

| loop | lower reservoir (L) | upper reservoir (U) | `POWSTAT_MASL` of the downhill station | rule requires ≥ | violated by |
|---|---|---|---|---|---|
| `HEISVERKET`(pump 0) / `HEIMFOSS`(gen) | `TROLLDAMMEN` 196–221 | `SKYFONNA` 288–308 | 195.0 | `HRW(TROLLDAMMEN)`=221.0 | 26 m |
| `OPPLOFT`(pump 1) / `DYPFALL`(gen) | `SALTVIKA` 13–23 | `TROLLDAMMEN` 196–221 | 20.0 | `HRW(SALTVIKA)`=23.0 | 3 m |

This table and the safe-placement rule (`POWSTAT_MASL ≥ HRW(lower reservoir)`) come from
[`analysis/r1_loop/R1_LOOP_REPORT.md`](r1_loop/R1_LOOP_REPORT.md) §5, which audited this exact
dataset (not a purpose-built instance) as its "does the rule hold on someone else's file"
check, run via `analysis/r1_loop/part5_fabelvassdraget.py` against `inst_fabel/`, a verbatim
copy of `data/fabelvassdraget`.

**Both loops violate the rule.** Measured round-trip efficiency (`eta_rt` = energy out ÷
energy in, pump then generate an identical volume back, everything else in the system held at
zero):

- `HEISVERKET` loop: **`eta_rt` up to 1.0256** — i.e. **2.56% more energy out than in**, at
  `a_pump=0.50`, `TROLLDAMMEN` near `HRW`, `SKYFONNA` near `LRW`. This is energy creation from
  a physically-impossible round trip, not a rounding artefact: `gc.Diagnose()`,
  `gc.checkNrSteps()`, and `DiagnoseRiversystemConfiguration()` all pass, and the HERSS log
  shows zero warnings across the run.
- `OPPLOFT` loop: `eta_rt` up to 0.7032 — below 1.0 (no energy creation), but still above the
  0.373 the loop's `R_L/D` geometry alone would suggest as safe, because of the same unsafe
  `POWSTAT_MASL` placement.

Root cause (per the same report, §3): `POWSTAT_MASL` is documented as "turbine centreline
elevation," but the physically-correct placement is *not* the intuitive one — the datum needs
to sit at or above the lower reservoir's `HRW`, not at the real centreline. `HEIMFOSS` is
placed at 195.0, one metre *below* `LRW(TROLLDAMMEN)=196`, the single worst placement class
the report measured. A prototype fix (`TAILWATER_IDNR`, on branch `r1-fix-prototype`) exists
but is not merged into `src/`; per CLAUDE.md this repo does not modify `src/` and any such fix
is upstream's to own.

**Interpretation, not in the cited report:** this means any optimizer given free rein over the
`HEISVERKET`/`HEIMFOSS` loop's actions in this dataset, evaluated by HERSS's own objective,
can extract positive expected value from cycling water through it even at a flat electricity
price, with no arbitrage spread required — a pure simulator artefact, not an economically
meaningful strategy. If this dataset (or any dataset with a similarly-placed pump loop) is
ever used as a benchmark instance rather than a pump-node stress test, this loop must either be
excluded from the action space, repaired (`POWSTAT_MASL := HRW(lower reservoir)`), or the
result must explicitly flag which fraction of reported value comes from it — otherwise a
reported "solution quality" number is not measuring what it claims to.

## 6. Behaviour of the shipped run (fact, from `output/riversystem_FABELVASSDRAGET_output.txt` and `output/reservoirs_FABELVASSDRAGET_out.txt`)

The checked-in `output/` directory is a completed 72 h run against the shipped `actions.txt`,
`start_state.txt`, `inflowseries.txt`, `pricefile.txt` (log timestamp 2026-09-21, `VERSION
4.0.00`).

- **Water balance closes:** `start_water_Mm3=425.372594`, `inflow=7.257600`,
  `outflow=11.211054`, `end_water=421.419140`, `waterbalance=-0.000000`.
- `Sum_Production_MWh = 10474.078`, `Sum_Pump_Consumption_MWh = 1551.591` — this is the only
  shipped dataset where that second line is nonzero.
- `sum_startstopcost_Euro = 37.250`, `sum_qmin_cost_Euro = 43.000`,
  `sum_aggressive_actions_cost = 0.000`, `sum_lrw_cost_Euro = 0.000`,
  `sum_max_adjustment_cost = 0.000` — soft-constraint costs are present but small next to
  `tot_profit_Euro = 307557.042`.
- `valuefunction_Euro = 19,688,679.590`, versus `tot_remaining_Euro = 19,381,122.548` — as
  CLAUDE.md §7 predicts generally, the terminal water-value term dominates total value on this
  instance too (remaining water valuation is ~63× the in-horizon profit).
- **The shipped `actions.txt` pumps through the local price trough and generates through the
  peak that follows.** First 24 h check: price falls `24.00 → 13.00` over hours 0–4 (trough at
  h4), `OPPLOFT` pumps at 0.70 through exactly those hours then stops; `HEISVERKET` then pumps
  at 0.60 through hours 5–8 as price climbs back `13.75 → 24.00`; both pumps are off from hour
  9 as price keeps climbing toward its hour-16 peak of 57.00. This is textbook pumped-storage
  arbitrage — plausible operator behaviour, not an attempt to exploit the loop above (the
  activated loop, `OPPLOFT`, is the one with `eta_rt < 1`; the exploitable loop is
  `HEISVERKET`, and it is not run anywhere near the `a_pump≈0.5`, `TROLLDAMMEN`-near-`HRW`
  region that the audit found the exploit in).

## 7. Practical notes for using this dataset

- `.topology.txt.swp` in the directory is a leftover vim swap file, not tracked input — safe
  to ignore or delete, but not this session's call without owner sign-off (CLAUDE.md §4: no
  deletions without explicit reason and approval — flagging it here instead).
- To experiment against this dataset without touching `data/`, copy it into an `analysis/`
  subdirectory first, as `analysis/r1_loop/part5_fabelvassdraget.py` already does via
  `inst_fabel/`. Per CLAUDE.md's `.gitignore` trap (line 26, `data/*`), anything new placed
  directly under `data/fabelvassdraget/` risks going untracked silently.
- If this dataset is ever pulled into the thesis's optimization benchmark set rather than kept
  as a pump-node stress fixture, treat §5 above as a go/no-go item for the `HEISVERKET` loop
  specifically, the same way §10 of CLAUDE.md treats the DP-vs-threshold gap for the main
  formulation.

---

*Sources: `data/fabelvassdraget/{topology,global,start_state,inflowseries,pricefile,actions}.txt`
and `data/fabelvassdraget/output/*` (read 2026-09-28); `analysis/r1_loop/R1_LOOP_REPORT.md` §§3, 5;
`analysis/pump_audit/PUMP_AUDIT_REPORT.md`; CLAUDE.md §§6, 7, 9.*
