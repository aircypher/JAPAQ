#!/usr/bin/env bash
# run_all.sh — rebuild the JAPAQ release, end to end, from the hourly observations.
#
# Usage: bash run_all.sh <input_dir> <work_dir> <out_dir> [graph_root]
#   input_dir  : japaq_raw_hourly_obs_v1.0.0.csv and japaq_raw_station_list_v1.0.0.csv from the Zenodo record
#   work_dir   : intermediate files (station recovery, downloaded third-party files)
#   out_dir    : the rebuilt release files
#   graph_root : optional; if given, the knowledge graph is built there with Docker (about 100 GB)
# If <work_dir>/external already holds the third-party files, they are not downloaded again.
set -euo pipefail
IN="$1"; WORK="$2"; OUT="$3"; GRAPH="${4:-}"
H="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
SNAP="$H/inputs/station_en_snapshot_2026-01.csv"
HOURLY="$IN/japaq_raw_hourly_obs_v1.0.0.csv"
mkdir -p "$WORK" "$OUT"
step() { echo; echo "== $(date '+%F %T') $*"; }

step "1/9 third-party sources for station metadata"
if [ -d "$WORK/external/nies" ] && [ -d "$WORK/external/mic" ]; then
  (cd "$WORK/external" && sha256sum -c "$H/inputs/external_sha256.txt") || echo "WARNING: external files differ from those used for JAPAQ" >&2
else
  bash "$H/stations/01_download_sources.sh" "$WORK/external"
fi
step "2/9 NIES station files; stations to recover"
"$PY" "$H/stations/02_nies_station_files.py" "$WORK/external" "$SNAP" "$HOURLY" "$WORK"
step "3/9 station codes and official municipality codes"
"$PY" "$H/stations/03_station_codes.py" "$WORK/external" "$SNAP" "$WORK"
step "4/9 metadata of the recovered stations"
"$PY" "$H/stations/04_recover_missing.py" "$WORK"
step "5/9 romanisation of Japanese-script addresses"
"$PY" "$H/stations/05_romanise_addresses.py" "$SNAP" "$WORK/nies_station_latest.csv" "$WORK"
step "6/9 station table"
"$PY" "$H/stations/06_build_station_table.py" "$SNAP" "$WORK" "$OUT"
cp "$WORK/romanisation_log.csv" "$OUT/japaq_romanisation_log_v1.0.0.csv"
cp "$IN/japaq_raw_station_list_v1.0.0.csv" "$OUT/"
cp "$HOURLY" "$OUT/"
step "7/9 quality control, enrichment, feature table, corrections log"
"$PY" "$H/pipeline/01_build_tables.py" "$HOURLY" "$WORK/station_resolved.csv" "$OUT"
step "8/9 meteorological quality flags"
"$PY" "$H/pipeline/02_flag_meteorology.py" "$OUT"
if [ -n "$GRAPH" ]; then
  step "9/9 knowledge graph"
  PYTHON="$PY" bash "$H/pipeline/04_build_graph.sh" "$OUT" "$WORK/station_resolved.csv" "$GRAPH"
else
  step "9/9 knowledge graph skipped (no graph_root given)"
fi
step "done"
