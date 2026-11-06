# JAPAQ — Japan Air Quality: hourly observations and knowledge graph, 2018–2025

[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data DOI](https://img.shields.io/badge/data-10.5281%2Fzenodo.21458239-informational)](https://doi.org/10.5281/zenodo.21458239)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](requirements.txt)
[![Neo4j 2026.02](https://img.shields.io/badge/neo4j-2026.02-008cc1.svg)](docs/KNOWLEDGE_GRAPH.md)
[![GitHub issues](https://img.shields.io/github/issues/aircypher/JAPAQ)](https://github.com/aircypher/JAPAQ/issues)

This repository holds the **code** that builds and validates JAPAQ, a dataset of Japan's national air
quality monitoring network. Its two products are built from the same records: **JAPAQ-FE**, the
feature-enriched hourly table (**110,328,514 records from 1,806 stations, January 2018 – December
2025**), and **JAPAQ-KG**, the same records as a Neo4j knowledge graph. They cover five pollutants
(PM2.5, SO2, SPM, and Ox, which have Japanese Environmental Quality Standards, and NO) and three
meteorological variables, with documented quality control
and a Neo4j knowledge graph (JAPAQ-KG) of the same records.

The **data** are on Zenodo: https://doi.org/10.5281/zenodo.21458239 (one zip, ~17 GB).

# Table of contents

- [Introduction](#introduction)
- [Start here: which path is yours?](#start-here-which-path-is-yours)
- [What is in the dataset](#what-is-in-the-dataset)
- [How the dataset is built](#how-the-dataset-is-built)
- [Try it in five minutes](#try-it-in-five-minutes)
- [Use the knowledge graph](#use-the-knowledge-graph)
- [Rebuild everything from scratch](#rebuild-everything-from-scratch)
- [Validation](#validation)
- [Repository layout](#repository-layout)
- [Things every user should know](#things-every-user-should-know)
- [Frequently asked questions](#frequently-asked-questions)
- [Citation](#citation)
- [License and data terms](#license-and-data-terms)
- [Getting help](#getting-help)

# Introduction

Japan's Ministry of the Environment publishes hourly air quality measurements from about 1,800
monitoring stations through the Soramame portal. The files are released per period, mix genuine
measurements with instrument fill codes (for example 65,535 µg/m³ for PM2.5), and lack station
information for stations that closed before the current station list was published. Every group that
uses them for nationwide, multi-year research has to merge, clean, and enrich them again.

JAPAQ does this once, documents every step, and releases the result with the evidence to check it:

- ✅ **Scope** — five pollutants (four with Japanese standards, plus NO) and three meteorological variables, eight years, one
  record per station and hour.
- 🔍 **Auditable quality control** — 2,235,358 non-physical values removed by three documented rules;
  implausible values flagged, not deleted; every change listed with its original value in a log; the raw
  file released alongside, so every change can be checked and reversed.
- 🗺️ **Complete context** — station location and type for every record (including 143 closed stations
  recovered from official sources), calendar and holiday attributes, severity labels referenced to the
  standards, and a Beaufort wind class.
- 🕸️ **Two forms of the same data** — a table (CSV and Parquet) and a Neo4j knowledge graph, already used
  as the substrate of a text-to-Cypher benchmark.
- 🔁 **Reproducible** — `run_all.sh` rebuilds the release from the raw file and reproduces the released
  tables byte for byte.

# Start here: which path is yours?

| You are… | You want… | Go to |
|---|---|---|
| **New to programming or data** (student, journalist, policy analyst) | Look at the data, make a chart | [Try it in five minutes](#try-it-in-five-minutes) and [Things every user should know](#things-every-user-should-know) |
| **Domain scientist** (atmospheric science, epidemiology, environmental health) | Clean hourly data with station metadata | [What is in the dataset](#what-is-in-the-dataset), [Things every user should know](#things-every-user-should-know), [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) |
| **Computer scientist** (databases, graph learning, text-to-Cypher) | The graph, its schema, loading and querying | [Use the knowledge graph](#use-the-knowledge-graph), [`docs/KNOWLEDGE_GRAPH.md`](docs/KNOWLEDGE_GRAPH.md) |
| **Reviewer or anyone checking the work** | Rebuild and verify | [Rebuild everything from scratch](#rebuild-everything-from-scratch), [Validation](#validation) |

# What is in the dataset

The Zenodo zip unpacks to a folder `japaq_v1.0.0/`:

| File | What it is | Size |
|---|---|---|
| `japaq_fe_v1.0.0.parquet` / `.csv` | **Start here.** The analysis-ready table: 110,328,514 rows × 48 columns | 0.5 GB / 35 GB |
| `japaq_raw_hourly_obs_v1.0.0.csv` | Raw hourly values exactly as downloaded (station, time, 5 pollutants, 3 weather variables) | 6 GB |
| `japaq_corrections_log_v1.0.0.csv` | Every value set to null or flagged, with original value, stage, and rule | 0.2 GB |
| `japaq_station_metadata_v1.0.0.csv` | English metadata for 1,825 stations, with the source of each station's metadata | 0.4 MB |
| `japaq_raw_station_list_v1.0.0.csv` | Original Soramame station list (Japanese) | 0.3 MB |
| `japaq_kg_v1.0.0.dump` | Neo4j database dump of the same records | 14 GB |
| `japaq_romanisation_log_v1.0.0.csv`, `sources.csv`, `STATION_METADATA_METHOD.md` | Romanised addresses, citations of all sources, method for recovered stations | small |
| `README.md`, `DATA_SOURCES_AND_TERMS.md`, licences, `CHECKSUMS_SHA256.txt` | Documentation | small |

One row of the feature table = one station and one hour. Every column is explained in
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).

# How the dataset is built

```
 Soramame hourly files ──► japaq_raw_hourly_obs (raw, as downloaded)
                                   │
 Soramame station list ─┐          ▼
 NIES station files     ├─► stations/  recover 143 closed stations, romanise addresses
 MIC municipality codes ┘          │       └─► japaq_station_en
                                   ▼
                       pipeline/01  keep rows with ≥1 valid pollutant value (110,328,514)
                                    Stage 1–3: negative values, fill codes, station artifacts → null
                                    Stage 4:   implausible pollutant values → flagged, kept
                                    Stage W:   meteorological values outside physical ranges → null
                                    enrichment: station (SSR), calendar (TSR), severity (PSR), Beaufort
                       pipeline/02  Stage 4 for meteorology: stuck sensors, disagreement with neighbours
                                   │
                                   ├─► JAPAQ-FE (table) + japaq_corrections_log
                                   ▼
                       pipeline/03–04  Neo4j bulk import ─► JAPAQ-KG (graph)
                                   │
                                   ▼
                       validation/  graph vs files, graph vs raw, structure, benchmark, paper numbers
```

# Try it in five minutes

You need Python 3 and two packages. No database is needed for the table.

```bash
pip install duckdb pandas
```

Download and unpack the Zenodo zip, then:

```bash
python examples/quickstart.py japaq_v1.0.0/4_JAPAQ-FE/japaq_fe_v1.0.0.parquet
```

It prints the size of the table, the monthly mean PM2.5 in Tokyo in 2023, the share of hours per
severity label, and one station-day of pollutant and weather values. The script is short and commented:
change the prefecture, year, or pollutant and run it again.

**In a notebook or Python session**

```python
import duckdb
f = "japaq_v1.0.0/4_JAPAQ-FE/japaq_fe_v1.0.0.parquet"
df = duckdb.sql(f"""
    SELECT obsdate, pm25, pm25_level FROM '{f}'
    WHERE prefecture_resolved = 'Osaka' AND year = 2024 AND month = 1 AND pm25_flag IS NULL
""").df()          # a pandas DataFrame: plot with df.plot(...) or save with df.to_csv(...)
```

**In R** (`install.packages(c("arrow", "dplyr"))`)

```r
library(arrow); library(dplyr)
d <- open_dataset("japaq_v1.0.0/4_JAPAQ-FE/japaq_fe_v1.0.0.parquet")
d |> filter(prefecture_resolved == "Osaka", year == 2024, is.na(pm25_flag)) |>
     group_by(month) |> summarise(pm25 = mean(pm25, na.rm = TRUE)) |> collect()
```

Do not open the 35 GB CSV in a spreadsheet program; use the Parquet file with DuckDB, pandas,
R/arrow, or Spark.

# Use the knowledge graph

JAPAQ-KG has four node types and four relationship types:

```
(:Station)-[:LOCATED_AT]->(:Location)
(:ObservedPollutant)-[:RECORDED_BY]->(:Station)
(:ObservedPollutant)-[:OBSERVED_AT]->(:ObservationTime)-[:AT_LOCATION]->(:Location)
```

One `ObservedPollutant` node holds the measurements, severity labels, and quality flags of one
station-hour and has the same `tid` as the row of the feature table. The full schema, all properties,
and indexes are in [`docs/KNOWLEDGE_GRAPH.md`](docs/KNOWLEDGE_GRAPH.md).

**With Docker (recommended, any operating system):**

```bash
mkdir -p japaq-neo4j/backups
cp japaq_v1.0.0/5_JAPAQ-KG/japaq_kg_v1.0.0.dump japaq-neo4j/backups/neo4j.dump
docker run --rm -v "$PWD/japaq-neo4j/data:/data" -v "$PWD/japaq-neo4j/backups:/backups" \
  neo4j:2026.02.2 neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
docker run -d --name japaq-kg -p 7474:7474 -p 7687:7687 \
  -v "$PWD/japaq-neo4j/data:/data" -e NEO4J_AUTH=neo4j/choose-a-password \
  -e NEO4J_server_memory_pagecache_size=16G -e NEO4J_server_memory_heap_max__size=8G \
  neo4j:2026.02.2
```

Open http://localhost:7474, log in as `neo4j` with your password, and run a query:

```cypher
MATCH (p:ObservedPollutant)-[:RECORDED_BY]->(:Station {sid: '13101010'}),
      (p)-[:OBSERVED_AT]->(t:ObservationTime)
WHERE t.obsdate STARTS WITH '2023-07-01' AND p.pm25_flag IS NULL
RETURN t.obsdate AS hour, p.pm25 AS pm25, p.pm25_level AS level ORDER BY hour;
```

**Without Docker** (Neo4j installed directly on Linux, macOS, or Windows): see
[`docs/KNOWLEDGE_GRAPH.md`](docs/KNOWLEDGE_GRAPH.md#installing-neo4j-without-docker).

More queries: [`examples/example_queries.cypher`](examples/example_queries.cypher) (each runs in under
a second). The loaded graph needs about 85 GB of disk; 16 GB of page cache is enough for selective
queries.

# Rebuild everything from scratch

For reviewers and anyone who wants to check or extend the processing.

```bash
git clone https://github.com/aircypher/JAPAQ.git && cd REPO
pip install -r requirements.txt                     # Python 3.12
# unpack the Zenodo zip; the pipeline reads the raw hourly file and the station list from it
bash run_all.sh ./japaq_v1.0.0 ./work ./out ./graph
```

| Step | Time on a 32-core server | Output |
|---|---|---|
| Station metadata (`stations/`; downloads NIES and MIC files and checks their SHA-256) | ~1 min | `japaq_station_metadata_v1.0.0.csv` |
| Tables (`pipeline/01–02`) | ~16 min | feature table, corrections log, `sources.csv` |
| Graph (`pipeline/03–04`, Docker) | ~50 min | Neo4j database in `./graph` |

Requirements: about 40 GB RAM for the table steps (`JAPAQ_MEMORY`, default `40GB`; DuckDB spills to
disk beyond that), 150 GB disk, Docker for the graph (`NEO4J_PAGECACHE`, `NEO4J_HEAP` set its memory).
Omit `./graph` to build only the tables. Compare `./out` with the Zenodo files using
`CHECKSUMS_SHA256.txt`: the CSV files, the log, and the station files are reproduced byte for byte.

The station geocoding (`stations/00_geocode_station_list.py`) needs network access to OpenStreetMap
Nominatim and gives different results as OpenStreetMap changes; the pipeline therefore uses the January
2026 result in `inputs/station_en_snapshot_2026-01.csv`.

# Validation

| Script | What it checks | Result for the release |
|---|---|---|
| `validation/verify_graph.py` | Graph vs released files: every station node, all counts, and all values, labels, flags, time attributes, and links for 8,313 records | 0 differences |
| `validation/source_fidelity.py` | Graph vs raw file: 10,000 random records and 5,000 corrected cells | unchanged values equal raw; corrected values null; logged originals equal raw |
| `validation/structural_checks.cypher` | Labels, relationship types, orphan nodes, link cardinality | 4 labels, 4 types, 0 orphans, 0 broken links |
| `validation/benchmark_compatibility/` | All 4,000 reference queries of the AirCypher benchmark on the released graph | same rows for every query |
| `validation/paper_numbers.py`, `validation/make_figures.py` | Every number and the data figures of the article | — |

The graph checks read `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS`, for example
`NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASS=choose-a-password python validation/verify_graph.py ./out ./work/station_resolved.csv`.

# Repository layout

```
run_all.sh        one command: station metadata → tables → graph
stations/         00 geocode · 01 download NIES/MIC · 02–04 recover closed stations · 05 romanise · 06 station table
pipeline/         01 quality control + enrichment · 02 meteorological flags · 03 import files · 04 Neo4j build
validation/       graph vs files · graph vs raw · structure · benchmark compatibility · paper numbers and figures
rdf_mapping/      W3C SOSA/SSN mapping (Turtle) and an RDF export query for Neosemantics
examples/         quickstart.py (table) · example_queries.cypher (graph)
docs/             DATA_DICTIONARY.md · KNOWLEDGE_GRAPH.md · STATION_METADATA_METHOD.md
inputs/           geocoded station list (January 2026) and checksums of third-party files
```

# Things every user should know

1. **Exclude flagged values.** Columns ending in `_flag` name the quality rule that marked a value as
   implausible (for example a sensor stuck for 24 hours, or a PM2.5 reading of 8,517 µg/m³). They are
   kept so that nothing is hidden; drop them for most analyses: `WHERE pm25_flag IS NULL`.
2. **Use the `_resolved` station columns.** The original station columns are empty for 143 stations that
   closed before January 2026; `prefecture_resolved`, `city_resolved`, `lat_resolved`, … are complete.
3. **Severity labels are descriptive.** Most Japanese standards are defined on daily or annual averages;
   the labels apply them to hourly values, so they are not a legal compliance assessment.
4. **Timestamps mark the end of the hour**, in Japan Standard Time: `2023-07-02 00:00:00` is the hour
   from 23:00 to 24:00 on 1 July (Soramame's hour-24 convention).
5. **Four periods have no data at all** in the source files: 12–31 July 2019, 29–31 March 2021,
   27–30 September 2022, and 1 October – 31 December 2024. Annual statistics for 2024 cover January to
   September only.
6. **Values are provisional.** Soramame publishes provisional values; confirmed values are published later
   by NIES and may differ slightly.
7. **Meteorology comes from air quality stations**, not from Japan Meteorological Agency stations; use it
   as covariates for the pollutants of the same station and hour.

# Frequently asked questions

**Which file should I use?** The Parquet feature table, for almost everything. Use the graph for graph
tools or Cypher, and the raw file to check or redo the cleaning.

**How do I get one station's data?** Find its code (`sid`) in `japaq_station_metadata_v1.0.0.csv` and filter
`WHERE sid = '…'`.

**Why are some values empty?** Either the station did not measure that variable at that hour, or quality
control set the value to null; the corrections log tells you which (`action = 'nulled'`).

**Can I undo a correction?** Yes: the log holds the original value of every nulled or flagged cell, keyed
by `tid` and `variable`.

**Why does the graph have 220 million nodes?** Every station-hour has its own time and observation node,
so that each node maps to exactly one row of the table.

**Is the graph RDF?** No, it is a Neo4j property graph; `rdf_mapping/` maps it to W3C SOSA/SSN and exports
any part of it as RDF.

# Citation

If you use the data, please cite the dataset and the article:

```bibtex
@dataset{japaq_data,
  author    = {Pogaku, Arjun Chakravarthi and Rage, Uday Kiran},
  title     = {{JAPAQ}: hourly air quality observations and knowledge graph for Japan, 2018--2025},
  version   = {1.0.0},
  publisher = {Zenodo},
  year      = {2026},
  doi       = {10.5281/zenodo.21458239}
}
@article{japaq_article,
  author  = {Pogaku, Arjun Chakravarthi and Rage, Uday Kiran},
  title   = {A Nationwide Dataset of Hourly Air Quality Observations in Japan with Documented Quality Control},
  journal = {Scientific Data},
  year    = {2026},
  note    = {DOI to be added on publication}
}
```

and give the source credit required by the data providers (see `DATA_SOURCES_AND_TERMS.md` in the zip):
"Source: Ministry of the Environment, Japan, Atmospheric Environmental Regional Observation System
(Soramame), https://soramame.env.go.jp/. Processed by the JAPAQ authors." GitHub's "Cite this repository"
button uses [`CITATION.cff`](CITATION.cff).

# License and data terms

- **Code:** MIT ([`LICENSE`](LICENSE)).
- **Data (Zenodo):** the authors' contributions under CC BY 4.0; the measurements under the terms of the
  Ministry of the Environment, Japan (Public Data License 1.0), the local governments operating the
  stations, and NIES; English addresses from OpenStreetMap under ODbL 1.0.
- `inputs/station_en_snapshot_2026-01.csv` contains OpenStreetMap data under ODbL (see
  [`inputs/README.md`](inputs/README.md)); it is not covered by the MIT licence.

# Getting help

- Questions or problems: open an issue at https://github.com/aircypher/JAPAQ/issues.
- Contact: Arjun Chakravarthi Pogaku (arjun.chakravarthip@gmail.com), The University of Aizu.
