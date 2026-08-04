#!/usr/bin/env bash
# Task C: the synthetic rho/R separation grid.
#
# SYNTHETIC INSTANCES -- not slices of uTAHPS. Results belong in their own
# chapter and must never be mixed into conclusions about the real system.
#
# Cells are listed in priority order (see params.SYNTHETIC_PRIORITY): the
# R_scale = 1 row first, then the rho = 1 column, then two diagonal corners.
# 16 cells is more than one night; whatever finishes is reported, and the report
# states explicitly which cells ran.
#
# Usage:  ./run_synthetic_grid.sh [parallelism]      (default 4)
set -u
cd "$(dirname "$0")"
PAR="${1:-4}"
PY=../../.venv/bin/python

CELLS=(
  syn_rho0p5_R1 syn_rho0p75_R1 syn_rho1_R1 syn_rho1p25_R1
  syn_rho1_R0p5 syn_rho1_R2 syn_rho1_R4
  syn_rho0p5_R0p5 syn_rho1p25_R4
)

printf '%s\n' "${CELLS[@]}" | xargs -P "$PAR" -I{} \
  sh -c 'echo "start {}"; '"$PY"' -u run_measurement.py {} > run_{}.log 2>&1; \
         echo "done {} rc=$?"'
