"""
03_make_import_files.py — write neo4j-admin bulk-import CSVs for JAPAQ-KG.

Four node labels and four relationship types; one ObservationTime and one ObservedPollutant node
per row of the feature table, one Station and one Location node per station. The original
properties are those on which the AirCypher benchmark is defined; the release adds:
  Station: stationname_resolved, stationtype_resolved, source
  Location: prefecture_resolved, city_resolved, street_resolved, lat_resolved, lon_resolved,
            metadata_source, metadata_note
  ObservedPollutant: pm25_flag, no_flag, spm_flag, ox_flag, ws, temp, hum, ws_level,
                     ws_flag, temp_flag, hum_flag
Empty cells become absent properties (as in v1.0.0).

Usage: python pipeline/03_make_import_files.py <out_dir> <station_resolved.csv> <import_dir>
"""
import os
import sys
import duckdb

ART, STN, IMP = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(IMP, exist_ok=True)
FEAT = f'{ART}/japaq_feature_obs_v1.0.0.parquet'

c = duckdb.connect()
c.execute("SET threads=16; SET memory_limit='40GB'")
c.execute(f"CREATE VIEW f AS SELECT * FROM '{FEAT}'")
c.execute(f"""CREATE TABLE st AS SELECT * FROM read_csv('{STN}', all_varchar=true, header=true)
              WHERE sid IN (SELECT DISTINCT sid FROM f)""")

def out(name, sql):
    c.execute(f"COPY ({sql}) TO '{IMP}/{name}' (HEADER, DELIMITER ',', QUOTE '\"')")
    print(name, c.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0], flush=True)

out('stations.csv', """SELECT sid AS "sid:ID(Station)", stationname_en, stationtype_en,
    stationname_resolved, stationtype_resolved, source FROM st ORDER BY sid""")
out('locations.csv', """SELECT sid AS "sid:ID(Location)", prefecture_en, city_en, street_en, pincode,
    TRY_CAST(lat AS DOUBLE) AS "lat:double", TRY_CAST(lon AS DOUBLE) AS "lon:double",
    prefecture_resolved, city_resolved, street_resolved,
    TRY_CAST(lat_resolved AS DOUBLE) AS "lat_resolved:double", TRY_CAST(lon_resolved AS DOUBLE) AS "lon_resolved:double",
    admin_source AS metadata_source, admin_note AS metadata_note
    FROM st ORDER BY sid""")
out('observation_time.csv', """SELECT tid AS "tid:ID(Time)", obsdate, "year" AS "year:int", "month" AS "month:int",
    month_name, weekday_name, "hour" AS "hour:int", dayType, timeCategory, season FROM f""")
out('observed_pollutant.csv', """SELECT tid AS "tid:ID(Pollutant)",
    pm25 AS "pm25:double", pm25_level, so2 AS "so2:double", so2_level, "no" AS "no:double", no_level,
    spm AS "spm:double", spm_level, ox AS "ox:double", ox_level,
    pm25_flag, no_flag, spm_flag, ox_flag,
    ws AS "ws:double", "temp" AS "temp:double", hum AS "hum:double", ws_level,
    ws_flag, temp_flag, hum_flag FROM f""")
out('rel_located_at.csv', """SELECT sid AS ":START_ID(Station)", sid AS ":END_ID(Location)" FROM st""")
out('rel_at_location.csv', """SELECT tid AS ":START_ID(Time)", sid AS ":END_ID(Location)" FROM f""")
out('rel_observed_at.csv', """SELECT tid AS ":START_ID(Pollutant)", tid AS ":END_ID(Time)" FROM f""")
out('rel_recorded_by.csv', """SELECT tid AS ":START_ID(Pollutant)", sid AS ":END_ID(Station)" FROM f""")
