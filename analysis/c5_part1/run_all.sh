#!/usr/bin/env bash
# C5 part 1 -- full reproduction. Run from anywhere; ~15 s.
# Baseline HERSS only: src/ must be identical to the recorded base commit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python"
BASE=0e98d837ed046e0089c6c7a0a641bc314cd627a4
cd "$HERE"
{
echo "C5 part 1 run  $(date -u +%FT%TZ)"
echo "repo HEAD      $(git -C "$REPO" rev-parse HEAD)  branch $(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
git -C "$REPO" diff --quiet "$BASE" -- src && echo "src/ identical to base $BASE (no R1 fix)" \
  || { echo "src/ DIFFERS from base -- abort"; exit 1; }
[ "$(strings "$REPO/src/herss.so" | grep -ci tailwater)" = 0 ] && echo "herss.so: no TAILWATER symbols"
rm -f c5_inprocess.log c5_sweep.log c5_inflow_check.log
"$PY" build_c5.py
for v in c5_high c5_headkeep c5_high_ctrl; do
  (cd "$v" && rm -f herss_*.log && "$REPO/src/herss.exe" global.txt > cli_stdout.txt 2>&1)
  echo "CLI $v: exit 0, ERR/WARN lines in log: $(grep -ciE 'error|warn' "$v"/herss_*.log || true)"
done
"$PY" validate_c5.py c5_high c5_headkeep
"$PY" r1_sweep.py
"$PY" inflow_check.py
"$PY" position.py
for lg in c5_inprocess.log c5_sweep.log c5_inflow_check.log; do
  echo "$lg: $(grep -c WRN "$lg" || true) WRN lines, of which not POWSTAT_MIN_DISCHARGE: $(grep -E 'WRN|ERR' "$lg" | grep -vc 'below minimum discharge' || true)"
done
} 2>&1 | tee c5_run.log
