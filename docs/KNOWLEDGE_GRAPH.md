# JAPAQ-KG — the knowledge graph

JAPAQ-KG holds the records of the feature table as a Neo4j property graph. Each row of
`japaq_fe_v1.0.0` is one `ObservedPollutant` node and one `ObservationTime` node with the same
`tid`; each station is one `Station` node and one `Location` node.

## Schema

```
(:Station)-[:LOCATED_AT]->(:Location)                         1,806 relationships   1:1
(:ObservedPollutant)-[:RECORDED_BY]->(:Station)          110,328,514 relationships   N:1
(:ObservedPollutant)-[:OBSERVED_AT]->(:ObservationTime)  110,328,514 relationships   1:1
(:ObservationTime)-[:AT_LOCATION]->(:Location)           110,328,514 relationships   N:1
```

| Node | Count | Key | Properties |
|---|---|---|---|
| `Station` | 1,806 | `sid` | `stationname_en`, `stationtype_en`, `stationname_resolved`, `stationtype_resolved`, `source` |
| `Location` | 1,806 | `sid` | `prefecture_en`, `city_en`, `street_en`, `pincode`, `lat`, `lon`, `prefecture_resolved`, `city_resolved`, `street_resolved`, `lat_resolved`, `lon_resolved`, `metadata_source`, `metadata_note` |
| `ObservationTime` | 110,328,514 | `tid` | `obsdate`, `year`, `month`, `month_name`, `weekday_name`, `hour`, `dayType`, `timeCategory`, `season` |
| `ObservedPollutant` | 110,328,514 | `tid` | `pm25`, `so2`, `no`, `spm`, `ox`, `pm25_level` … `ox_level`, `pm25_flag`, `no_flag`, `spm_flag`, `ox_flag`, `ws`, `temp`, `hum`, `ws_level`, `ws_flag`, `temp_flag`, `hum_flag` |

Empty values are absent properties (Neo4j has no null property values): `p.pm25 IS NULL` is true when
the value is missing or was removed by quality control. Meanings and units: `DATA_DICTIONARY.md`.

**Constraints** (unique): `Station.sid`, `Location.sid`, `ObservationTime.tid`, `ObservedPollutant.tid`.
**Indexes**: `Station.stationname_en`; `Location.prefecture_en`, `city_en`, `prefecture_resolved`,
`city_resolved`; `ObservationTime.year`, `month`, `hour`, `season`, `dayType`, `timeCategory`;
`ObservedPollutant.pm25_level`, `so2_level`, `no_level`, `spm_level`, `ox_level`, `ws_level`.

Size: 220,660,640 nodes and 330,987,348 relationships; about 85 GB of disk once loaded; the dump file
is 14 GB.

## Loading the graph with Docker

Works the same on Linux, macOS (Intel or Apple silicon) and Windows (Docker Desktop with WSL 2).
Install Docker from https://docs.docker.com/get-docker/ first.

```bash
# 1. put the dump where the loader can see it (the file must be called neo4j.dump)
mkdir -p japaq-neo4j/backups japaq-neo4j/data
cp japaq_v1.0.0/5_JAPAQ-KG/japaq_kg_v1.0.0.dump japaq-neo4j/backups/neo4j.dump

# 2. load it into an empty database folder (takes about 10 minutes)
docker run --rm \
  -v "$PWD/japaq-neo4j/data:/data" -v "$PWD/japaq-neo4j/backups:/backups" \
  neo4j:2026.02.2 neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true

# 3. start the database (choose your own password; at least 8 characters)
docker run -d --name japaq-kg -p 7474:7474 -p 7687:7687 \
  -v "$PWD/japaq-neo4j/data:/data" \
  -e NEO4J_AUTH=neo4j/choose-a-password \
  -e NEO4J_server_memory_pagecache_size=16G \
  -e NEO4J_server_memory_heap_initial__size=8G -e NEO4J_server_memory_heap_max__size=8G \
  neo4j:2026.02.2
```

Wait about a minute, then open **http://localhost:7474** (Neo4j Browser), connect to
`neo4j://localhost:7687` as user `neo4j` with your password, and type a query.

Stop and restart later with `docker stop japaq-kg` and `docker start japaq-kg`; the data stay in
`japaq-neo4j/data`. On Linux, add `--user "$(id -u):$(id -g)"` to both `docker run` commands if you want
the files to belong to your user.

Memory: the page cache caches the database files. 16 GB is enough for queries that start from a station,
a place, a year, or a severity label; whole-network aggregations run faster with more page cache (up to
the database size) or on the Parquet table instead.

## Installing Neo4j without Docker

1. **Install Java.** The official Neo4j 2026.02 image runs on Java 25; install the version listed in
   Neo4j's system requirements (https://neo4j.com/docs/operations-manual/current/installation/requirements/),
   for example Eclipse Temurin 25 from https://adoptium.net/. Check with `java -version`.
2. **Install Neo4j Community Edition 2026.02** from https://neo4j.com/deployment-center/: on Linux and
   macOS, download the `.tar.gz` and unpack it (`tar -xzf neo4j-community-2026.02.2-unix.tar.gz`); on
   Windows, unpack the `.zip`. Neo4j Desktop (https://neo4j.com/download/) is an alternative with a
   graphical interface: create a local database there, then use its "Open folder → Terminal" to run
   the commands below.
3. **Load the dump** (from the Neo4j folder):

   ```bash
   mkdir -p backups && cp /path/to/japaq_v1.0.0/5_JAPAQ-KG/japaq_kg_v1.0.0.dump backups/neo4j.dump
   bin/neo4j-admin database load neo4j --from-path=backups --overwrite-destination=true
   ```

   (On Windows use `bin\neo4j-admin.bat` and backslashes.)
4. **Set memory** in `conf/neo4j.conf`:

   ```
   server.memory.pagecache.size=16g
   server.memory.heap.initial_size=8g
   server.memory.heap.max_size=8g
   ```

5. **Set a password and start**:

   ```bash
   bin/neo4j-admin dbms set-initial-password choose-a-password
   bin/neo4j start        # or: bin/neo4j console  (runs in the foreground)
   ```

   Open http://localhost:7474. Stop with `bin/neo4j stop`.

## Querying

In Neo4j Browser or `cypher-shell -u neo4j -p choose-a-password`. Start queries from an indexed
property — a station (`sid`), a place (`prefecture_resolved`, `city_resolved`), a year, or a severity
label — so that the database does not have to scan all 110 million observations.

```cypher
// hourly PM2.5 at one station on one day, without flagged values
MATCH (p:ObservedPollutant)-[:RECORDED_BY]->(:Station {sid: '13101010'}),
      (p)-[:OBSERVED_AT]->(t:ObservationTime)
WHERE t.obsdate STARTS WITH '2023-07-01' AND p.pm25_flag IS NULL
RETURN t.obsdate AS hour, p.pm25 AS pm25, p.pm25_level AS level ORDER BY hour;

// hours with Unhealthy PM2.5 in 2023, by prefecture
MATCH (p:ObservedPollutant {pm25_level: 'Unhealthy'})-[:OBSERVED_AT]->(t:ObservationTime {year: 2023}),
      (t)-[:AT_LOCATION]->(l:Location)
WHERE p.pm25_flag IS NULL
RETURN l.prefecture_resolved AS prefecture, count(*) AS hours ORDER BY hours DESC LIMIT 5;
```

More: `examples/example_queries.cypher`. Stations and their codes: `japaq_station_metadata_v1.0.0.csv`.

## From Python

```python
from neo4j import GraphDatabase          # pip install neo4j
drv = GraphDatabase.driver("neo4j://localhost:7687", auth=("neo4j", "choose-a-password"))
q = """MATCH (l:Location) RETURN l.prefecture_resolved AS prefecture, count(*) AS stations
       ORDER BY stations DESC LIMIT 5"""
with drv.session() as s:
    print(s.run(q).data())
drv.close()
```

For graph learning, export the part you need (for example one prefecture and one year) with a Cypher
query into a table, or use the Neo4j Graph Data Science library.

## RDF and SOSA/SSN

The graph is not an RDF resource, but `rdf_mapping/japaq_kg_sosa_mapping.ttl` maps its labels,
relationships, and properties to W3C SOSA/SSN, OWL-Time, and GeoSPARQL, and
`rdf_mapping/neosemantics_export.cypher` exports any subset as SOSA/SSN RDF with the Neosemantics (n10s)
plug-in (one `sosa:Observation` per measurement, with its severity label and quality flag).

## Relation to the AirCypher benchmark

JAPAQ-KG is the evaluation substrate of the AirCypher text-to-Cypher benchmark (IEEE BigData 2026). The
quality flags, meteorological variables, resolved station fields, and source properties were added
without changing any node, relationship, or original value: all 4,000 reference queries of the benchmark
return the same rows on this graph (`validation/benchmark_compatibility/`).
