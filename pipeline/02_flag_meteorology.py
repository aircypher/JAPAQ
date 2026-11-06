"""
02_flag_meteorology.py — Stage 4 quality flags for the meteorological variables.

Run after 01_build_tables.py. Adds three columns to the feature table — ws_flag, temp_flag, hum_flag —
and appends the flagged values to the corrections log (stage 4, action 'flagged'). Values are KEPT,
as for the pollutant flags; no existing column or value changes.

Rules (a value is flagged when any applies; the flag names the first that applies):
  stuck_run        the same value in 24 or more consecutive hours at one station
                   (wind speed: only values above 0, since calm periods are genuine;
                    humidity: values below 100 %; a run at exactly 100 % must last 72 hours or
                    more, since saturation in rain or fog can persist for a day or two)
  neighbour_check  temperature: more than 15 degC from the median of at least 3 other stations
                   within 50 km in the same hour;
                   wind speed: more than 25 m/s above that median.
                   Stations without coordinates use the stations of the same prefecture.
Humidity has no neighbour check, because it varies strongly between nearby sites.

Usage: python pipeline/02_flag_meteorology.py <out_dir>
"""
import os
import sys
import time
import duckdb

ART = sys.argv[1]
FEAT = f'{ART}/japaq_fe_v1.0.0'
LOG = f'{ART}/japaq_corrections_log_v1.0.0.csv'
REPORT = f'{ART}/BUILD_REPORT_meteorology_flags.txt'
RUN, RUN_SAT, RADIUS_KM, TEMP_DEV, WS_EXCESS, MIN_NB = 24, 72, 50, 15, 25, 3
t0 = time.time()
report = []
def log(s):
    print(s, flush=True); report.append(s)

con = duckdb.connect(f'{ART}/.flagmet.duckdb')
con.execute("SET memory_limit='40GB'; SET threads=16; SET preserve_insertion_order=true")
cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{FEAT}.parquet'").fetchall()]
assert 'temp_flag' not in cols, 'flags already present'
assert len(cols) == 45, len(cols)
con.execute(f"""CREATE OR REPLACE TABLE m AS SELECT tid, sid, obsdate, obsdate::TIMESTAMP ts, ws, "temp", hum,
  prefecture_resolved p, lat_resolved la, lon_resolved lo FROM '{FEAT}.parquet'
  WHERE ws IS NOT NULL OR "temp" IS NOT NULL OR hum IS NOT NULL""")

# stuck runs: same value in consecutive hours
def stuck(col, cond, run=RUN):
    return f"""
    WITH s AS (SELECT tid, sid, ts, {col} v FROM m WHERE {col} IS NOT NULL AND {cond}),
    g AS (SELECT *, CASE WHEN v = lag(v) OVER w AND ts = lag(ts) OVER w + INTERVAL 1 HOUR THEN 0 ELSE 1 END nb
          FROM s WINDOW w AS (PARTITION BY sid ORDER BY ts)),
    h AS (SELECT *, sum(nb) OVER (PARTITION BY sid ORDER BY ts) gid FROM g),
    k AS (SELECT *, count(*) OVER (PARTITION BY sid, gid) runlen FROM h)
    SELECT tid, 'stuck_run' AS rule FROM k WHERE runlen >= {run}"""
con.execute("CREATE TABLE st_temp AS " + stuck('"temp"', 'TRUE'))
con.execute("CREATE TABLE st_ws AS " + stuck('ws', 'ws > 0'))
con.execute("CREATE TABLE st_hum AS SELECT * FROM (" + stuck('hum', 'hum < 100') + ") UNION ALL SELECT * FROM ("
            + stuck('hum', 'hum = 100', RUN_SAT) + ")")

# neighbour check: stations within RADIUS_KM (same prefecture when coordinates are missing)
con.execute("""CREATE TABLE sta AS SELECT sid, any_value(la) la, any_value(lo) lo, any_value(p) p,
  count("temp") > 0 ht, count(ws) > 0 hw FROM m GROUP BY sid""")
con.execute(f"""CREATE TABLE nbr AS SELECT a.sid s, b.sid n, a.ht AND b.ht bt, a.hw AND b.hw bw
  FROM sta a JOIN sta b ON a.sid <> b.sid AND (
   (a.la IS NOT NULL AND b.la IS NOT NULL AND 2 * 6371 * asin(sqrt(pow(sin(radians(b.la - a.la) / 2), 2)
      + cos(radians(a.la)) * cos(radians(b.la)) * pow(sin(radians(b.lo - a.lo) / 2), 2))) <= {RADIUS_KM})
   OR ((a.la IS NULL OR b.la IS NULL) AND a.p = b.p))""")
con.execute(f"""CREATE TABLE nb_temp AS SELECT x.tid, 'neighbour_check' AS rule FROM m x
  JOIN nbr ON nbr.s = x.sid AND nbr.bt JOIN m y ON y.sid = nbr.n AND y.ts = x.ts
  WHERE x."temp" IS NOT NULL AND y."temp" IS NOT NULL GROUP BY x.tid, x."temp"
  HAVING count(y."temp") >= {MIN_NB} AND abs(x."temp" - median(y."temp")) > {TEMP_DEV}""")
con.execute(f"""CREATE TABLE nb_ws AS SELECT x.tid, 'neighbour_check' AS rule FROM m x
  JOIN nbr ON nbr.s = x.sid AND nbr.bw JOIN m y ON y.sid = nbr.n AND y.ts = x.ts
  WHERE x.ws > {WS_EXCESS} AND y.ws IS NOT NULL GROUP BY x.tid, x.ws
  HAVING count(y.ws) >= {MIN_NB} AND x.ws - median(y.ws) > {WS_EXCESS}""")
for v, parts in [('temp', ['st_temp', 'nb_temp']), ('ws', ['st_ws', 'nb_ws']), ('hum', ['st_hum'])]:
    q = ' UNION ALL '.join(f"SELECT tid, rule, {i} pr FROM {t}" for i, t in enumerate(parts))
    con.execute(f"CREATE TABLE f_{v} AS SELECT tid, arg_min(rule, pr) AS rule FROM ({q}) GROUP BY tid")
    for r in con.execute(f"SELECT rule, count(*), count(DISTINCT m.sid) FROM f_{v} JOIN m USING (tid) GROUP BY rule ORDER BY rule").fetchall():
        log(f'{v:5s} {r[0]:16s} values {r[1]:,}  stations {r[2]:,}')
    log(f'{v:5s} total flagged {con.execute(f"SELECT count(*) FROM f_{v}").fetchone()[0]:,}')

# feature table: existing 45 columns unchanged + ws_flag, temp_flag, hum_flag
sel = ', '.join(f'f."{c}"' for c in cols)
con.execute(f"""CREATE TABLE feat AS SELECT {sel}, a.rule AS ws_flag, b.rule AS temp_flag, c.rule AS hum_flag
  FROM '{FEAT}.parquet' f LEFT JOIN f_ws a USING (tid) LEFT JOIN f_temp b USING (tid) LEFT JOIN f_hum c USING (tid)
  ORDER BY f.tid""")
n = con.execute("SELECT count(*) FROM feat").fetchone()[0]
assert n == 110328514, n
con.execute(f"COPY feat TO '{FEAT}.parquet.new' (FORMAT parquet, COMPRESSION zstd)")
con.execute(f"COPY feat TO '{FEAT}.csv.new' (HEADER)")

# corrections log: existing rows + flagged meteorological values
new = ' UNION ALL '.join(f"""SELECT m.sid, m.tid, m.obsdate, '{v}' AS variable, m."{v}"::VARCHAR AS original_value, '4' AS stage, f.rule, 'flagged' AS action
   FROM m JOIN f_{v} f USING (tid)""" for v in ['ws', 'temp', 'hum'])
con.execute(f"""CREATE TABLE clog AS SELECT sid, tid, obsdate, variable, original_value, stage, rule, action
   FROM read_csv('{LOG}', header=true, all_varchar=true) UNION ALL {new}""")
con.execute(f"COPY (SELECT * FROM clog ORDER BY tid, variable) TO '{LOG}.new' (HEADER)")
for r in con.execute("SELECT stage, action, count(*) FROM clog GROUP BY ALL ORDER BY ALL").fetchall():
    log(f'log stage {r[0]} {r[1]:8s} {r[2]:,}')
log(f'log total rows {con.execute("SELECT count(*) FROM clog").fetchone()[0]:,}')
for c in ['ws', '"temp"', 'hum']:
    fl = c.strip('"') + '_flag'
    r = con.execute(f"SELECT min({c}) FILTER (WHERE {fl} IS NULL), max({c}) FILTER (WHERE {fl} IS NULL) FROM feat").fetchone()
    log(f'{c:6s} range excluding flagged: {r[0]} .. {r[1]}')
for p in [f'{FEAT}.parquet', f'{FEAT}.csv', LOG]:
    os.replace(f'{p}.new', p)
con.close(); os.remove(f'{ART}/.flagmet.duckdb')
log(f'Done in {(time.time() - t0) / 60:.1f} min')
open(REPORT, 'w').write('\n'.join(report) + '\n')
