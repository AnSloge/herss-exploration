#!/usr/bin/env python
"""
Validate replica3 against real HERSS, PER STEP and PER NODE.

Why not just compare value functions. On the previous run the CalcOverflow guard
was transcribed with the HRW clip hoisted out of the `masl > masl_start_overflow`
test. That pins a reservoir at exactly HRW forever -- a gross physical error --
and it was invisible in the value function, because the reservoir concerned was
never near HRW under the policies being compared. A VF check answers "do these
two numbers agree on this trajectory", which is not the question. The question
is whether the transition is the same function.

So: run the HERSS command-line binary, which writes a full per-step trace for
every node when WRITE_NODEFILES is 1, and compare every field the replica
produces against its column in those files. Three action sets are used, chosen
to exercise different branches:

  shipped   the dataset's own actions_utahps.txt -- the reference trajectory
  zero      all actions 0.0 -- reservoirs fill, overflow and the HRW clip are
            exercised at every reservoir, nothing produces
  random    seed 42, uniform [0,1] -- trips the aggressive-action guards, the
            start/stop cost, and partial-load points on the turbine curves

The comparison runs in a COPY of the instance directory, so the working
instance's verbatim actions_utahps.txt is never overwritten.

Tolerance, and why it is not uniform. The node files are printed with %.4f, so
5e-4 is the floor for any traced quantity. For DERIVED money columns that floor
propagates: income is power times price, and power is only printed to 1e-4, so
the achievable agreement on income is 5e-4 * price -- up to 0.28 EUR at this
instance's peak price of 564.88. That is not a hypothesis. HERSS's own printed
income differs from its own printed power times price by up to 0.025 EUR on the
shipped trajectory, i.e. the file is already inconsistent with itself at that
scale. Holding the replica to a tighter bound than the file can express would be
measuring printf, so income and profit carry a per-step tolerance of
PRINT_RESOLUTION * price[t] and everything else carries PRINT_RESOLUTION.

The value function is therefore NOT checked against the printed one. It is
checked against CalcVF through cppyy, in full double precision. The printed
value cannot serve: riversystem.cpp:533 WriteRiverSystemData recomputes and
overwrites valuefunction_Euro at :576,591,593, duplicating CalcVF's logic, and
on this instance the two disagree by 0.197 EUR (CLAUDE.md section 8, open item
4). That disagreement is recorded as a finding, not treated as a replica error.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nodefiles
import oracle3
import params3
import replica3

HERE = os.path.dirname(os.path.abspath(__file__))

# printf uses %.4f throughout the node files
PRINT_RESOLUTION = 5e-4
REL_TOL = 1e-6


def action_sets(p, T):
    names = [f"g{s.idnr}" for s in p.stations]
    sets = {"shipped": params3.load_actions(p)}
    sets["zero"] = {n: [0.0] * T for n in names}
    rng = np.random.default_rng(42)
    sets["random"] = {n: [float(x) for x in rng.uniform(0.0, 1.0, T)] for n in names}
    return sets


def run_herss_cli(p, actions, workdir):
    """Copy the instance, drop in the action file, run the CLI, read the trace."""
    shutil.copytree(p.dataset_dir, workdir, dirs_exist_ok=True)
    os.makedirs(os.path.join(workdir, "output"), exist_ok=True)
    oracle3.write_action_file(p, actions, os.path.join(workdir, p.actionfile))
    oracle3.run_cli(p, cwd=workdir)
    out = os.path.join(workdir, "output")
    return nodefiles.trace(out, p), nodefiles.read_riversystem(
        os.path.join(out, "riversystem_uTAHPS_output.txt"))


def run_replica(plan, actions, inflow, prices, restprice):
    trace = {}
    vf, profits = replica3.simulate_sequence(plan, actions, inflow, prices,
                                             restprice, trace=trace)
    flat = {}
    for k, v in trace.items():
        if k == "negative_overflow_events":
            continue
        flat[k] = np.array([x[0] for x in v])
    return vf, profits, flat, trace.get("negative_overflow_events", 0)


# Money columns derived from Power, whose own printed precision is 1e-4.
PRICE_SCALED_FIELDS = ("income", "profit")


def field_tolerance(field, prices, n):
    """
    Per-step absolute tolerance -- see the module docstring on propagation.

    Two floors apply to a derived money column and the larger wins:
      - its own %.4f quantisation, which is PRINT_RESOLUTION regardless of price
      - the propagated quantisation of Power, which is PRINT_RESOLUTION * price
    Using only the second collapses the tolerance to nothing at t = 341, where
    this instance's price bottoms out at 0.04 EUR/MWh.
    """
    if field in PRICE_SCALED_FIELDS:
        return PRINT_RESOLUTION * np.maximum(np.asarray(prices[:n], float), 1.0)
    return np.full(n, PRINT_RESOLUTION)


def compare(herss_tr, repl_tr, prices):
    """Per (idnr, field) worst deviation, against the propagated print floor."""
    rows = []
    for key in sorted(herss_tr, key=lambda k: (k[0], k[1])):
        if key not in repl_tr:
            rows.append({"idnr": key[0], "field": key[1], "status": "MISSING"})
            continue
        h = np.asarray(herss_tr[key], float)
        r = np.asarray(repl_tr[key], float)
        n = min(len(h), len(r))
        h, r = h[:n], r[:n]
        d = np.abs(h - r)
        tol = field_tolerance(key[1], prices, n)
        # how far each step sits from its own tolerance, as a ratio
        margin = d / tol
        i = int(np.argmax(margin))
        ok = bool(margin.max() <= 1.0)
        rows.append({"idnr": key[0], "field": key[1], "n": n,
                     "max_abs": float(d.max()),
                     "max_rel": float((d / np.maximum(np.abs(h), 1.0)).max()),
                     "worst_margin": float(margin.max()), "worst_t": i,
                     "tolerance_at_worst": float(tol[i]),
                     "herss": float(h[i]), "replica": float(r[i]),
                     "status": "OK" if ok else "FAIL"})
    return rows


def determinism_check(p, sets):
    """
    CLAUDE.md section 10, item 5. The manual states Simulate() reinitialises all
    state on every call; that is documentation, not verified behaviour, and every
    result downstream is invalid if state leaks between calls.

    A -> A must be bit identical, and A -> B -> A must reproduce A exactly. Both
    are run in ONE process, which is the case that matters: the search calls
    evaluate_vf repeatedly against a rebuilt Herss object, and a leak would show
    up as history dependence.
    """
    a, b = sets["shipped"], sets["random"]
    vf_a1 = oracle3.evaluate_vf(p, a)
    vf_a2 = oracle3.evaluate_vf(p, a)
    vf_b = oracle3.evaluate_vf(p, b)
    vf_a3 = oracle3.evaluate_vf(p, a)
    return {
        "A_first": vf_a1, "A_repeat": vf_a2, "B": vf_b, "A_after_B": vf_a3,
        "repeat_bit_identical": vf_a1 == vf_a2,
        "aba_bit_identical": vf_a1 == vf_a3,
        "ok": bool(vf_a1 == vf_a2 == vf_a3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="validation_replica3.json")
    ap.add_argument("--keep", action="store_true",
                    help="keep the temporary instance copies")
    args = ap.parse_args()

    p = params3.get()
    plan = replica3.build_plan(p)
    prices, inflow, restprice = params3.load_series(p)
    T = len(prices)
    version, version_date = oracle3.version_info()

    result = {"instance": p.name, "T": T, "restprice": restprice,
              "herss_version": version, "herss_version_date": version_date,
              "print_resolution": PRINT_RESOLUTION, "rel_tol": REL_TOL,
              "sets": {}}

    sets = action_sets(p, T)

    det = determinism_check(p, sets)
    result["determinism"] = det
    print(f"[determinism] A {det['A_first']:.6f} -> A {det['A_repeat']:.6f} "
          f"-> B {det['B']:.6f} -> A {det['A_after_B']:.6f}")
    print(f"[determinism] repeat bit-identical {det['repeat_bit_identical']}, "
          f"A->B->A bit-identical {det['aba_bit_identical']}")

    all_ok = det["ok"]
    for name, actions in sets.items():
        workdir = tempfile.mkdtemp(prefix=f"utahps_val_{name}_")
        try:
            herss_tr, scalars = run_herss_cli(p, actions, workdir)
            vf_r, profits, repl_tr, neg_ov = run_replica(plan, actions, inflow,
                                                         prices, restprice)
            # authoritative: CalcVF in full precision, not the printed value
            vf_h = float(oracle3.evaluate_vf(p, actions))
            vf_cli = scalars["valuefunction_Euro"]
            rows = compare(herss_tr, repl_tr, prices)
            fails = [r for r in rows if r["status"] != "OK"]
            vf_rel = abs(vf_h - vf_r) / abs(vf_h)
            ok = bool(not fails and vf_rel < 1e-8)
            all_ok &= ok

            worst = max((r for r in rows if r["status"] == "OK"),
                        key=lambda r: r["worst_margin"], default=None)
            result["sets"][name] = {
                "vf_calcvf": vf_h, "vf_replica": vf_r,
                "vf_abs_diff": float(vf_h - vf_r), "vf_rel_diff": float(vf_rel),
                # riversystem.cpp:576,591,593 recompute what CalcVF already did
                "vf_cli_writeriversystemdata": vf_cli,
                "cli_minus_calcvf": float(vf_cli - vf_h),
                "negative_overflow_events": int(neg_ov),
                "waterbalance": scalars["waterbalance"],
                "n_fields": len(rows), "n_fail": len(fails),
                "worst_ok_field": worst, "failures": fails,
                "ok": ok,
            }
            print(f"[{name}] VF CalcVF {vf_h:16.4f}  replica {vf_r:16.4f}  "
                  f"rel {vf_rel:.3e}")
            print(f"[{name}] CLI printed VF {vf_cli:16.4f}  "
                  f"(CLI - CalcVF = {vf_cli - vf_h:+.4f}, "
                  f"WriteRiverSystemData duplicate)")
            print(f"[{name}] {len(rows)} traced fields, {len(fails)} failing, "
                  f"negative-overflow events {neg_ov}, "
                  f"waterbalance {scalars['waterbalance']:.6f}")
            if worst:
                print(f"[{name}] tightest agreeing field: node {worst['idnr']} "
                      f"{worst['field']} max_abs {worst['max_abs']:.2e} "
                      f"at {worst['worst_margin'] * 100:.0f} % of its tolerance")
            for f in fails:
                print(f"  FAIL node {f['idnr']} {f['field']}: "
                      f"max_abs {f.get('max_abs')} "
                      f"margin {f.get('worst_margin')} "
                      f"at t={f.get('worst_t')} "
                      f"HERSS {f.get('herss')} replica {f.get('replica')}")
        finally:
            if not args.keep:
                shutil.rmtree(workdir, ignore_errors=True)
            else:
                print(f"[{name}] kept {workdir}")

    result["all_ok"] = all_ok
    with open(os.path.join(HERE, args.out), "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n{'OK' if all_ok else 'FAIL'}: wrote {args.out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
