"""C5 part 1, Part D -- place the built instances on the Fase C (rho, R) plane.

NO DP, NO B4. Reads rho/R back-computed by validate_c5.py and the Fase C
landscape from analysis/scarcity_gap/faseC_summary.json. Every gap quoted here
is a FASE C READ-ACROSS from a different (pump-free) instance, not a
measurement of these instances.

Distance on the plane: |d rho| and |d log2 R| (the Fase C R axis is a doubling
axis), combined as sqrt(d_rho^2/0.25^2 + d_log2R^2) so one rho grid step (0.25)
weighs the same as one R doubling.
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FC = json.load(open(os.path.join(REPO, "analysis", "scarcity_gap", "faseC_summary.json")))
VAL = json.load(open(os.path.join(HERE, "validation_results.json")))

# Fase C hard corner, gap_fase_c.md sec. 11: R <= ~0.09 and rho in ~0.5-1.0
CORNER = dict(R_max=0.09, rho_lo=0.5, rho_hi=1.0)
R_STAR = {1.0: 0.096, 0.782: 0.074}          # 1 % crossings, gap_fase_c.md sec. 7.1

cells = []
for r in FC["rows"]:
    if r.get("gap_B4") is None:
        continue
    cells.append(dict(instance=r["instance"], kind=r["kind"], rho=r["rho"], R=r["R"],
                      gap_B4=r["gap_B4"], gap_B2=r["gap_B2"],
                      overflow_Mm3=r["overflow_Mm3"]))

out = dict(corner=CORNER, R_star=R_STAR, variants={})
for name, v in VAL["variants"].items():
    nb = v["numbers"]
    rho, R = nb["rho"], nb["R"]
    for c in cells:
        c["dist"] = math.hypot((c["rho"] - rho) / 0.25, math.log2(c["R"] / R))
    near = sorted(cells, key=lambda c: c["dist"])[:6]
    # rho = 1 is the band's upper edge AND the measured peak of the rho edge
    # (gap_fase_c.md sec. 7.2); the edge itself is not a measured threshold
    # (sec. 11), so compare with a float tolerance and flag the edge.
    inside = (R <= CORNER["R_max"]) and (CORNER["rho_lo"] - 1e-6 <= rho <= CORNER["rho_hi"] + 1e-6)
    on_upper_edge = abs(rho - CORNER["rho_hi"]) < 1e-6
    out["variants"][name] = dict(rho=rho, R=R, rho_system=nb["rho_system"],
                                 head_span_ratio=nb["head_span_ratio"],
                                 in_corner=inside, on_upper_rho_edge=on_upper_edge,
                                 R_over_Rstar_at_rho1=R / R_STAR[1.0],
                                 nearest=[dict((k, c[k]) for k in
                                               ("instance", "kind", "rho", "R", "gap_B4",
                                                "gap_B2", "overflow_Mm3", "dist"))
                                          for c in near])
    print(f"\n=== {name}: rho {rho:.6f}  R {R:.6f}  in corner: {inside}  "
          f"upper rho edge: {on_upper_edge}  R/R*(rho=1) = {R / R_STAR[1.0]:.3f}  head_span_ratio {nb['head_span_ratio']:.4f}")
    print(f"  {'Fase C cell':<22} {'kind':<10} {'rho':>6} {'R':>7} {'B4 gap %':>9} "
          f"{'B2 gap %':>9} {'dist':>6}")
    for c in near:
        print(f"  {c['instance']:<22} {c['kind']:<10} {c['rho']:>6.3f} {c['R']:>7.4f} "
              f"{c['gap_B4']:>9.3f} {c['gap_B2']:>9.3f} {c['dist']:>6.3f}")
json.dump(out, open(os.path.join(HERE, "position_results.json"), "w"), indent=1)
print("\nwrote position_results.json")
