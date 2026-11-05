#!/usr/bin/env bash
# 04_build_graph.sh — build JAPAQ-KG with the Neo4j bulk importer in a new Docker container,
# create constraints and indexes, and print node and relationship counts.
# Usage: bash pipeline/04_build_graph.sh <out_dir> <station_resolved.csv> <graph_root> [name] [http_port] [bolt_port]
#   graph_root: empty directory for the database (about 100 GB); the password is written to
#   <graph_root>/neo4j_auth (mode 600). Memory: NEO4J_PAGECACHE (default 32G), NEO4J_HEAP (default 16G).
set -euo pipefail

ART="$1"; STN="$2"; ROOT="$3"
NAME="${4:-japaq-kg}"; HTTP_PORT="${5:-7474}"; BOLT_PORT="${6:-7687}"
IMP="$ROOT/import"
IMAGE=neo4j:2026.02.2
AUTH_FILE="$ROOT/neo4j_auth"
PAGECACHE="${NEO4J_PAGECACHE:-32G}"; HEAP="${NEO4J_HEAP:-16G}"

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "Container $NAME already exists; refusing to overwrite." >&2; exit 1
fi
mkdir -p "$ROOT/data" "$ROOT/logs" "$IMP"

echo "== $(date) writing import files"
"${PYTHON:-python}" "$(dirname "$0")/03_make_import_files.py" "$ART" "$STN" "$IMP"

echo "== $(date) neo4j-admin import"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$ROOT/data:/data" -v "$IMP:/import" \
  -e NEO4J_server_memory_heap_max__size=16G \
  "$IMAGE" neo4j-admin database import full neo4j \
    --overwrite-destination=true --threads=32 --high-parallel-io=on \
    --nodes=Station=/import/stations.csv \
    --nodes=Location=/import/locations.csv \
    --nodes=ObservationTime=/import/observation_time.csv \
    --nodes=ObservedPollutant=/import/observed_pollutant.csv \
    --relationships=LOCATED_AT=/import/rel_located_at.csv \
    --relationships=AT_LOCATION=/import/rel_at_location.csv \
    --relationships=OBSERVED_AT=/import/rel_observed_at.csv \
    --relationships=RECORDED_BY=/import/rel_recorded_by.csv

if [ ! -f "$AUTH_FILE" ]; then
  umask 077; echo "neo4j/$(openssl rand -hex 16)" > "$AUTH_FILE"
fi

echo "== $(date) starting $NAME"
docker run -d --name "$NAME" --user "$(id -u):$(id -g)" \
  -p "$HTTP_PORT:7474" -p "$BOLT_PORT:7687" \
  -v "$ROOT/data:/data" -v "$ROOT/logs:/logs" -v "$IMP:/var/lib/neo4j/import" \
  -e NEO4J_AUTH="$(cat "$AUTH_FILE")" \
  -e NEO4J_server_memory_heap_initial__size="$HEAP" -e NEO4J_server_memory_heap_max__size="$HEAP" \
  -e NEO4J_server_memory_pagecache_size="$PAGECACHE" \
  "$IMAGE" >/dev/null

PASS="$(cut -d/ -f2- "$AUTH_FILE")"
for i in $(seq 1 120); do
  docker exec "$NAME" cypher-shell -u neo4j -p "$PASS" "RETURN 1" >/dev/null 2>&1 && break
  sleep 5
done

echo "== $(date) constraints and indexes"
docker exec -i "$NAME" cypher-shell -u neo4j -p "$PASS" <<'CYPHER'
CREATE CONSTRAINT station_sid IF NOT EXISTS FOR (s:Station) REQUIRE s.sid IS UNIQUE;
CREATE CONSTRAINT location_sid IF NOT EXISTS FOR (l:Location) REQUIRE l.sid IS UNIQUE;
CREATE CONSTRAINT observationtime_tid IF NOT EXISTS FOR (t:ObservationTime) REQUIRE t.tid IS UNIQUE;
CREATE CONSTRAINT observedpollutant_tid IF NOT EXISTS FOR (p:ObservedPollutant) REQUIRE p.tid IS UNIQUE;
CREATE INDEX station_name_idx IF NOT EXISTS FOR (s:Station) ON (s.stationname_en);
CREATE INDEX location_prefecture_idx IF NOT EXISTS FOR (l:Location) ON (l.prefecture_en);
CREATE INDEX location_city_idx IF NOT EXISTS FOR (l:Location) ON (l.city_en);
CREATE INDEX obs_year_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.year);
CREATE INDEX obs_month_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.month);
CREATE INDEX obs_hour_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.hour);
CREATE INDEX obs_season_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.season);
CREATE INDEX obs_daytype_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.dayType);
CREATE INDEX obs_timecategory_idx IF NOT EXISTS FOR (t:ObservationTime) ON (t.timeCategory);
CREATE INDEX pm25_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.pm25_level);
CREATE INDEX so2_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.so2_level);
CREATE INDEX no_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.no_level);
CREATE INDEX spm_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.spm_level);
CREATE INDEX ox_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.ox_level);
CREATE INDEX location_prefecture_resolved_idx IF NOT EXISTS FOR (l:Location) ON (l.prefecture_resolved);
CREATE INDEX location_city_resolved_idx IF NOT EXISTS FOR (l:Location) ON (l.city_resolved);
CREATE INDEX ws_level_idx IF NOT EXISTS FOR (p:ObservedPollutant) ON (p.ws_level);
CALL db.awaitIndexes(7200);
CYPHER

echo "== $(date) counts"
docker exec -i "$NAME" cypher-shell -u neo4j -p "$PASS" --format plain <<'CYPHER'
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label;
MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type;
CYPHER
echo "== $(date) DONE"
