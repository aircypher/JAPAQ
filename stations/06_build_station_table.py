"""
06_build_station_table.py — the station metadata of the release.

Combines
  * the January 2026 station list, geocoded (inputs/station_en_snapshot_2026-01.csv, 1,682 stations),
  * its romanised copy (05_romanise_addresses.py), and
  * the recovered stations (04_recover_missing.py),
into
  <out_dir>/japaq_station_en_v1.0.0.csv   release file: every station described by the same columns
                                          (recovered and romanised values written into them), with
                                          metadata_source, metadata_note and source;
  <work_dir>/station_resolved.csv         for pipeline/01_build_tables.py: the original columns of the
                                          station list (as used by the knowledge graph) and the
                                          *_resolved columns (= the release file).

Usage: python stations/06_build_station_table.py <station_snapshot.csv> <work_dir> <out_dir>
"""
import os
import sys
import duckdb

SNAP, WORK, OUT = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)
c = duckdb.connect()
c.execute(f"""
CREATE TABLE st AS
WITH orig AS (SELECT * FROM read_csv('{SNAP}', all_varchar=true, header=true)),
     rom  AS (SELECT * FROM read_csv('{WORK}/station_en_romanised.csv', all_varchar=true, header=true)),
     rec  AS (SELECT * FROM read_csv('{WORK}/recovered_stations.csv', all_varchar=true, header=true)),
     ids  AS (SELECT sid FROM orig UNION SELECT sid FROM rec)
SELECT ids.sid,
  o.stationname_en, o.stationtype_en, o.prefecture_en, o.city_en, o.street_en, o.pincode,
  TRY_CAST(o.lat AS DOUBLE) lat, TRY_CAST(o.lon AS DOUBLE) lon,
  coalesce(r.stationname_en, x.stationname_en) stationname_resolved,
  coalesce(r.stationtype_en, x.stationtype_en) stationtype_resolved,
  coalesce(r.prefecture_en, x.prefecture_en) prefecture_resolved,
  coalesce(r.city_en, x.city_romaji) city_resolved,
  coalesce(r.street_en, x.street_en) street_resolved,
  coalesce(TRY_CAST(r.lat AS DOUBLE), TRY_CAST(x.lat AS DOUBLE)) lat_resolved,
  coalesce(TRY_CAST(r.lon AS DOUBLE), TRY_CAST(x.lon AS DOUBLE)) lon_resolved,
  CASE WHEN o.sid IS NOT NULL THEN 'station_metadata_snapshot' ELSE x.admin_source END admin_source,
  CASE WHEN o.sid IS NOT NULL THEN r.admin_note ELSE x.admin_note END admin_note
FROM ids LEFT JOIN orig o ON o.sid = ids.sid LEFT JOIN rom r ON r.sid = ids.sid LEFT JOIN rec x ON x.sid = ids.sid""")
SRC = """CASE WHEN admin_source = 'station_metadata_snapshot' THEN 'AEROS;OSM'
              WHEN admin_source LIKE 'nies%' THEN 'AEROS;NIES' ELSE 'AEROS;MIC' END"""
c.execute(f"COPY (SELECT *, {SRC} AS source FROM st ORDER BY sid) TO '{WORK}/station_resolved.csv' (HEADER)")
c.execute(f"""COPY (SELECT sid, stationname_resolved AS stationname_en, stationtype_resolved AS stationtype_en,
    prefecture_resolved AS prefecture_en, city_resolved AS city_en, street_resolved AS street_en, pincode,
    lat_resolved AS lat, lon_resolved AS lon, admin_source AS metadata_source, admin_note AS metadata_note,
    {SRC} AS source FROM st ORDER BY sid) TO '{OUT}/japaq_station_en_v1.0.0.csv' (HEADER)""")
print('stations:', c.execute("SELECT count(*), count(prefecture_resolved), count(lat_resolved) FROM st").fetchone())
print(c.execute("SELECT admin_source, count(*) FROM st GROUP BY 1 ORDER BY 1").fetchall())
