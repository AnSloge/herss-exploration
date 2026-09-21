# Fixed head datum vs. tracked tailwater — why R1 creates energy, and why tracking removes it

Companion to `R1_LOOP_REPORT.md` (the measurement of R1) and `R1_FIX_PROTOTYPE.md` (the scope and
risk verdict). This document is the *explanation*: what HERSS does today, why that lets a closed
pumped-storage loop produce more energy than it consumes, what the prototype changes, and why the
change is correct rather than merely convenient.

Numbers quoted here are measured, HERSS `4.0.00` / `20260814`, base commit `b6962f1`.
Labels follow CLAUDE.md §4: **[fact]** verified in source or measured, **[interp]** interpretation,
**[open]** unresolved.

---

## 1. The two head conventions HERSS uses today

A hydro machine's energy is `ρ · g · V · H`, where `H` is the height the water actually falls
(or is lifted). Everything below is about *what HERSS uses as the bottom of that height*.

### 1.1 The turbine: head down to a fixed elevation **[fact]**

`Powerstation::Simulate`, `powerstation.cpp:167` (base):

```cpp
Hbrutto = ((start_of_stp_masl + end_of_stp_masl)/2.0) - powstat_masl;
```

- `start_of_stp_masl`, `end_of_stp_masl`: the **intake** reservoir's water surface at the start and
  end of the timestep, pushed in by `Reservoir::Simulate` (`reservoir.cpp:521, 706`) and clipped at
  HRW. The average of the two is a mid-point estimate of the head over the step.
- `powstat_masl`: `POWSTAT_MASL` from the topology file. A **constant**. The manual calls it the
  turbine centreline elevation.

So the top of the drop moves with the reservoir, and the bottom never moves.

### 1.2 The pump: head between two moving surfaces **[fact]**

`Pump::CalcPowerAndCost`, `pump.cpp:268-272`:

```cpp
double src_avg_masl = (src_start_masl + src_end_masl) / 2.0;
double tgt_avg_masl = (tgt_start_masl + tgt_end_masl) / 2.0;
double Hbrutto = tgt_avg_masl - src_avg_masl;
```

Both ends are actual reservoir surfaces, averaged over the step the same way. Nothing is fixed.

### 1.3 Each is defensible alone; together they are inconsistent **[interp]**

For a single station discharging to a river, a fixed datum is a reasonable approximation: the
tailrace level barely moves. For a pump between two reservoirs, only moving surfaces make sense.
The problem appears when **the same body of water** is handled by both conventions. Then the
elevation the turbine drops *to* and the elevation the pump lifts *from* are different numbers for
the same physical water surface.

Potential energy only balances if both directions are measured against the same reference. HERSS
does not enforce that, and nothing in the code cross-checks a pump's source/target against a
station's intake/outfall **[fact, `R1_LOOP_REPORT.md`]**.

---

## 2. Before the change: how the loop creates energy

### 2.1 The wiring

```
        ┌──────────── reservoir U (upper), surface U ────────────┐
        │                                                        │
   pump lifts V                                            station releases V
   from L to U                                             from U down to ...
        │                                                        │
        └──────────── reservoir L (lower), surface L ────────────┘
                                   ▲
                       POWSTAT_MASL = P, a constant, may sit BELOW L
```

The pump's source is L and its target is U. The station's intake is U and its `DOWNLINK_IDNR` is L.
The same water goes up and comes back down. HERSS permits this and ships one as its canonical pump
example (`src_tests/pump_test`) **[fact]**.

### 2.2 The arithmetic

Move a volume `V` up and immediately back down, ignoring head loss for clarity:

```
energy in   = ρ g V (U − L) / (η_pump · η_motor)        the pump pays for the real lift, L → U
energy out  = ρ g V (U − P) · η_turb · η_gen            the turbine is paid for a drop to P
```

so

```
        η_rt = η_pump · η_motor · η_turb · η_gen · (U − P)/(U − L)
                └──────── η_prod ────────┘     └─ geometric amplifier ─┘
```

**[fact]** This closed form was confirmed against HERSS to 1.1e-16 in part 2 of the R1 report.

The amplifier is the whole problem:

- If `P = L`, it is 1, and `η_rt = η_prod`. Physically sound.
- If `P < L`, it is **greater than 1**. The turbine is credited with a fall of `(U − P)` while the
  water is actually deposited at `L`. The height `(L − P)` is paid for by nobody and produced by
  nothing. It is invented at the boundary between the two conventions.
- The lower reservoir moves, so `L` is not a constant. `P` is. The amplifier therefore *changes
  with reservoir level* — and it is worst exactly when `L` is high, i.e. when the pump has the
  least to pay and the turbine still claims the full drop to `P`.

Energy creation requires `η_prod · (U − P)/(U − L) > 1`. With the centreline at the lower
reservoir's LRW, `D = LRW(U) − HRW(L)` and `R_L = HRW(L) − LRW(L)`, this becomes the criterion from
the R1 report **[fact]**:

```
η_rt > 1   iff   R_L / D  >  (1 − η_prod) / η_prod
```

A deep-drawdown lower reservoir (large `R_L`) close in elevation to the upper one (small `D`) is the
dangerous combination.

### 2.3 Measured, on the part-2 instance

U held at 210 masl, L swept over its range 100–120, `POWSTAT_MASL = 100`, `η_prod = 0.64`:

| L surface [masl] | pump head [m] | turbine head [m] | `η_rt` |
|---|---|---|---|
| 100 (LRW) | 110.0 | 110.0 | 0.6400 |
| 110 | 100.0 | 110.0 | 0.7040 |
| 120 (HRW) | 90.0 | 110.0 | **0.7822** |

The turbine head is frozen at 110 m while the pump head falls to 90 m. Same water, same trip.

Push the geometry and it passes 1.0 **[fact, measured]**: `η_rt = 2.3386` for two mountain lakes
with deep drawdown, and `6.4675` for two lakes with a small elevation gap — against `η_prod = 0.79521`,
with every HERSS diagnostic clean and no warning logged.

### 2.4 Measured, on a real dataset

`data/fabelvassdraget`, HEISVERKET loop (TROLLDAMMEN ↔ SKYFONNA via HEIMFOSS), at `a_pump = 0.5`,
SKYFONNA at its LRW and TROLLDAMMEN full **[fact]**:

```
energy in  = 5.731873511274111 MWh
energy out = 5.878772468821576 MWh        η_rt = 1.0256
```

0.1469 MWh created per cycle, repeatable, with a free-energy machine available to any optimizer
that finds it. `POWSTAT_MASL` for HEIMFOSS is 195.0, one metre *below* TROLLDAMMEN's LRW of 196.

**[interp] Why this matters beyond pumping.** Even without a pump, a fixed datum means a station's
head does not fall as the reservoir it discharges into fills up. In a cascade that is an accuracy
error with a known sign. In a closed loop it becomes an arbitrage the objective function actively
rewards, which is what makes R1 a research risk rather than a modelling detail.

---

## 3. The change

### 3.1 What it does

A new, optional topology keyword inside a `NODE PSTATION` block:

```
TAILWATER_IDNR <reservoir_idnr>      # absent or negative → old behaviour, unchanged
```

When present, the bottom of the station's head is no longer the constant `POWSTAT_MASL` but the
named reservoir's **actual surface**, averaged over the timestep exactly as the intake is:

```
Hbrutto = (intake_start + intake_end)/2  −  (tailwater_start + tailwater_end)/2
```

This is the pump's convention, applied to the turbine. Both machines then measure the same water
surface the same way.

### 3.2 The obstacle: the tailwater level does not exist yet **[fact]**

`Herss::Simulate` runs nodes in ascending idnr order (`herss.cpp:729-745`). A station's downstream
reservoir must have a *higher* idnr, otherwise the station's
`ptr_downstream_node->S->up_inflow[t] += total_Q` would arrive after that reservoir had already
consumed its inflow for the step. Consequently, when the station computes its head:

- the tailwater reservoir's `res_masl` still holds the level at the **end of `t−1`** — usable as the
  start level;
- its **end-of-`t`** level does not exist yet, and cannot, because it depends on the discharge this
  station is computing right now.

So `(start + end)/2` cannot be evaluated inside `Powerstation::Simulate`. HERSS already solved this
problem once: the PUMP defers its head, power and cost to `Pump::CalcPowerAndCost(t)`, run after all
nodes have finished the step (`herss.cpp:747-752`), and the reservoirs push their start and end
levels into it through reverse lists (`reservoir.cpp:508-509, 714-715`). **The prototype copies that
pattern rather than inventing a new one.**

### 3.3 Where the changes were made

Four files, +62 / −5 lines, roughly a third of it comments.

| # | File | Location | Change |
|---|---|---|---|
| 1 | `src/herss.h` | line 173 | forward declaration `class Powerstation;` |
| 2 | `src/herss.h` | `class Reservoir`, after `ptr_pumps_as_target` | new reverse list `std::vector<Powerstation*> ptr_stations_as_tailwater;` |
| 3 | `src/herss.h` | `class Powerstation`, after `aggressive_actions_cost` | `tailwater_idnr`, `tailwater_in_use`, `tailwater_final_pass`, `tw_start_masl`, `tw_end_masl` |
| 4 | `src/powerstation.cpp` | constructor | initialise those five; `tailwater_in_use = false` is what makes the old path the default |
| 5 | `src/powerstation.cpp` | `Simulate`, the `Hbrutto` line | the datum becomes a local variable; it is the tracked average **only** when opted in *and* in the final pass |
| 6 | `src/powerstation.cpp` | `Simulate`, downstream push | guarded with `&& !tailwater_final_pass`, so the re-run cannot route the same water twice |
| 7 | `src/powerstation.cpp` | `ReadNodeData` | parse `TAILWATER_IDNR`; negative value = not in use |
| 8 | `src/reservoir.cpp` | `Simulate`, beside the pump start push | push `tw_start_masl` to registered stations |
| 9 | `src/reservoir.cpp` | `Simulate`, beside the pump end push | push `tw_end_masl` to registered stations |
| 10 | `src/herss.cpp` | `SetPointers` | validate the target is a RESERVOIR (`LOG_ERR` otherwise) and register the station on it |
| 11 | `src/herss.cpp` | `Simulate`, after the pump pass | re-run opted-in stations with `tailwater_final_pass = true` |

The two changes that carry the physics are #5 and #11. The rest is plumbing and safety.

**#5, the head itself:**

```cpp
double tailwater_masl = this->powstat_masl;
if (tailwater_in_use && tailwater_final_pass) {
    tailwater_masl = (this->tw_start_masl + this->tw_end_masl) / 2.0;
}
Hbrutto = ((this->start_of_stp_masl + this->end_of_stp_masl)/2.0) - tailwater_masl;
```

With the keyword absent this subtracts `powstat_masl`, the same operand in the same operation as
before — which is why every shipped dataset is bit-for-bit unchanged **[fact, measured on all 12]**.

**#11, the end-of-timestep re-run:**

```cpp
for(size_t p = 0; p < gc->nr_pstations; p++) {
    if(rs->pstations[p].tailwater_in_use) {
        rs->pstations[p].tailwater_final_pass = true;
        rs->pstations[p].Simulate(t);
        rs->pstations[p].tailwater_final_pass = false;
    }
}
```

The first call, inside the node loop, does the water: discharge, the aggressive-action rule, routing
downstream. Its head is provisional, and identical to today's. The second call recomputes head,
power, income and profit with the final tailwater, and overwrites every affected output field.

---

## 4. Why this is the correct treatment in a closed loop

### 4.1 The symmetry argument **[interp], confirmed by measurement**

Take the round trip: pump `V` from L to U in step 0, release the same `V` back in step 1, nothing
else happening. Write `ΔU` for the rise in U and `ΔL` for the drop in L.

**Step 0 (pumping).** U goes `U₀ → U₀+ΔU`; L goes `L₀ → L₀−ΔL`. The pump's head:

```
H_pump = (U₀ + (U₀+ΔU))/2 − (L₀ + (L₀−ΔL))/2 = (U₀ + ΔU/2) − (L₀ − ΔL/2)
```

**Step 1 (generating).** The same volume returns, so U goes `U₀+ΔU → U₀` and L goes `L₀−ΔL → L₀`.
With tailwater tracking, the turbine's head:

```
H_turb = ((U₀+ΔU) + U₀)/2 − ((L₀−ΔL) + L₀)/2 = (U₀ + ΔU/2) − (L₀ − ΔL/2)
```

**The two are the same expression.** Both passes average the same four surface elevations
`{U₀, U₀+ΔU}` and `{L₀, L₀−ΔL}`; the trip up and the trip down simply traverse them in opposite
order, and an average does not care about order. So `H_turb = H_pump` identically, the geometric
amplifier of §2.2 is exactly 1, and

```
η_rt = η_pump · η_motor · η_turb · η_gen = η_prod
```

no matter where the reservoirs sit or how much they have been drawn down.

This is the discrete statement of the thing that made the old behaviour wrong: **potential energy is
a state function.** Going A → B → A must net to zero work before losses. The round trip can only be
lossy, never generative, once both directions are measured against the same reference.

Two things worth noting about the strength of this argument:

- **It does not depend on the reservoir curves being linear.** The averaging is a trapezoidal
  approximation of the true `∫ ρ g h dV`, and it carries a second-order error in `Δ`. But the pump
  pass and the turbine pass make *the same* approximation over *the same* interval, so the error
  cancels in the round trip. An imperfect head estimate that is applied symmetrically cannot create
  energy; an exact head estimate applied asymmetrically can. **[interp]**
- **It explains why a datum rule can only ever be a patch.** The R1 report's rule
  `POWSTAT_MASL >= HRW(L)` makes the amplifier `≤ 1` and so caps `η_rt` at `η_prod`, but it cannot
  make it *equal* to 1 at every level, because a constant cannot track a moving surface. Its price
  was measured: a one-directional understatement of recovered energy of up to 2.9 % for a high-head
  PSH, 10 % medium-head, and 27.2 % for Fabelvassdraget's HEISVERKET. Tracking removes the error in
  both directions instead of capping it in one. **[fact]**

### 4.2 Why the end-of-timestep re-run is the right place, not just a convenient one

The tailwater level at the end of step `t` **must** include this station's own discharge, because
that is what the pump's mirror image does: the pump's target level at the end of step 0 includes the
water the pump just moved. Only then do the four elevations coincide and the heads match exactly.

The alternative — using only the tailwater level at the *start* of the step, which is available in
the node loop and would need no re-run — would leave the turbine's head too high by about `ΔL/2`
while the pump's is measured to the midpoint. That is an asymmetry of the same kind as R1, just
smaller, and it would scale with how much the lower reservoir moves per step. **[interp: reasoned
from the algebra above, not separately measured.]**

### 4.3 The measurement

`fix_r1_verify.py`, section A, 121 volume-matched cells per geometry across the full (U_fr, L_fr)
grid **[fact]**:

| Geometry | `η_prod` | before: max `η_rt` | after: max `η_rt` |
|---|---|---|---|
| part-2 loop, P = LRW(L) | 0.64000 | 0.7992 | **0.640000** |
| part-2, P below L | 0.64000 | 0.8788 | **0.640000** |
| D = 30, R_L = 30 | 0.79521 | 1.5797 | **0.795211** |
| high-head PSH | 0.79521 | 0.8186 | **0.795211** |
| medium-head PSH | 0.79521 | 0.8834 | **0.795211** |
| two lakes, deep drawdown | 0.79521 | 2.3386 | **0.795211** |
| two lakes, small gap | 0.79521 | 6.4675 | **0.795211** |

`η_rt` equals `η_prod` at *every* level, to within one unit in the last place (1.1e-16) — which is
exactly what §4.1 predicts, and is the strongest evidence that the mechanism is understood rather
than merely patched. The same sweep as §2.3, after the change:

| L surface [masl] | pump head [m] | turbine head [m] | `η_rt` |
|---|---|---|---|
| 100 (LRW) | 110.01 | 110.01 | 0.640000 |
| 110 | 100.01 | 100.01 | 0.640000 |
| 120 (HRW) | 90.01 | 90.01 | 0.640000 |

And on the real dataset, HEISVERKET at the cell that used to create energy:

```
before:  5.731874 MWh in  →  5.878772 MWh out     η_rt = 1.0256   (0.147 MWh created)
after:   5.731874 MWh in  →  4.188796 MWh out     η_rt = 0.7308   (η_prod = 0.78817)
```

Zero of 192 tested cells exceed `η_prod` after the change, against 4 above 1.0 before.

### 4.4 Where the equality is not exact, and why **[fact]**

Two residuals showed up in the sweeps. Neither creates energy; both are worth knowing.

1. **Upper reservoir at HRW: `η_rt` lands up to 5e-5 *below* `η_prod`.** HERSS clips the station
   *intake* level at HRW (`reservoir.cpp:523`, "it should never pay off to flood") but the pump does
   not clip, and the prototype's tailwater does not either. When pumping pushes U above HRW, the
   turbine's top is clipped while the pump paid for the real level. The asymmetry is conservative,
   and it is pre-existing behaviour, not something the change introduces. **[open]** whether the
   tailwater should be clipped too.
2. **A tailwater below the turbine centreline now gives *more* head, not less.** Fabelvassdraget
   DYPFALL: `H_turb` rises from 186.7 m to 193.7 m when SALTVIKA sits at its LRW. For a reaction
   turbine (Francis, Kaplan) that is right — the draft tube recovers head down to the tailwater
   surface. For an impulse turbine (Pelton) it is wrong, since the jet cannot use head below the
   runner. `max(POWSTAT_MASL, tailwater)` would cover both machine types and still bounds `η_rt` by
   `η_prod`, because the turbine head then never exceeds the pump head. **[open]**

---

## 5. Summary

| | Before | After (opted in) |
|---|---|---|
| Turbine head bottom | `POWSTAT_MASL`, constant | tailwater reservoir's averaged surface |
| Pump head bottom | source reservoir's averaged surface | unchanged |
| Consistent in a loop? | no — different references for the same water | yes — identical expression both ways |
| `η_rt` vs level | rises as the lower reservoir fills | flat at `η_prod` |
| `η_rt > 1` possible? | yes, measured up to 6.47 (and 1.0256 on a real dataset) | no, up to 1 ulp |
| Existing datasets | — | bit-for-bit identical, all 12 |
| Cost | — | one extra station pass per timestep, ≈ +14 % on fabelvassdraget |

**What is settled [fact]:** the mechanism, the closed form, the measurement before and after, and
that the default path does not move.

**What is not [open]:** HRW clipping of the tailwater, Pelton vs reaction (`max(P, tailwater)`),
whether end-of-timestep station accounting is acceptable, and whether a production version should
split `Powerstation::Simulate` into a flow phase and an energy phase instead of re-running it.
Those are decisions about HERSS physics and belong with the HERSS lead developer, not in this
thesis (CLAUDE.md §3).
