#!/usr/bin/env bash
#
# Fase C -- the synthetic rho/R grid, extension run of 2026-08-18.
#
# SYNTHETIC INSTANCES. Nothing measured here is a statement about uTAHPS, and
# these numbers never enter a conclusion about the real system.
#
# Construction is deliberately the SAME as the 2026-08-04 grid:
#   V'(m) = s_R * V(m) over the whole reservoir curve, LRW/HRW fixed at 748/757,
#   inflow rescaled by params.synthetic_inflow_scale so rho lands exactly on its
#   target independently of s_R.
# That convention was verified by reading the nine existing instances back off
# disk before this run was designed. Keeping it is what allows one gap-vs-R
# curve instead of two.
#
# What is NEW here is the state grid: the 2026-08-04 run held the DP point count
# fixed at 8001, so its resolution fell from 389 to 41 cells per full-load step
# as R grew -- and a coarser grid makes DP worse, which makes the gap look
# smaller. Every cell here uses --auto-grid (~155 cells per full-load step).
# Cell 0 is the bridge that measures what that change alone is worth.
#
# Usage:  bash analysis/scarcity_gap/run_fase_c.sh
# Writes: result_<slug>.json per cell, as soon as the cell finishes
#         faseC_summary.md / .json, rewritten after every cell
#         faseC_<slug>.log per cell
set -u
cd "$(dirname "$0")"

PY=../../.venv/bin/python
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

banner() { printf '\n========== %s  [%s] ==========\n' "$1" "$(date -u +%H:%M:%S)"; }
die()    { printf '\n!!! ABORT: %s\n' "$1" >&2; exit 1; }

banner "Fase C start $STAMP"
printf 'commit  : %s\n' "$(git rev-parse --short HEAD)"
printf 'upstream: 029a2d5 (pinned)\n'
printf 'python  : %s\n' "$($PY --version)"
printf 'cores   : %s   free RAM: %s\n' "$(nproc)" "$(free -h | awk '/^Mem:/{print $7}')"

# ---------------------------------------------------------------- 1. smoke
# Fails in seconds if .venv, cppyy, herss.so or the subprocess oracle are
# broken. A night that dies on an import in cell 1 and sits dead until morning
# is a wasted night.
banner "1. smoke test: validate_instance.py hjelle"
cp -p validation_instance.json .validation_instance.bak 2>/dev/null || true
$PY validate_instance.py hjelle || die "smoke test failed -- venv/cppyy/herss.so"
mv -f .validation_instance.bak validation_instance.json 2>/dev/null || true

# ---------------------------------------------------------- 2. regression
# Proves the params.py extension changed no formula.
banner "2. test_regression.py"
$PY test_regression.py || die "regression failed -- params.py extension moved a formula"

# --------------------------------------------------------------- 3. build
banner "3. build_instances.py --fase-c"
$PY build_instances.py --fase-c || die "instance build failed"

# Manifest straight from params, so this script and FASE_C_CELLS cannot drift.
$PY -c "
import params as P
for r, s, c in P.FASE_C_CELLS:
    print(P.synthetic_slug(r, s), int(c), s)
" > faseC_manifest.txt || die "could not read FASE_C_CELLS"
CELLS=$(awk '{print $1}' faseC_manifest.txt)
printf 'cells: %s\n' "$(echo $CELLS | tr '\n' ' ')"

conv_flag() {  # cell needs the doubled-grid convergence check?
  awk -v k="$1" '$1==k {print ($2==1 ? "" : "--skip-convergence")}' faseC_manifest.txt
}

# ---------------------------------------------------- 4. instance validation
# CLI run, Diagnose()/checkNrSteps()/DiagnoseRiversystemConfiguration(), water
# balance, and rho/R reported BEFORE any gap.
banner "4. validate_instance.py (all Phase C cells)"
cp -p validation_instance.json .validation_instance.bak 2>/dev/null || true
$PY validate_instance.py $CELLS 2>&1 | tee faseC_validate_instance.log
INST_RC=${PIPESTATUS[0]}
mv -f validation_instance.json validation_instance_faseC.json
mv -f .validation_instance.bak validation_instance.json 2>/dev/null || true
[ "$INST_RC" -eq 0 ] || printf '\n!!! some instances FAILED validation -- see faseC_validate_instance.log\n'

# ----------------------------------------------------- 5. replica validation
# Volume scaling moves the reservoir curve, so the replica's ArrayCurve lookup
# has to hit the NEW curve. |dVF| < 0.05 EUR. Critical on s_R = 1.25/1.5/8,
# which have never been built before.
#
# Note the nine cells of 2026-08-04 were never replica-validated -- only
# hjelle/gresse and later toppsy/kroknesvatn ever were, because the script
# overwrote one shared report each run. Hence --out and one process per
# instance: ~2m15s each, independent, so they parallelise cleanly.
banner "5. validate_replica.py (all Phase C cells, parallel)"
rm -f faseC_replica_*.json
printf '%s\n' $CELLS | xargs -P 4 -I{} sh -c \
  "$PY -u validate_replica.py {} --out faseC_replica_{}.json > faseC_replica_{}.log 2>&1; \
   printf '%s replica rc=%s\n' {} \$?"
REP_FAIL=0
for c in $CELLS; do
  grep -q "^ALL PASS" "faseC_replica_${c}.log" 2>/dev/null || { echo "  REPLICA FAIL: $c"; REP_FAIL=1; }
done
$PY -c "
import glob, json
out = {}
for fn in sorted(glob.glob('faseC_replica_*.json')):
    out.update(json.load(open(fn)))
json.dump(out, open('validation_replica_faseC.json', 'w'), indent=2)
print(f'merged {len(out)} instances into validation_replica_faseC.json')
"
[ "$REP_FAIL" -eq 0 ] || die "replica validation FAILED after volume scaling -- \
a gap measured against a replica that does not reproduce HERSS is meaningless"

# ------------------------------------------------------------ measure a cell
measure() {  # measure <slug> [extra flags...]
  local slug="$1"; shift
  printf '>>> start %s  [%s]\n' "$slug" "$(date -u +%H:%M:%S)"
  $PY -u run_measurement.py "$slug" --auto-grid "$@" > "faseC_${slug}.log" 2>&1
  local rc=$?
  printf '<<< done  %s  rc=%s  [%s]\n' "$slug" "$rc" "$(date -u +%H:%M:%S)"
  $PY faseC_summary.py >/dev/null 2>&1 || true
  return $rc
}
export -f measure
export PY

wave() {  # wave <parallelism> <slug>...
  local par="$1"; shift
  printf '\n--- wave: -P %s : %s ---\n' "$par" "$*"
  printf '%s\n' "$@" | xargs -P "$par" -I{} bash -c '
    slug="{}"
    flags=$(awk -v k="$slug" "\$1==k {print (\$2==1 ? \"\" : \"--skip-convergence\")}" faseC_manifest.txt)
    measure "$slug" $flags'
  $PY faseC_summary.py
}

# ------------------------------------------------------------ 6. bridge cell
# syn_rho1_R4 exactly as it sits on disk, re-measured on the derived grid
# (8001 -> ~27000 points). Any change in its gap is PURE resolution. Run alone,
# before anything else, because it decides whether the 2026-08-04 cells and
# these ones may share a table.
banner "6. bridge cell: syn_rho1_R4 on the derived grid"
measure syn_rho1_R4 --skip-convergence --out-suffix _fasec
$PY faseC_summary.py
$PY -c "
import json
b = json.load(open('faseC_summary.json'))['bridge']
print()
print('BRIDGE VERDICT:', b['status'])
print(b['text'])
print()
if b['status'] != 'merge_allowed':
    print('=> Resten av natten kjores som normalt, men gamle og nye celler')
    print('   holdes i SEPARATE tabeller. faseC_summary.py handhever dette.')
"

# ----------------------------------------------------------------- 7. cells
# Order is priority order; parallelism is set by memory, not by cores. The
# machine has 16 cores but ~5 GB free, and the DP value list alone is
# T * n_grid * 2 * 8 bytes ~ 340 MB at s_R = 8, ~1.4 GB during a convergence
# check. Big cells therefore run few-at-a-time.
banner "7. cells 1-2: crossing bracket (rho = 1, s_R = 1.25 / 1.5)"
wave 2 syn_rho1_R1p25 syn_rho1_R1p5

banner "7. cell 3: rho = 1, s_R = 8 (largest grid + convergence -- alone)"
wave 1 syn_rho1_R8

banner "7. cells 4,7,10: small cells (s_R <= 2)"
wave 3 syn_rho0p782_R2 syn_rho1p75_R1 syn_rho0p782_R1p25

banner "7. cells 5,8: s_R = 4"
wave 2 syn_rho0p782_R4 syn_rho1p221_R4

banner "7. cells 6,9: s_R = 8"
wave 2 syn_rho0p782_R8 syn_rho1p733_R8

# ------------------------------------------------------------------ 8. done
banner "8. summary"
$PY faseC_summary.py
printf '\nresults on disk:\n'
ls -la result_syn_*.json
printf '\nmissing cells (if any):\n'
for c in $CELLS; do [ -f "result_${c}.json" ] || echo "  MISSING $c"; done
banner "Fase C end (started $STAMP)"
