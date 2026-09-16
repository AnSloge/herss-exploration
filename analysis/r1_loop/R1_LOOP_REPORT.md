# Does R1 actually bite? The pump-and-generate loop in HERSS

**Date:** 2026-09-16
**Repository commit:** `368f34fbfe7a3886b15e605a3a3e694e2f552405` (branch `system-design`)
**HERSS `VERSION` / `VERSION_DATE`:** `4.0.00` / `20260814`
**Predecessor:** `analysis/pump_audit/PUMP_AUDIT_REPORT.md`, risk **R1**
**Working tree:** nothing under `src/` or `data/` modified. All artefacts under `analysis/r1_loop/`.

---

## Verdict

**R1 is real, it bites in a closed loop, and it is *partly* removable — but not by the
placement a physicist would choose.**

Three findings, in order of importance:

1. **HERSS fully permits the closed loop, and ships one as its own pump example.** A pump
   `L → U` together with a station whose intake is `U` and whose outfall is `L` is expressible
   with no special effort, passes every diagnostic, and is exactly the topology of
   `src_tests/pump_test` and `data/mini_pump_test`. Nothing in `src/` forbids or warns about it.
   The manual never discusses the round trip at all.

2. **The loop's round-trip efficiency obeys a closed form, confirmed to 1.1e-16:**

   ```
   eta_rt  =  eta_pump * eta_motor * eta_turbine * eta_generator  *  (U - P) / (U - L)
   ```

   where `U` and `L` are the two reservoir surfaces and `P` is `POWSTAT_MASL`. The component
   product is recovered **only** where `L == P`. Everywhere else the model gains or loses
   energy, and `eta_rt > 1` — literal energy creation — whenever

   ```
   R_L / D  >  (1 - eta_prod) / eta_prod       with  D = LRW(U) - HRW(L),  R_L = HRW(L) - LRW(L)
   ```

   measured crossing between `R_L/D = 0.2564` and `0.2586` against a predicted `0.25753`
   for a realistic machine (`eta_prod = 0.79521`).

3. **The one placement rule that is *guaranteed* safe is `POWSTAT_MASL >= HRW(L)`** — the
   turbine datum at or above the lower reservoir's *highest* level. It caps `eta_rt` at
   `eta_prod` for every reservoir level in every geometry tested (residual `-5.3e-06` to
   `-6.4e-04`). Its price is a systematic **understatement** of recovered energy, bounded
   exactly by `R_L / (D + R_L)`: **2.9 % for a high-head PSH**, 10 % medium-head, 66 % for two
   mountain lakes at similar elevation.

A one-parameter edit to the fixture HERSS ships — moving `POWSTAT_MASL` from 70.0 to
`LRW(reservoir_B) = 60.0` — makes it return **`eta_rt = 1.2336`**, i.e. 23 % more energy out
than in, with every diagnostic passing and no warning logged.

**So, for this thesis:** if pumped storage is built on a **high-head** geometry
(`R_L/D` of a few percent) with `POWSTAT_MASL = HRW(lower reservoir)`, R1 becomes a
**statable simplification with a ≤ 3 % conservative bias** — declarable in the methods
chapter and defensible. If the design search is allowed to place two reservoirs at similar
elevations with deep drawdown, R1 is a **real defect** that produces round-trip efficiencies
of 2.34 and 6.47 in otherwise-legal topologies, and no choice of a fixed datum repairs it.

**The intrinsic part is unrepairable without a code change:** no constant `P` can track a
moving surface, so no placement makes `eta_rt == eta_prod` at every level. You get to choose
*which side* of the truth to sit on, not whether to be wrong.

---

## Part 1 — What HERSS permits, and what it documents

### 1.1 How the two node types are wired (from source, not the manual)

The pump and the station connect to reservoirs by completely different mechanisms, and
neither knows about the other.

**Pump → reservoirs.** `PUMP_SOURCE_IDNR` and `PUMP_TARGET_IDNR` are resolved in
`Herss::SetPointers` (`herss.cpp:388–411`) straight to `Node*`, then `Pump::Simulate`
(`pump.cpp:235, 239`) mutates `src->res_Mm3` and `tgt->res_Mm3` **directly**. Validation
(`Pump::ValidatePumpSettings`) requires only: both set, in range, not the pump itself, not
equal to each other, both of type `RESERVOIR`, and both idnrs strictly greater than the
pump's own.

**Station intake.** The station does *not* declare its intake. The **reservoir** declares
`OUTLET_TUNNEL <station_idnr>`, and `Reservoir::Simulate` pushes everything the station needs
into it (`reservoir.cpp:521–538`): `start_of_stp_masl`, `up_res_Mm3`, and the tunnel flow via
`GetTunnelFLow`. So a station's intake reservoir is whichever reservoir names it.

**Station outfall.** The station declares `DOWNLINK_IDNR` (`powerstation.cpp:383–385`), which
becomes `downstream_idnr` → `ptr_downstream_node`, and the turbined flow is added to that
node's `up_inflow` in `Powerstation::Simulate`.

**Consequence:** nothing anywhere cross-checks a pump's source or target against a station's
intake or outfall. The two mechanisms are independent.

### 1.2 Is the closed loop permitted? — Yes, and it needs no tricks

```
  0  PUMP pump_LU      PUMP_SOURCE_IDNR 3 (L)   PUMP_TARGET_IDNR 1 (U)
  1  RESERVOIR U       OUTLET_TUNNEL 2                -> station intake is U
  2  PSTATION sta_UL   DOWNLINK_IDNR 3                -> station outfall is L
  3  RESERVOIR L       OUTLET_HATCH 4 (shut), overflow -> 4
  4  CHANNEL elv -9
```

Built as `analysis/r1_loop/inst_loop/`. It loads, `gc.Diagnose()`, `gc.checkNrSteps()` and
`rs.DiagnoseRiversystemConfiguration()` all pass clean, and it simulates. A controlled round
trip moves `0.00720000 Mm³` up at `t=0` and `0.00720000 Mm³` down at `t=1` — identical to the
digit, i.e. demonstrably the same water.

The only ordering constraint is the pump's own numbering rule (`pump.idnr` below both source
and target), which the loop satisfies trivially. **There is no rule that forbids a station
from discharging into a pump's source reservoir.**

### 1.3 What is documented — the honest answer: nothing about the loop

The manual is clear that the pump *is* meant to be a pumped-storage facility:

> "A `PUMP` node, representing a Pumped Storage Hydropower (PSH) facility … since it moves
> water against the normal flow direction" — `doc/herss.tex:441`

> "The `PUMP` node models a PSH facility, which is mutch like a power staion node but in
> reverse. It lifts water from a source `RESERVOIR` to a target `RESERVOIR` while consuming
> electricity." — `doc/herss.tex:1115`

And `POWSTAT_MASL` is documented, unambiguously, as a **machine** elevation:

> "$h_\mathrm{turbine}$ is the turbine centreline elevation (`POWSTAT_MASL`) [masl]"
> — `doc/herss.tex:752`

But on the interaction between them, **the manual says nothing at all**:

- no discussion of round-trip efficiency anywhere (`grep -i "round.trip\|arbitrage\|closed loop"`
  in `doc/herss.tex`: zero hits);
- no guidance on where to place `POWSTAT_MASL` relative to the lower reservoir;
- no statement of whether pumping is intended for closed-loop storage arbitrage or only for
  inter-reservoir transfer feeding *different* stations.

**And yet the shipped example is a closed loop.** `src_tests/pump_test/topology.txt` and
`data/mini_pump_test/topology.txt` both wire pump source = `reservoir_B`, target =
`reservoir_A`, station intake = `reservoir_A`, station outfall = `reservoir_B`. The manual's
own figure (`fig:Pump_system`, "Schematic of the `Mini_pump_test` system") illustrates it.

**So: HERSS ships closed-loop pumped storage as its canonical pump example, and documents
neither the round-trip implication nor any placement rule.** That is itself the answer to the
question of intent — it is unspecified.

---

## Part 2 — Building the loop and measuring the round trip

Instance generator: `build_loop.py`. Both reservoir curves are exactly 1.0 Mm³/m; the pump's
`UNIFORM_NORMALIZED_CURVE` is flat; `HEADLOSSCOEF = 0` on both machines, so `Hnetto == Hbrutto`
and every number has a closed form. (The `TURBINE_CURVE` cannot be flat — `ArrayCurve`
hard-errors on `ydiff < 1e-4` — so it is built to hit its nominal efficiency exactly at
`Q = Qmax`, which is where every measurement runs.)

Protocol per measurement: pump one full step `L → U` at `t=0`, generate the identical volume
`U → L` at `t=1`, everything else shut. `eta_rt = e_out / e_in`, both from HERSS's own
`S->Power`.

### 2.1 Round-trip efficiency vs the lower reservoir's level

`U`: LRW 200, HRW 220, held at 210 masl. `L`: LRW 100, HRW 120.
`POWSTAT_MASL = 100.0 = LRW(L)` — a turbine centreline at the bottom of the lower reservoir's
range, i.e. **as a real turbine would sit**.
Components: `0.80 × 1.00 × 0.80 × 1.00 = 0.6400`.

| L masl | H_pump | H_turb | ratio | MWh in | MWh out | **eta_rt** | vs 0.6400 |
|---|---|---|---|---|---|---|---|
| 100.00 | 110.0072 | 110.0036 | 1.0000 | 2.69701 | 1.72603 | **0.6400** | 1.000× |
| 104.00 | 106.0072 | 110.0036 | 1.0377 | 2.59894 | 1.72603 | **0.6641** | 1.038× |
| 110.00 | 100.0072 | 110.0036 | 1.1000 | 2.45184 | 1.72603 | **0.7040** | 1.100× |
| 116.00 | 94.0072 | 110.0036 | 1.1702 | 2.30474 | 1.72603 | **0.7489** | 1.170× |
| 120.00 | 90.0072 | 110.0036 | 1.2222 | 2.20667 | 1.72603 | **0.7822** | 1.222× |

The energy *recovered* is constant (1.72603 MWh — the turbine only ever sees `U − P`, and `U`
barely moves). The energy *spent* falls as `L` rises, because the pump correctly sees a shorter
lift. Nothing corrects the turbine for the fact that it is now discharging into a higher pool.

**Closed form check:** worst `|eta_rt − eta_prod · H_turb/H_pump|` over the sweep =
**1.110e-16**. The relation is exact.

### 2.2 Round-trip efficiency vs `POWSTAT_MASL`

Same geometry, `L` swept across its whole 100–120 range for each datum:

| POWSTAT_MASL | placement | eta_rt @ L=LRW | eta_rt @ L=HRW | max over L | |
|---|---|---|---|---|---|
| 90.0 | below L (deep tailrace) | 0.6982 | 0.8533 | **0.8533** | exceeds 0.6400 |
| 100.0 | = LRW(L) | 0.6400 | 0.7822 | **0.7822** | exceeds 0.6400 |
| 110.0 | mid L's range | 0.5818 | 0.7111 | **0.7111** | exceeds 0.6400 |
| **120.0** | **= HRW(L)** | 0.5236 | 0.6400 | **0.6400** | **never exceeds** |
| 125.0 | above HRW(L) | 0.4945 | 0.6044 | **0.6044** | never exceeds |

`P = HRW(L)` is the **boundary case**: the first datum at which the loop never beats the
product of its component efficiencies, with equality only at the single level `L = HRW(L)`.

### 2.3 The fixture HERSS itself ships

`src_tests/pump_test`: `reservoir_A` LRW 90 / HRW 110, `reservoir_B` LRW 60 / HRW 75,
`POWSTAT_MASL = 70.0`. Components at `Q = Qmax`: `0.78 × 0.97 × 0.88 × 0.96 = 0.6392`.

| B masl | H_pump | H_turb | MWh in | MWh out | eta_rt |
|---|---|---|---|---|---|
| 60.009 | 41.2565 | 30.8392 | 0.00000 | — | *pump blocked by `PUMP_INLET_MASL 61.0`* |
| 61.036 | 40.3861 | 30.9256 | 25.12623 | 12.29798 | 0.4894 |
| 66.194 | 35.1927 | 30.9256 | 21.89515 | 12.29798 | 0.5617 |
| 69.623 | 31.7641 | 30.9256 | 19.76207 | 12.29798 | 0.6223 |
| 71.337 | 30.0498 | 30.9256 | 18.69552 | 12.29798 | 0.6578 |
| 74.765 | 26.6213 | 30.9256 | 16.56243 | 12.29798 | 0.7425 |

**The shipped fixture's round-trip efficiency varies by a factor of 1.517 across the lower
reservoir's range alone**, crossing the component product at `B ≈ 70 masl = POWSTAT_MASL`
exactly as the closed form predicts. It stays below 1.0 — but only because `POWSTAT_MASL = 70`
happens to sit 10 m *inside* `reservoir_B`'s range rather than at its LRW. Its geometry
(`D = 15 m`, `R_L = 15 m`, `R_L/D = 1.00`) is far above the `0.5645` energy-creation threshold
for its own efficiencies.

**Measured: the shipped fixture is one parameter away from free energy.** Taking the same
fixture and moving only `POWSTAT_MASL` from 70.0 to `LRW(reservoir_B) = 60.0` — the placement
the manual's "turbine centreline elevation" wording actively invites — and nothing else
(`inst_shipped_P60/`):

| reservoir_A | B masl | H_pump | H_turb | MWh in | MWh out | eta_rt |
|---|---|---|---|---|---|---|
| at HRW (fr 0.5) | 74.765 | 26.6213 | 40.9256 | 16.56243 | 16.27462 | 0.9826 |
| **at LRW (fr 0.0)** | 71.337 | 18.8178 | 29.7008 | 11.70752 | 11.81093 | **1.0088** |
| **at LRW (fr 0.0)** | 73.051 | 17.1035 | 29.7008 | 10.64098 | 11.81093 | **1.1099** |
| **at LRW (fr 0.0)** | 74.765 | 15.3893 | 29.7008 | 9.57444 | 11.81093 | **1.2336** |

A one-line edit to the shipped example turns it into a perpetual-motion machine returning
23 % more energy than it consumes, with a clean log and all diagnostics passing.

---

## Part 3 — Intrinsic, or an artefact of placement?

### 3.1 The energy-creation boundary, measured

Realistic machine: pump 0.90 × motor 0.98 × turbine 0.92 × generator 0.98 = **0.79521**.
Centreline at `LRW(L)` (physically correct placement). `R_L = 30 m` fixed, gap `D` swept.
Worst case over the envelope: `L` at HRW, `U` near LRW.

| R_L/D | H_pump | H_turb | MWh in | MWh out | eta_rt | |
|---|---|---|---|---|---|---|
| 0.1500 | 200.407 | 230.404 | 4.45652 | 4.07431 | 0.9142 | |
| 0.2000 | 150.407 | 180.404 | 3.34465 | 3.19014 | 0.9538 | |
| 0.2500 | 120.407 | 150.404 | 2.67753 | 2.65964 | 0.9933 | |
| 0.2564 | 117.407 | 147.404 | 2.61082 | 2.60659 | 0.9984 | |
| **0.2586** | 116.407 | 146.404 | 2.58858 | 2.58891 | **1.0001** | **energy created** |
| 0.2727 | 110.407 | 140.404 | 2.45516 | 2.48281 | **1.0113** | energy created |
| 0.3333 | 90.407 | 120.404 | 2.01041 | 2.12914 | **1.0591** | energy created |
| 0.5000 | 60.407 | 90.404 | 1.34329 | 1.59864 | **1.1901** | energy created |
| 1.0000 | 30.407 | 60.404 | 0.67617 | 1.06814 | **1.5797** | energy created |

Measured crossing: between `R_L/D = 0.2564` and `0.2586`.
Predicted: `(1 − 0.79521)/0.79521 = 0.25753`. **The criterion is confirmed.**

### 3.2 Is that reachable in a realistic design?

Centreline at `LRW(L)` throughout; worst case over the envelope:

| geometry | D [m] | R_L [m] | R_L/D | eta_rt worst |
|---|---|---|---|---|
| high-head PSH (Norwegian fjord type), U 1200–1230 / L 500–520 | 680 | 20 | 0.0294 | 0.8186 |
| medium-head PSH, U 800–830 / L 500–530 | 270 | 30 | 0.1111 | 0.8834 |
| two mountain lakes, deep drawdown, U 560–590 / L 500–540 | 20 | 40 | 2.0000 | **2.3386** |
| two mountain lakes, small gap, U 545–575 / L 500–540 | 5 | 40 | 8.0000 | **6.4675** |

The first two are safe from energy creation but still **overstate** round-trip efficiency by
2.9 % and 11.1 % relative at the top of `L`'s range. The last two are catastrophic — and they
are not contrived: two regulated mountain lakes a few tens of metres apart in elevation, each
with 40 m of drawdown, is an ordinary Norwegian configuration and is exactly the kind of thing
an automated river-system design search would propose.

### 3.3 Does a placement rule fix it?

**Rule: `POWSTAT_MASL >= HRW(lower reservoir)`.** Worst `eta_rt` over `L`'s whole range:

| geometry | P = LRW(L) | P = HRW(L) | eta_prod | residual |
|---|---|---|---|---|
| high-head PSH | 0.8186 | 0.7952 | 0.7952 | **−5.29e−06** |
| medium-head PSH | 0.8834 | 0.7952 | 0.7952 | **−1.33e−05** |
| two mountain lakes, deep drawdown | 2.3386 | 0.7951 | 0.7952 | **−1.75e−04** |
| two mountain lakes, small gap | 6.4675 | 0.7947 | 0.7952 | **−6.42e−04** |

The rule holds in **every** geometry, including the pathological ones: `eta_rt` never exceeds
the product of the component efficiencies. (The residual is slightly negative rather than
exactly zero only because the sweep's worst sample point is not exactly at `L = HRW`.)

**The price is a bounded understatement**, exactly `R_L / (D + R_L)`, realised when `L` sits at
its LRW:

| geometry | understates recovered energy by up to |
|---|---|
| high-head PSH | **2.9 %** (`20/700`) |
| medium-head PSH | **10.0 %** (`30/300`) |
| two mountain lakes, deep drawdown | **66.0 %** (`40/60`) |
| two mountain lakes, small gap | **87.7 %** (`40/45`) |

### 3.4 Is there a better rule? — a minimax datum, and why it is not safe

Centring the datum on `L`'s range halves the worst-case error, but gives up the guarantee:

| geometry | datum | eta_rt min | eta_rt max | max abs error vs eta_prod |
|---|---|---|---|---|
| high-head PSH | mid(L) = 510 | 0.7839 | 0.8069 | **1.47 %** |
| high-head PSH | HRW(L) = 520 | 0.7725 | 0.7952 | 2.86 % |
| medium-head PSH | mid(L) = 515 | 0.7555 | 0.8393 | **5.54 %** |
| medium-head PSH | HRW(L) = 530 | 0.7158 | 0.7952 | 9.98 % |
| two mountain lakes, deep drawdown | mid(L) = 520 | 0.5327 | **1.5669** | 97.04 % |
| two mountain lakes, deep drawdown | HRW(L) = 540 | 0.2703 | 0.7951 | 66.00 % |

`P = mid(L)` is the better *accuracy* choice for sensible geometries — but it permits
`eta_rt = 1.567` in the pathological one. **Only `P >= HRW(L)` is unconditionally safe.**

### 3.5 The intrinsic residual

No fixed `P` reproduces `eta_prod` at more than one level, because

```
eta_rt(L) = eta_prod * (U - P) / (U - L)
```

is level-dependent for every constant `P`. The full-range spread is fixed by the geometry alone:

```
eta_rt(L=HRW) / eta_rt(L=LRW)  =  (U - LRW_L) / (U - HRW_L)   -- independent of P
```

≈ 1.03 for the high-head case, 1.12 medium-head, 3.0 for the deep-drawdown lakes.
**That spread is the irreducible part of R1.** Choosing `P` only slides the whole curve up or
down; it cannot flatten it. Removing it would require the power station to use its downstream
reservoir's surface as its tailwater — a change in `src/powerstation.cpp`, out of scope here.

---

## Answer to the question asked

**R1 is removable by a statable placement rule, for the geometries this thesis should use —
and is a real defect outside them.**

Precisely:

- **The rule:** for every pump `L → U` whose water returns through a station discharging into
  `L`, set `POWSTAT_MASL = HRW(L)`. Combined with the pump audit's `HRW(L) < LRW(U)` (needed
  anyway to avoid the negative-head process abort), this guarantees `eta_rt <= eta_prod` at
  every reservoir level, in every geometry.
- **The residual under the rule:** recovered energy is understated by at most `R_L/(D + R_L)`,
  i.e. **2.9 % for a high-head PSH**, 10 % medium-head. The bias is one-directional
  (conservative: the model never invents energy), which makes it safe to declare.
- **The declaration for the thesis:** *"Generation head is measured to a fixed turbine
  centreline while pumping head is measured between water surfaces. With the centreline placed
  at the lower reservoir's HRW, this makes modelled round-trip efficiency conservative by at
  most R_L/(D+R_L) = 2.9 % on the instances used."* That is an ordinary, bounded, signed
  modelling simplification.
- **The boundary beyond which it stops being a simplification:** any instance where the lower
  reservoir's regulated range is comparable to the elevation gap between the reservoirs. At
  `R_L/D > (1 − eta_prod)/eta_prod ≈ 0.26` with a physically-placed centreline, the model
  creates energy outright.

**Therefore: pumped-storage arbitrage is safe to build on HERSS as-is only under a
hard-constrained topology.** An unconstrained design search over reservoir elevations and
`POWSTAT_MASL` is **not** safe — it has a free-energy exploit available with `eta_rt` up to
6.47, reachable through perfectly ordinary-looking inputs.

---

## Bugs, undocumented behaviour, open questions

**B1 — HERSS ships a closed-loop pumped-storage fixture and documents no placement rule.**
`src_tests/pump_test` and `data/mini_pump_test` are closed loops whose round-trip efficiency
varies 1.517× across the lower reservoir's range. Neither the fixture comments nor
`doc/herss.tex` mention this. Changing only `POWSTAT_MASL` from 70.0 to 60.0 — still a legal,
physically-motivated value — makes the shipped fixture return **`eta_rt = 1.2336`** (§2.3).

**B2 — nothing validates the pump/station datum relationship.** `ValidatePumpSettings`,
`ValidatePowerstationSettings`, `gc.Diagnose()` and `DiagnoseRiversystemConfiguration()` all
pass on `inst_g545_500_540`, which returns `eta_rt = 6.4675`. A cross-node check is possible
and cheap: if a station's `DOWNLINK_IDNR` reservoir is also some pump's `PUMP_SOURCE_IDNR`, and
that pump's target is the station's intake, then warn unless `POWSTAT_MASL >= HRW` of the
downlink reservoir.

**B3 — `POWSTAT_MASL` is documented as "turbine centreline elevation" (`doc/herss.tex:752`),
which invites exactly the unsafe placement.** A real centreline sits at or below tailwater; the
safe value here is at or above the lower reservoir's *highest* level. The physically-correct
reading of the parameter is the dangerous one.

**B4 — the energy-balance violation is silent.** No warning is emitted at any `eta_rt`. A
closed-loop instance can return `eta_rt = 6.47` with a clean log.

### Open questions for the HERSS lead developer

1. Is a power station discharging into a reservoir *intended* to use a fixed
   `POWSTAT_MASL`, or should its tailwater track that reservoir's surface? For conventional
   cascades the fixed datum is the standard simplification; in a pump loop it breaks energy
   balance. Is a `TAILWATER_IDNR`-style option wanted?
2. Should `ValidatePumpSettings` (or a new cross-node check) reject or warn on a pump/station
   closed loop whose `POWSTAT_MASL < HRW(lower reservoir)`?
3. Was the closed loop the intended use of `PUMP`, or was it meant only for inter-reservoir
   transfer feeding different stations? The shipped fixture says the former; the manual is
   silent. (Note: in the **non-loop** use — pump transferring between reservoirs that feed
   *different* stations — no round trip exists, so R1 does not arise and the fixed datum is
   just the ordinary conventional-hydropower simplification.)
4. Should `PUMP_INLET_MASL` and the lower reservoir's LRW be reconciled? In the shipped fixture
   `PUMP_INLET_MASL = 61.0` sits above `LRW(reservoir_B) = 60.0`, so the pump is blocked at
   `B_fr = 0` while the reservoir is still nominally within its operating range.

---

## Reproducing

```bash
cd analysis/r1_loop
../../.venv/bin/python build_loop.py        # writes inst_loop/
../../.venv/bin/python part2_roundtrip.py   # loop exists; sweeps over L and POWSTAT_MASL
../../.venv/bin/python part3_boundary.py    # energy-creation boundary; placement rule
../../.venv/bin/python part4_shipped.py     # the shipped fixture; minimax alternative
# inst_shipped_P60/ is the shipped fixture with POWSTAT_MASL 70.0 -> 60.0 (see 2.3)
```

Each writes a `part*_results.json`. Nothing under `src/` or `data/` is touched.
No test here needs an out-of-range action or a negative head, so no subprocess isolation was
required — every instance in this report simulates to completion.
