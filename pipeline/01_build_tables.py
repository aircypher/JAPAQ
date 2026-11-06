"""
01_build_tables.py — JAPAQ feature table and corrections log from the hourly observations.

Input
  japaq_raw_hourly_obs_v1.0.0.csv   raw hourly observations (station, timestamp, five pollutants, three
                                meteorological variables), values exactly as downloaded from Soramame
  station_resolved.csv          station metadata from stations/06_build_station_table.py
Steps
  1. Row filter (at least one non-negative value of the five pollutants) and observation IDs
     (tid, ordered by station and time).
  2. Stages 1-3: negative values, fill codes, station- and event-specific artifacts -> value and
     severity label set to null.
  3. Stage 4 (pollutants): implausible high values flagged, not removed (physical cap, stuck run,
     instrument ceiling, short burst, one reviewed event). SO2 is not screened.
  4. Stage W: meteorological values outside physical ranges set to null.
  5. Corrections log (stage, rule, action) for every nulled or flagged value.
  6. Feature table: station attributes (SSR), temporal attributes (TSR), severity labels (PSR),
     Beaufort class, quality flags, source.
The meteorological Stage 4 flags are added by 02_flag_meteorology.py.

Usage: python pipeline/01_build_tables.py <japaq_raw_hourly_obs_v1.0.0.csv> <station_resolved.csv> <out_dir>
Memory: DuckDB is limited to JAPAQ_MEMORY (default 40GB) and spills to <out_dir>/_tmp.
"""
import csv
import os
import sys
import time
import duckdb
import holidays

RAW_SRC, STATION_RESOLVED, OUT = sys.argv[1:4]
TABLE_OUT = f'{OUT}/japaq_fe_v1.0.0'
LOG_OUT = f'{OUT}/japaq_corrections_log_v1.0.0.csv'
SOURCES_OUT = f'{OUT}/sources.csv'
REPORT = f'{OUT}/BUILD_REPORT.txt'
SOURCE = 'AEROS'
SOURCES = [
    ('AEROS', 'Ministry of the Environment, Japan. Atmospheric Environmental Regional Observation System '
     '(AEROS, Soramame)', 'https://soramame.env.go.jp/', 'provisional hourly values (sokuhochi), 2018-2025',
     'Public Data License 1.0 (MOE content); local-government and NIES terms for their stations',
     'measurements, station identifiers, Japanese station metadata'),
    ('OSM', 'OpenStreetMap contributors, via Nominatim reverse geocoding', 'https://www.openstreetmap.org/',
     'retrieved 2026', 'ODbL 1.0',
     'city_en, street_en, pincode of stations with metadata_source = station_metadata_snapshot '
     '(except values replaced by NIES romanisations)'),
    ('NIES', 'National Institute for Environmental Studies, The Environmental Observatory, Air Pollution Monitoring '
     'Data File (station data, TM files FY2016-2024)', 'https://tenbou.nies.go.jp/download/', 'accessed 2026-11-04',
     'NIES terms of use',
     'station metadata of 84 stations (metadata_source = nies_station_file_fy*); official romanised addresses'),
    ('MIC', 'Ministry of Internal Affairs and Communications, Japan. Local government codes and code revision list; '
     'e-Stat Standard Area Code history', 'https://www.soumu.go.jp/denshijiti/code.html; '
     'https://www.e-stat.go.jp/municipalities/cities/areacodesearch', 'accessed 2026-11-04',
     'terms of use of the MIC and e-Stat websites',
     'prefecture, municipality and station type of 59 stations (metadata_source = station_code_mic)'),
]

os.makedirs(OUT, exist_ok=True)
report = []
def log(msg):
    print(msg, flush=True); report.append(msg)

con = duckdb.connect(f'{OUT}/_build.duckdb')
MEM = os.environ.get('JAPAQ_MEMORY', '40GB')
con.execute(f"SET threads=24; SET memory_limit='{MEM}'; SET preserve_insertion_order=true; SET temp_directory='{OUT}/_tmp'")
t0 = time.time()

# ── Step 0: raw file, values as downloaded ───────────────────────────────────────────────
con.execute(f"""CREATE OR REPLACE TABLE raw AS
SELECT stationid, obsdate, so2, "no", spm, ox, pm25, ws, "temp", hum FROM read_csv('{RAW_SRC}', all_varchar=true, header=true)""")
log(f'Step 0: raw file: {con.execute("SELECT count(*) FROM raw").fetchone()[0]:,} rows')

# ── Step 1: row filter + TIDs ────────────────────────────────────────────────────────────
con.execute("""CREATE OR REPLACE TABLE obs AS
WITH t AS (SELECT lpad(stationid, 8, '0') AS sid, obsdate::TIMESTAMP AS ts,
                  TRY_CAST(pm25 AS DOUBLE) pm25, TRY_CAST(so2 AS DOUBLE) so2, TRY_CAST("no" AS DOUBLE) "no",
                  TRY_CAST(spm AS DOUBLE) spm, TRY_CAST(ox AS DOUBLE) ox,
                  TRY_CAST(ws AS DOUBLE) ws, TRY_CAST("temp" AS DOUBLE) tmp, TRY_CAST(hum AS DOUBLE) hum FROM raw)
SELECT 'T' || lpad((row_number() OVER (ORDER BY sid, ts))::VARCHAR, 9, '0') AS tid, *
FROM t WHERE pm25 >= 0 OR so2 >= 0 OR "no" >= 0 OR spm >= 0 OR ox >= 0 ORDER BY sid, ts""")
log(f'Step 1: observation rows after filter: {con.execute("SELECT count(*) FROM obs").fetchone()[0]:,} (expected 110,328,514)')

# ── Step 2: stages 1-3: value and label set to null ───────────────────────────────────────
con.execute("""CREATE OR REPLACE TABLE s123 AS
SELECT tid,
  CASE WHEN pm25 IN (-10000, 65535) THEN '2:sentinel' WHEN pm25 < 0 THEN '1:negative'
       WHEN sid='32201060' AND pm25=30001 THEN '3:station_fill_code'
       WHEN pm25 BETWEEN 65530 AND 65534 THEN '3:pm25_6553x' END pm25_c,
  CASE WHEN so2 IN (-9.999, 9.999) THEN '2:sentinel' WHEN so2 < 0 THEN '1:negative'
       WHEN sid='32201060' AND so2=3.0 THEN '3:station_fill_code' END so2_c,
  CASE WHEN "no" IN (-9.999, 9.999) THEN '2:sentinel' WHEN "no" < 0 THEN '1:negative'
       WHEN sid='32201060' AND "no"=3.0 THEN '3:station_fill_code' END no_c,
  CASE WHEN spm IN (-9.999, 9.999, 30.001) THEN '2:sentinel' WHEN spm < 0 THEN '1:negative' END spm_c,
  CASE WHEN ox IN (-9.999, 9.999) THEN '2:sentinel' WHEN ox < 0 THEN '1:negative'
       WHEN sid='32201060' AND ox=3.0 THEN '3:station_fill_code'
       WHEN ts = TIMESTAMP '2020-01-28 17:00:00' AND ox BETWEEN 6.9 AND 9.984 THEN '3:ox_20200128' END ox_c
FROM obs""")

# ── Step 3: stage 4 — flags only (values kept) ─────────────────────────────────────────
FLOOR = {'pm25': 200, 'no': 0.5, 'spm': 0.5, 'ox': 0.2}   # rules only look above these
CAP = {'pm25': 1000, 'no': 2.0, 'spm': 5.0, 'ox': 0.5}     # physically implausible above this
burst = """(pt = ts - INTERVAL 1 HOUR AND nt = ts + INTERVAL 1 HOUR AND pv < v/5 AND nv < v/5)
         OR (pt = ts - INTERVAL 1 HOUR AND nt2 = ts + INTERVAL 2 HOUR AND pv < v/5 AND nv >= v/5 AND nv2 < v/5 AND nv2 < nv/5)
         OR (nt = ts + INTERVAL 1 HOUR AND pt2 = ts - INTERVAL 2 HOUR AND nv < v/5 AND pv >= v/5 AND pv2 < v/5 AND pv2 < pv/5)"""
for col, fl in FLOOR.items():
    con.execute(f"""
    CREATE OR REPLACE TABLE s4_{col} AS
    WITH s AS (SELECT o.tid, o.sid, o.ts, o."{col}" v FROM obs o JOIN s123 c USING (tid)
               WHERE o."{col}" IS NOT NULL AND c.{col}_c IS NULL),
    g AS (SELECT *, lag(v) OVER w pv, lead(v) OVER w nv, lag(ts) OVER w pt, lead(ts) OVER w nt,
          lag(v, 2) OVER w pv2, lead(v, 2) OVER w nv2, lag(ts, 2) OVER w pt2, lead(ts, 2) OVER w nt2,
          CASE WHEN v = lag(v) OVER w AND ts = lag(ts) OVER w + INTERVAL 1 HOUR THEN 0 ELSE 1 END nb
          FROM s WINDOW w AS (PARTITION BY sid ORDER BY ts)),
    h AS (SELECT *, sum(nb) OVER (PARTITION BY sid ORDER BY ts) gid FROM g),
    k0 AS (SELECT *, count(*) OVER (PARTITION BY sid, gid) runlen FROM h),
    k1 AS (SELECT * FROM k0 WHERE v > {fl}),
    ns AS (SELECT v, count(DISTINCT sid) nst, count(*) ncell FROM k1 GROUP BY v),
    k AS (SELECT k1.*, nst, ncell FROM k1 JOIN ns USING (v))
    SELECT tid, CASE WHEN v > {CAP[col]} THEN 'physical_cap' WHEN runlen >= 3 THEN 'stuck_run'
                     WHEN nst >= 10 AND ncell >= 2 * nst THEN 'instrument_ceiling'
                     WHEN {burst} THEN 'short_burst' END AS rule
    FROM k WHERE v > {CAP[col]} OR runlen >= 3 OR (nst >= 10 AND ncell >= 2 * nst) OR {burst}""")
ENA = "o.sid = '21210501' AND o.ts IN (TIMESTAMP '2019-12-09 15:00', TIMESTAMP '2019-12-10 14:00', TIMESTAMP '2019-12-10 15:00')"
for col in ['pm25', 'ox']:
    con.execute(f"""INSERT INTO s4_{col} SELECT o.tid, 'reviewed_event' FROM obs o JOIN s123 c USING (tid)
                   WHERE {ENA} AND o.{col} IS NOT NULL AND c.{col}_c IS NULL AND o.tid NOT IN (SELECT tid FROM s4_{col})""")

# ── Step 3b: stage W — meteorological physical ranges (weather values only) ─────────────
con.execute("""CREATE OR REPLACE TABLE sw AS
SELECT tid,
  CASE WHEN ws  IS NOT NULL AND NOT (ws  >= 0   AND ws  <= 60) THEN 'W:out_of_range' END ws_c,
  CASE WHEN tmp IS NOT NULL AND NOT (tmp >= -40 AND tmp < 42)  THEN 'W:out_of_range' END tmp_c,
  CASE WHEN hum IS NOT NULL AND NOT (hum >  0   AND hum <= 100) THEN 'W:out_of_range' END hum_c
FROM obs""")

# ── Step 4: corrections log (nulled stages 1-3 and W + flagged stage 4) ─────────────────
parts = []
for col, src in [('pm25', 'pm25'), ('so2', 'so2'), ('no', '"no"'), ('spm', 'spm'), ('ox', 'ox')]:
    parts.append(f"""SELECT o.sid, o.tid, strftime(o.ts, '%Y-%m-%d %H:%M:%S') obsdate, '{col}' AS variable,
        o.{src} AS original_value, split_part(c.{col}_c, ':', 1) AS stage, split_part(c.{col}_c, ':', 2) AS rule,
        'nulled' AS action FROM obs o JOIN s123 c USING (tid) WHERE c.{col}_c IS NOT NULL""")
for col, src, cc in [('ws', 'ws', 'ws_c'), ('temp', 'tmp', 'tmp_c'), ('hum', 'hum', 'hum_c')]:
    parts.append(f"""SELECT o.sid, o.tid, strftime(o.ts, '%Y-%m-%d %H:%M:%S'), '{col}', o.{src}, 'W', 'out_of_range', 'nulled'
        FROM obs o JOIN sw w USING (tid) WHERE w.{cc} IS NOT NULL""")
for col in FLOOR:
    src = '"no"' if col == 'no' else col
    parts.append(f"""SELECT o.sid, o.tid, strftime(o.ts, '%Y-%m-%d %H:%M:%S'), '{col}', o.{src}, '4', f.rule, 'flagged'
        FROM obs o JOIN s4_{col} f USING (tid)""")
con.execute("CREATE OR REPLACE TABLE clog AS " + " UNION ALL ".join(parts))
con.execute(f"COPY (SELECT * FROM clog ORDER BY tid, variable) TO '{LOG_OUT}' (HEADER)")
for r in con.execute("SELECT stage, action, variable, rule, count(*) FROM clog GROUP BY ALL ORDER BY ALL").fetchall():
    log(f'        log  stage {r[0]} {r[1]:8s} {r[2]:5s} {r[3]:20s} {r[4]:,}')
n_null = con.execute("SELECT count(*) FROM clog WHERE action='nulled' AND stage <> 'W'").fetchone()[0]
n_w = con.execute("SELECT count(*) FROM clog WHERE stage = 'W'").fetchone()[0]
n_flag = con.execute("SELECT count(*) FROM clog WHERE action='flagged'").fetchone()[0]
log(f'Step 4: nulled (stages 1-3): {n_null:,} (expected 2,235,358); flagged (stage 4): {n_flag:,}; weather nulled (W): {n_w:,}')

# ── Step 5: station metadata (original columns of the station list + *_resolved) ────────────
con.execute(f"""CREATE OR REPLACE TABLE st AS
SELECT sid, stationname_en, stationtype_en, prefecture_en, city_en, street_en, pincode,
  TRY_CAST(lat AS DOUBLE) lat, TRY_CAST(lon AS DOUBLE) lon,
  stationname_resolved, stationtype_resolved, prefecture_resolved, city_resolved, street_resolved,
  TRY_CAST(lat_resolved AS DOUBLE) lat_resolved, TRY_CAST(lon_resolved AS DOUBLE) lon_resolved,
  admin_source, admin_note
FROM read_csv('{STATION_RESOLVED}', all_varchar=true, header=true)""")
n_st = con.execute("SELECT count(*) FROM st").fetchone()[0]
n_unres = con.execute("SELECT count(DISTINCT sid) FROM obs WHERE sid NOT IN (SELECT sid FROM st WHERE prefecture_resolved IS NOT NULL)").fetchone()[0]
log(f'Step 5: station rows: {n_st:,}; stations in observations without resolved prefecture: {n_unres}')
with open(SOURCES_OUT, 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['source_id', 'citation', 'url', 'version', 'licence', 'covers']); w.writerows(SOURCES)

# ── Step 6: feature table — 29 original columns, then the added columns ───────────────────
hol = sorted({str(d) for y in range(2018, 2026) for d in holidays.Japan(years=y).keys()})
con.execute("CREATE OR REPLACE TABLE hol AS SELECT unnest(?::VARCHAR[])::DATE AS d", [hol])
def psr(col, b):
    return (f"CASE WHEN {col} IS NULL THEN NULL WHEN {col} < {b[0]} THEN 'Safe' WHEN {col} < {b[1]} THEN 'Moderate' "
            f"WHEN {col} < {b[2]} THEN 'Slightly Unhealthy' WHEN {col} < {b[3]} THEN 'Unhealthy' ELSE 'Very Unhealthy' END")
BEAUFORT = [(0.3, 'Calm'), (1.6, 'Light air'), (3.4, 'Light breeze'), (5.5, 'Gentle breeze'),
            (8.0, 'Moderate breeze'), (10.8, 'Fresh breeze'), (13.9, 'Strong breeze'), (17.2, 'Near gale'),
            (20.8, 'Gale'), (24.5, 'Strong gale'), (28.5, 'Storm'), (32.7, 'Violent storm')]   # JMA Beaufort scale (m/s)
BF = 'CASE WHEN v.ws IS NULL THEN NULL ' + ' '.join(f"WHEN v.ws < {b} THEN '{n}'" for b, n in BEAUFORT) + " ELSE 'Hurricane force' END"
con.execute(f"""
CREATE OR REPLACE TABLE feat AS
WITH v AS (
  SELECT o.tid, o.sid, o.ts,
    CASE WHEN c.pm25_c IS NULL THEN o.pm25 END pm25, CASE WHEN c.so2_c IS NULL THEN o.so2 END so2,
    CASE WHEN c.no_c IS NULL THEN o."no" END "no", CASE WHEN c.spm_c IS NULL THEN o.spm END spm,
    CASE WHEN c.ox_c IS NULL THEN o.ox END ox,
    CASE WHEN w.ws_c IS NULL THEN o.ws END ws, CASE WHEN w.tmp_c IS NULL THEN o.tmp END "temp",
    CASE WHEN w.hum_c IS NULL THEN o.hum END hum
  FROM obs o JOIN s123 c USING (tid) JOIN sw w USING (tid))
SELECT v.sid, v.tid, st.stationname_en, st.stationtype_en, st.prefecture_en, st.city_en, st.street_en,
  st.pincode, st.lat, st.lon, strftime(v.ts, '%Y-%m-%d %H:%M:%S') obsdate,
  year(v.ts) "year", month(v.ts) "month", strftime(v.ts, '%B') month_name, strftime(v.ts, '%A') weekday_name,
  hour(v.ts) "hour",
  CASE WHEN year(v.ts) >= 2026 THEN 'Unknown' WHEN hol.d IS NOT NULL THEN 'Holiday'
       WHEN isodow(v.ts) >= 6 THEN 'Weekend' ELSE 'Weekday' END dayType,
  CASE WHEN hour(v.ts) BETWEEN 5 AND 8 THEN 'Early Morning' WHEN hour(v.ts) BETWEEN 9 AND 11 THEN 'Morning'
       WHEN hour(v.ts) BETWEEN 12 AND 16 THEN 'Afternoon' WHEN hour(v.ts) BETWEEN 17 AND 20 THEN 'Evening'
       ELSE 'Night' END timeCategory,
  CASE WHEN month(v.ts) IN (3,4,5) THEN 'Spring' WHEN month(v.ts) IN (6,7,8) THEN 'Summer'
       WHEN month(v.ts) IN (9,10,11) THEN 'Autumn' ELSE 'Winter' END season,
  v.pm25, v.so2, v."no", v.spm, v.ox,
  {psr('v.pm25', [15, 35, 55, 150])} pm25_level, {psr('v.so2', [0.04, 0.1, 0.2, 1.0])} so2_level,
  {psr('v."no"', [0.02, 0.06, 0.20, 1.0])} no_level, {psr('v.spm', [0.10, 0.20, 0.40, 1.0])} spm_level,
  {psr('v.ox', [0.06, 0.12, 0.24, 0.40])} ox_level,
  f1.rule pm25_flag, f2.rule no_flag, f3.rule spm_flag, f4.rule ox_flag,
  st.stationname_resolved, st.stationtype_resolved, st.prefecture_resolved, st.city_resolved,
  st.street_resolved, st.lat_resolved, st.lon_resolved,
  '{SOURCE}' AS source,
  v.ws, v."temp", v.hum, {BF} ws_level
FROM v LEFT JOIN st USING (sid) LEFT JOIN hol ON hol.d = v.ts::DATE
LEFT JOIN s4_pm25 f1 USING (tid) LEFT JOIN s4_no f2 USING (tid) LEFT JOIN s4_spm f3 USING (tid) LEFT JOIN s4_ox f4 USING (tid)
ORDER BY v.tid""")
con.execute(f"COPY feat TO '{TABLE_OUT}.csv' (HEADER)")
con.execute(f"COPY feat TO '{TABLE_OUT}.parquet' (FORMAT parquet, COMPRESSION zstd)")
n_feat = con.execute("SELECT count(*) FROM feat").fetchone()[0]
n_cols = len(con.execute("SELECT * FROM feat LIMIT 0").description)
log(f'Step 6: feature table rows: {n_feat:,}, columns: {n_cols} (29 original + 16 added; 02_flag_meteorology.py adds 3)')
for col in ['pm25', 'so2', '"no"', 'spm', 'ox', 'ws', '"temp"', 'hum']:
    r = con.execute(f"SELECT count({col}), avg({col}), median({col}), stddev_samp({col}), min({col}), max({col}) FROM feat").fetchone()
    log(f'Table  {col:6s} n={r[0]:,} mean={r[1]:.5f} median={r[2]:.5f} sd={r[3]:.5f} min={r[4]} max={r[5]}')
con.close()
for f in [f'{OUT}/_build.duckdb', f'{OUT}/_build.duckdb.wal']:
    if os.path.exists(f):
        os.remove(f)
log(f'Done in {(time.time() - t0) / 60:.1f} min')
open(REPORT, 'w').write('\n'.join(report) + '\n')
