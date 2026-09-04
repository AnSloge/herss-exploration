#!/usr/bin/env python
"""
Roll every result_*.json in this directory into the Phase C tables.

Run after each cell, so a night that stops halfway is still readable. Writes
faseC_summary.md and faseC_summary.json next to this file.

Three things this script refuses to do silently, because each of them is a way
to make a merged table say something the measurements do not support:

  1. It never drops the resolution column. The 2026-08-04 run held the DP point
     count fixed at 8001, so its resolution fell from 389 to 41 grid cells per
     full-load step as R grew -- and the coarsest cells are exactly the ones
     reporting a near-zero gap. A coarse grid makes DP worse, which makes the
     gap look SMALLER, so those cells cannot be read as equally resolved.
  2. It never hides an unchecked convergence. A cell run with
     --skip-convergence shows "-" and is marked in the notes.
  3. It never merges the 2026-08-04 and Phase C cells into one gap-vs-R table
     until the bridge cell has been measured and the merge verdict computed
     here says it is allowed.

Budget is reported in three columns because they are not interchangeable:
wall clock, full-horizon evaluations, and DP step-cells. Only wall clock is
comparable across methods -- see the footnote emitted with the table.
"""

import glob
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

# Cells measured on 2026-08-04 with the fixed 8001-point grid.
LEGACY = {
    "syn_rho0p5_R0p5", "syn_rho0p5_R1", "syn_rho0p75_R1", "syn_rho1_R0p5",
    "syn_rho1_R1", "syn_rho1_R2", "syn_rho1_R4", "syn_rho1p25_R1", "syn_rho1p25_R4",
}
UTAHPS = {"hjelle_daily", "gresse_daily", "toppsy_daily", "kroknesvatn_daily",
          "hjelle_daily_e163", "mini_utahps_daily"}

# The bridge: same instance, two resolutions. If re-measuring syn_rho1_R4 on the
# derived grid moves its gap by much, the two runs are not on one curve.
BRIDGE_LEGACY = "result_syn_rho1_R4.json"
BRIDGE_FASEC = "result_syn_rho1_R4_fasec.json"
# The gaps this axis is used to compare are 0.003 % .. 3.5 %. A bridge shift
# that stays under a tenth of the smallest gap the merged table is asked to
# resolve (0.1 %) leaves the shape of the curve intact.
BRIDGE_TOL_PCT = 0.01


def load_all():
    out = {}
    for fn in sorted(glob.glob(os.path.join(HERE, "result_*.json"))):
        try:
            with open(fn) as f:
                out[os.path.basename(fn)] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  skipped {os.path.basename(fn)}: {e}")
    return out


def cells_per_step(d):
    """Grid cells per full-load step, from the record if present, else derived."""
    v = d["dp"].get("cells_per_fullload_step")
    if v is not None:
        return v
    lo, hi, n = d["dp"]["grid"]
    # GENERATOR_MAX_DISCHARGE * dt is not in the record; recover it from the
    # regime block, which stores turbine capacity over the whole horizon.
    step_Mm3 = d["regime"]["turbine_capacity_Mm3"] / d["regime"]["T"]
    return step_Mm3 / ((hi - lo) / (n - 1))


def row(fn, d):
    b = d.get("baselines", {})
    dg = d["dp"]
    diag = d.get("diagnosis", {}).get("DP", {})
    b4_evals = b.get("B4", {}).get("evaluations")
    b2_evals = b.get("B2", {}).get("evaluations")
    # The bridge is the SAME instance measured twice at different resolutions,
    # so it must not appear in a table under a name identical to the cell it is
    # being compared against.
    label = d["instance"] + (" (bro)" if fn == BRIDGE_FASEC else "")
    return {
        "file": fn,
        "instance": label,
        "kind": ("uTAHPS" if d["instance"] in UTAHPS else
                 "2026-08-04" if d["instance"] in LEGACY and "_fasec" not in fn
                 else "Phase C"),
        "rho": d["regime"]["rho"],
        "R": d["regime"]["R"],
        "gap_B2": b.get("B2", {}).get("gap_pct_vs_dp"),
        "gap_B4": b.get("B4", {}).get("gap_pct_vs_dp"),
        "overflow_Mm3": diag.get("overflow_total_Mm3"),
        "overflow_steps": diag.get("overflow_steps"),
        "n_grid": int(dg["grid"][2]),
        "cells_per_step": cells_per_step(d),
        "converged": dg.get("convergence_checked", dg.get("grid_doubled") is not None),
        "conv_delta_pct": dg.get("convergence_delta_pct"),
        "seconds_total": sum(v for v in [dg.get("seconds"), dg.get("seconds_convergence")] +
                             [r.get("seconds") for r in b.values()] if v),
        "evals_full_horizon": (b2_evals or 0) + (b4_evals or 0),
        "dp_step_cells": dg.get("n_transition_evaluations"),
        "vf_dp_real": dg.get("vf_real_herss"),
        "replica_minus_herss": (dg.get("vf_replica", 0) - dg.get("vf_real_herss", 0)
                                if dg.get("vf_real_herss") else None),
    }


def effective_grid(d):
    """
    The grid the reported DP value actually came from.

    run_measurement.py takes max(base grid, doubled grid) whenever the
    convergence check runs, so a cell labelled "8001 points" reports the
    16001-point value if that one came out higher. Comparing the bridge cell
    against the nominal 8001 would overstate what it proves -- the same class
    of silent mismatch as the e163 case, where replica and simulator optimised
    two different objectives without it showing in the VF.

    Returns (n_points, cells_per_full_load_step, used_doubled_grid).
    """
    dg = d["dp"]
    n_base = int(dg["grid"][2])
    if not dg.get("grid_doubled") or dg.get("vf_doubled_grid") is None:
        return n_base, cells_per_step(d), False
    if dg["vf_doubled_grid"] <= dg["vf_base_grid"]:
        return n_base, cells_per_step(d), False
    n_dbl = int(dg["grid_doubled"][2])
    return n_dbl, cells_per_step(d) * (n_dbl - 1) / (n_base - 1), True


def bridge_verdict(results):
    a, b = results.get(BRIDGE_LEGACY), results.get(BRIDGE_FASEC)
    if not b:
        return {"status": "not_measured",
                "text": "Brocellen er ikke målt ennå. Gamle og nye celler holdes i "
                        "SEPARATE tabeller til den er det."}
    ga = a["baselines"]["B4"]["gap_pct_vs_dp"]
    gb = b["baselines"]["B4"]["gap_pct_vs_dp"]
    shift = gb - ga
    ok = abs(shift) <= BRIDGE_TOL_PCT
    na, ca, dbl_a = effective_grid(a)
    nb, cb, _ = effective_grid(b)
    note = (f" (gammelcellen er merket {int(a['dp']['grid'][2])} punkt, men DP-verdien "
            f"kommer fra den doblede {na}-punktskjoringen -- run_measurement.py tar "
            f"max av de to)" if dbl_a else "")
    return {
        "status": "merge_allowed" if ok else "merge_refused",
        "gap_legacy_pct": ga, "gap_fasec_pct": gb, "shift_pct": shift,
        "n_grid_legacy_nominal": int(a["dp"]["grid"][2]),
        "n_grid_legacy_effective": na, "n_grid_fasec": nb,
        "cells_per_step_legacy_effective": ca, "cells_per_step_fasec": cb,
        "legacy_used_doubled_grid": dbl_a,
        "tol_pct": BRIDGE_TOL_PCT,
        "text": (f"syn_rho1_R4 pa {na} punkt ({ca:.0f} celler/fullaststeg){note} ga "
                 f"{ga:.4f} %; pa {nb} punkt ({cb:.0f} celler/fullaststeg) {gb:.4f} %. "
                 f"Forskyvning {shift:+.4f} prosentpoeng mot toleranse "
                 f"{BRIDGE_TOL_PCT:.3f}. "
                 + ("Sammenslaing tillatt: opplosningen flytter ikke gapet nok til a "
                    "endre formen pa kurven."
                    if ok else
                    "SAMMENSLAING AVVIST: opplosning alene flytter gapet like mye som "
                    "det tabellen skal sammenlikne. Hold tabellene atskilt.")),
    }


def fmt(v, spec=".4f", dash="-"):
    return dash if v is None else format(v, spec)


def md_table(rows, title):
    if not rows:
        return f"### {title}\n\n*(ingen celler ennå)*\n"
    out = [f"### {title}", "",
           "| instans | rho | R | B2 gap % | B4 gap % | overløp Mm³ | steg m/ovl | "
           "celler/fullaststeg | n_grid | konv. |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["R"], r["rho"])):
        conv = (f"{r['conv_delta_pct']:+.5f} %" if r["converged"] and
                r["conv_delta_pct"] is not None else "ikke kjørt")
        out.append(
            f"| `{r['instance']}` | {r['rho']:.3f} | {r['R']:.4f} | "
            f"{fmt(r['gap_B2'], '.3f')} | {fmt(r['gap_B4'], '.3f')} | "
            f"{fmt(r['overflow_Mm3'], '.2f')} | {fmt(r['overflow_steps'], 'd')} | "
            f"{r['cells_per_step']:.0f} | {r['n_grid']} | {conv} |")
    return "\n".join(out) + "\n"


def md_budget(rows):
    out = ["### Budsjett", "",
           "| instans | veggklokke s | fulle horisontevalueringer | DP-stegceller |",
           "|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["kind"], r["R"], r["rho"])):
        out.append(f"| `{r['instance']}` | {r['seconds_total']:.0f} | "
                   f"{r['evals_full_horizon']:,} | {r['dp_step_cells']:,} |")
    out += ["",
            "> Kun veggklokketid er sammenlignbar på tvers av metodene. En "
            "«full horisontevaluering» i B2/B4 og en DP-stegcelle er ikke samme "
            "arbeidsmengde: DP-stegcellen er én tilstand-handling-transisjon, "
            "vektorisert, mens en B2/B4-evaluering er en hel T-stegs "
            "framoverkjøring. Kolonnene står ved siden av hverandre for å vise "
            "hva som faktisk ble brukt, ikke for å settes mot hverandre."]
    return "\n".join(out) + "\n"


def main():
    results = load_all()
    rows = [row(fn, d) for fn, d in results.items()
            if "regime" in d and "dp" in d and d["instance"] != "mini_utahps_daily"]

    bridge = bridge_verdict(results)
    legacy = [r for r in rows if r["kind"] == "2026-08-04"]
    fasec = [r for r in rows if r["kind"] == "Phase C"]
    utahps = [r for r in rows if r["kind"] == "uTAHPS"]

    md = [f"# Fase C — løpende sammendrag",
          "",
          f"Generert {datetime.now(timezone.utc).isoformat(timespec='seconds')} av "
          f"`faseC_summary.py`. Skrives om etter hver ferdige celle; et delvis "
          f"resultat er ment å være lesbart.",
          "",
          f"**Celler:** {len(fasec)} Fase C, {len(legacy)} fra 2026-08-04, "
          f"{len(utahps)} uTAHPS-utsnitt.",
          "",
          "## Brocelle — er sammenslåing tillatt?",
          "",
          bridge["text"],
          ""]

    if bridge["status"] == "merge_allowed":
        md += [md_table(legacy + fasec,
                        "Syntetisk rutenett, sammenslått (brocellen bekreftet)"), ""]
    else:
        md += [md_table(fasec, "Fase C-celler (avledet rutenett, 155 celler/fullaststeg)"),
               "",
               md_table(legacy, "2026-08-04-celler (fast rutenett, 8001 punkt)"),
               "",
               "> Tabellene er IKKE slått sammen. `R` betyr det samme i begge — "
               "konvensjonen `V'(m) = s_R · V(m)` er verifisert lest tilbake fra "
               "instansene på disk — men DP-oppløsningen gjør det ikke, og "
               "brocellen har ikke frikjent forskjellen.", ""]

    md += [md_table(utahps, "uTAHPS-utsnitt (ekte, ikke syntetiske — aldri i samme "
                            "konklusjon som cellene over)"), "",
           md_budget(rows), ""]

    unconverged = [r for r in fasec if not r["converged"]]
    if unconverged:
        md += ["> Konvergenssjekk ikke kjørt på: "
               + ", ".join(f"`{r['instance']}`" for r in unconverged)
               + ". Etter planen kjøres den på tre representative celler; gapene "
                 "for de øvrige hviler på at diskretiseringsfeilen der oppfører "
                 "seg som på de tre.", ""]

    # Atomic: parallel cells each call this on finishing, so a reader must never
    # catch a half-written table.
    def write_atomic(name, text):
        tmp = os.path.join(HERE, f".{name}.{os.getpid()}.tmp")
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, os.path.join(HERE, name))

    write_atomic("faseC_summary.md", "\n".join(md))
    write_atomic("faseC_summary.json",
                 json.dumps({"generated": datetime.now(timezone.utc).isoformat(),
                             "bridge": bridge, "rows": rows}, indent=2, default=float))
    print(f"faseC_summary.md: {len(fasec)} Fase C + {len(legacy)} legacy cells; "
          f"bridge = {bridge['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
