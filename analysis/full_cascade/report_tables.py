#!/usr/bin/env python
"""
Emit the report's tables straight from result_utahps_daily.json.

Transcribing a dozen numbers by hand into a markdown table is a reliable way to
introduce an error that nobody catches, and the whole point of the run is that
the numbers are trustworthy. Everything in analysis/gap_full_kaskade.md that is
a table comes from here.
"""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path=None):
    with open(path or os.path.join(HERE, "result_utahps_daily.json")) as f:
        return json.load(f)


def _n(x, d=2):
    """Norwegian decimal comma, space as thousands separator."""
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def _thousands(x):
    """Integer with a non-breaking space as thousands separator."""
    return f"{x:,}".replace(",", "\u00a0")


def table_b4_spread(r):
    b4 = r["B4"]
    sp = b4["spread"]
    out = ["| seed | VF HERSS [EUR] | konvergert | grov it. | fin it. | finpuss [EUR] | veggklokke [t] |",
           "|---|---|---|---|---|---|---|"]
    for d in sp["distribution"]:
        out.append(f"| {d['seed']} | {_n(d['vf_herss'])} | "
                   f"{'ja' if d['converged'] else '**nei**'} | "
                   f"{d['coarse_iterations']} | {d['fine_iterations']} | "
                   f"{_n(d['polish_gain'])} | {d['wall_clock_hours']:.2f} |".replace(".", ","))
    out.append("")
    out.append("| statistikk | verdi |")
    out.append("|---|---|")
    out.append(f"| min | {_n(sp['min'])} |")
    out.append(f"| median | {_n(sp['median'])} |")
    out.append(f"| gjennomsnitt | {_n(sp['mean'])} |")
    out.append(f"| maks | {_n(sp['max'])} |")
    out.append(f"| standardavvik | {_n(sp['std'])} |")
    out.append(f"| **spredning (maks−min)** | **{_n(sp['range_Euro'])}** |")
    out.append(f"| **spredning i % av beste** | **{_n(sp['range_pct_of_best'], 4)} %** |")
    return "\n".join(out)


def table_methods(r):
    rows = []
    b2 = r["baselines"]["B2"]["vf_herss"]
    best = r.get("B5", r.get("B4", {})).get("vf_herss") or r["B4"]["vf_herss"]
    for tag in ("B0", "B1", "B2", "B3"):
        if tag in r.get("baselines", {}):
            b = r["baselines"][tag]
            rows.append((tag, b["description"], b["vf_herss"], b["budget"],
                         b["herss_minus_replica"]))
    for tag in ("B4", "B5"):
        if tag in r:
            b = r[tag]
            bud = b.get("budget") or b.get("budget_summed_over_restarts")
            rows.append((tag, b["description"], b["vf_herss"], bud,
                         b["herss_minus_replica"]))
    out = ["| | metode | VF HERSS [EUR] | mot beste | fulle eval. | stegceller | veggklokke [s] | \\|d\\| |",
           "|---|---|---|---|---|---|---|---|"]
    for tag, desc, vf, bud, d in rows:
        out.append(f"| {tag} | {desc} | {_n(vf)} | "
                   f"{_n(100.0 * (vf - best) / best, 4)} % | "
                   f"{_thousands(bud['n_full_evaluations'])} | "
                   f"{_thousands(bud['n_step_cells'])} | "
                   f"{_n(bud['seconds'], 0)} | {_n(d, 4)} |")
    out.append("")
    out.append("Kun veggklokketid er sammenlignbar på tvers av metodefamilier: en "
               "batchet sveip og en skalar løkke koster svært ulikt per "
               "«evaluering». For B4 er veggklokketiden **summen over åtte "
               "omstarter**; per omstart står i spredningstabellen.")
    return "\n".join(out)


def table_spill(r):
    diag = r["diagnosis"]
    tags = [t for t in ("B0", "B1", "B2", "B3", "B4", "B5") if t in diag]
    names = list(diag[tags[0]]["spill"].keys())
    out = ["| magasin | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for n in names:
        cells = []
        for t in tags:
            v = diag[t]["spill"][n]
            cells.append(f"{_n(v['overflow_Mm3'], 1)} / {v['overflow_steps']}")
        out.append(f"| {n} | " + " | ".join(cells) + " |")
    cells = []
    for t in tags:
        tot = sum(v["overflow_Mm3"] for v in diag[t]["spill"].values())
        st = sum(v["overflow_steps"] for v in diag[t]["spill"].values())
        cells.append(f"**{_n(tot, 1)} / {st}**")
    out.append("| **sum** | " + " | ".join(cells) + " |")
    out.append("")
    out.append("Format: overløpsvolum [Mm³] / antall steg med overløp.")
    return "\n".join(out)


def table_feasibility(r):
    diag = r["diagnosis"]
    tags = [t for t in ("B0", "B1", "B2", "B3", "B4", "B5") if t in diag]
    out = ["| metode | aggressive [EUR / steg] | LRW-straff [EUR / steg] | start/stopp [EUR] | steg over HRW |",
           "|---|---|---|---|---|"]
    for t in tags:
        d = diag[t]["feasibility"]
        agg = sum(v["aggressive_cost_Euro"] for v in d["per_station"].values())
        aggs = sum(v["aggressive_steps"] for v in d["per_station"].values())
        lrw = sum(v["lrw_cost_Euro"] for v in d["per_reservoir"].values())
        lrws = sum(v["lrw_steps"] for v in d["per_reservoir"].values())
        ss = sum(v["startstop_cost_Euro"] for v in d["per_station"].values())
        hrw = sum(v["steps_above_HRW"] for v in d["per_reservoir"].values())
        out.append(f"| {t} | {_n(agg, 1)} / {aggs} | {_n(lrw, 1)} / {lrws} | "
                   f"{_n(ss, 1)} | {hrw} |")
    return "\n".join(out)


def table_regime(r):
    st = r["regime_static"]["per_reservoir"]
    re = r.get("regime_realised", {})
    out = ["| magasin | R | rho eget | rho realisert | oppstrøms mottatt [Mm³] | differanse mot skive |",
           "|---|---|---|---|---|---|"]
    for idnr, d in st.items():
        n = d["name"]
        rr = re.get(n)
        if rr:
            out.append(f"| {n} | {_n(d['R'], 3)} | {_n(d['rho_own'], 3)} | "
                       f"**{_n(rr['rho_realised'], 3)}** | "
                       f"{_n(rr['upstream_received_Mm3'], 1)} | "
                       f"{_n(100.0 * (rr['rho_realised'] / d['rho_own'] - 1.0), 1)} % |")
        else:
            out.append(f"| {n} | {_n(d['R'], 3)} | {_n(d['rho_own'], 3)} | – | – | – |")
    return "\n".join(out)


def table_b5(r):
    if "B5" not in r:
        return "*(B5 ikke kjørt)*"
    b5 = r["B5"]
    out = [f"B5 − B4 = **{_n(b5['B5_minus_B4_Euro'])} EUR** "
           f"({_n(b5['B5_minus_B4_pct_of_B4'], 5)} % av B4), "
           f"{b5['iterations']} iterasjoner, konvergert = "
           f"{'ja' if b5['converged'] else '**nei**'}.", "",
           "| naboskap | gevinst [EUR] (replika) |", "|---|---|"]
    labels = {"a": "(a) to stasjoner i samme steg",
              "b": "(b) samme stasjon i nabosteg",
              "c": "(c) oppstrøms t + nedstrøms t+1 (reservoarmediert)",
              "single": "enkelttrekk låst opp av parvise trekk"}
    for k in ("a", "b", "c", "single"):
        out.append(f"| {labels[k]} | {_n(b5['gain_by_kind_replica'].get(k, 0.0))} |")
    out.append("")
    out.append("Per trekktype:")
    out.append("")
    out.append("| trekk | gevinst [EUR] |")
    out.append("|---|---|")
    for tag, g in sorted(b5["gain_by_tag_replica"].items(), key=lambda x: -x[1]):
        out.append(f"| `{tag}` | {_n(g)} |")
    return "\n".join(out)


def table_operation(r):
    diag = r["diagnosis"]
    tags = [t for t in ("B2", "B4", "B5") if t in diag]
    out = ["| stasjon | " + " | ".join(f"{t} nivåer / produserende steg" for t in tags) + " |",
           "|---|" + "---|" * len(tags)]
    names = list(diag[tags[0]]["operation"]["per_station"].keys())
    for n in names:
        cells = []
        for t in tags:
            v = diag[t]["operation"]["per_station"][n]
            cells.append(f"{v['distinct_action_levels']} / {v['steps_producing']}")
        out.append(f"| {n} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def table_correlation(r):
    diag = r["diagnosis"]
    tags = [t for t in ("B0", "B2", "B4", "B5") if t in diag]
    keys = list(diag[tags[0]]["coupling"]["production_correlation"].keys())
    out = ["| stasjonspar | " + " | ".join(tags) + " |", "|---|" + "---|" * len(tags)]
    for k in keys:
        cells = []
        for t in tags:
            v = diag[t]["coupling"]["production_correlation"][k]
            cells.append("–" if v is None else _n(v, 3))
        out.append(f"| {k.replace('~', ' ~ ')} | " + " | ".join(cells) + " |")
    return "\n".join(out)


SECTIONS = {
    "methods": ("Metodesammenlikning", table_methods),
    "b4": ("B4 spredning", table_b4_spread),
    "b5": ("B5 dekomponering", table_b5),
    "spill": ("Overløp", table_spill),
    "feasibility": ("Feasibility", table_feasibility),
    "regime": ("Regimetall", table_regime),
    "operation": ("Drift", table_operation),
    "correlation": ("Produksjonskorrelasjon", table_correlation),
}


def main():
    r = load(sys.argv[1] if len(sys.argv) > 1 else None)
    for key, (title, fn) in SECTIONS.items():
        print(f"\n<!-- ===== {key}: {title} ===== -->\n")
        try:
            print(fn(r))
        except (KeyError, IndexError) as e:
            print(f"*(mangler: {e})*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
