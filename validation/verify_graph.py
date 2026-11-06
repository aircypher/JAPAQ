"""
verify_graph.py — read-only check of the graph against the released files (feature table,
corrections log) and the station metadata (station_resolved.csv).

Checks: every Station and Location node vs the station file; node/relationship counts;
a random sample of 2,000 observations, all rows with a Stage 4 pollutant flag, 2,000 rows with a
Stage 4 meteorological flag, and 2,000 rows changed by the meteorological range check (Stage W),
vs the feature table (all values, labels, flags, weather, time features, station link).
Usage (with NEO4J_URI, NEO4J_USER, NEO4J_PASS): python validation/verify_graph.py <out_dir> <station_resolved.csv>
"""
import json, math, os, sys
import duckdb
from neo4j import GraphDatabase

ART, STN = sys.argv[1], sys.argv[2]
FEAT = f'{ART}/japaq_fe_v1.0.0.parquet'
LOG = f'{ART}/japaq_corrections_log_v1.0.0.csv'
drv = GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASS']))
c = duckdb.connect()
c.execute("SET memory_limit='30GB'; SET threads=16")
st = c.execute(f"SELECT * FROM read_csv('{STN}', all_varchar=true) WHERE sid IN (SELECT DISTINCT sid FROM '{FEAT}')").df()
st = st.astype(object).where(st.notna(), None)
rows = st.to_dict('records')
res = {}

with drv.session() as s:
    pass  # read-only: no updates
    g = {r['sid']: r for r in s.run("""MATCH (n:Station)-[:LOCATED_AT]->(l:Location)
        RETURN n.sid AS sid, n.stationname_en AS stationname_en, n.stationtype_en AS stationtype_en, n.source AS source,
               n.stationname_resolved AS stationname_resolved, n.stationtype_resolved AS stationtype_resolved,
               l.prefecture_en AS prefecture_en, l.city_en AS city_en, l.street_en AS street_en, l.pincode AS pincode,
               l.prefecture_resolved AS prefecture_resolved, l.city_resolved AS city_resolved, l.street_resolved AS street_resolved,
               l.lat_resolved AS lat_resolved, l.lon_resolved AS lon_resolved,
               l.metadata_source AS admin_source, l.lat AS lat, l.lon AS lon""").data()}
    def eq(a, b, num=False):
        if a is None or a == '':
            return b is None
        return b is not None and (abs(float(a) - float(b)) < 1e-9 if num else str(a) == str(b))
    bad = [r['sid'] for r in rows if r['sid'] not in g or not all(
        eq(r[k], g[r['sid']][k], k.startswith(('lat', 'lon'))) for k in
        ['stationname_en', 'stationtype_en', 'source', 'prefecture_en', 'city_en', 'street_en', 'pincode', 'admin_source', 'lat', 'lon'])]
    res['stations_in_file'] = len(rows)
    res['stations_in_graph'] = len(g)
    res['station_location_mismatch'] = bad[:20]
    res['node_counts'] = {r['l']: r['n'] for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n").data()}
    res['rel_counts'] = {r['t']: r['n'] for r in s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n").data()}

    c.execute(f"""CREATE TABLE smp AS
      SELECT * FROM '{FEAT}' USING SAMPLE reservoir(2000 ROWS) REPEATABLE (20261104)
      UNION SELECT * FROM '{FEAT}' WHERE tid IN (SELECT tid FROM read_csv('{LOG}', all_varchar=true) WHERE stage = '4'
                                                 AND variable IN ('pm25', 'no', 'spm', 'ox'))
      UNION SELECT * FROM '{FEAT}' WHERE tid IN (SELECT tid FROM (SELECT DISTINCT tid FROM read_csv('{LOG}', all_varchar=true)
                                                 WHERE stage = '4' AND variable IN ('ws', 'temp', 'hum'))
                                                 USING SAMPLE reservoir(2000 ROWS) REPEATABLE (20261104))
      UNION SELECT * FROM '{FEAT}' WHERE tid IN (SELECT tid FROM (SELECT DISTINCT tid FROM read_csv('{LOG}', all_varchar=true)
                                                 WHERE stage = 'W') USING SAMPLE reservoir(2000 ROWS) REPEATABLE (20261104))""")
    smp = c.execute("SELECT * FROM smp").df()
    COLS = ['pm25', 'so2', 'no', 'spm', 'ox', 'ws', 'temp', 'hum']
    LAB = ['pm25_level', 'so2_level', 'no_level', 'spm_level', 'ox_level', 'ws_level', 'pm25_flag', 'no_flag', 'spm_flag', 'ox_flag', 'ws_flag', 'temp_flag', 'hum_flag']
    TIME = ['obsdate', 'dayType', 'timeCategory', 'season', 'weekday_name', 'month_name']
    Q = """UNWIND $tids AS t
           MATCH (p:ObservedPollutant {tid: t})-[:OBSERVED_AT]->(o:ObservationTime)-[:AT_LOCATION]->(l:Location)
           MATCH (p)-[:RECORDED_BY]->(s:Station)
           RETURN t AS tid, s.sid AS sid, l.sid AS lsid, properties(p) AS p, properties(o) AS o"""
    got = {}
    tids = smp.tid.tolist()
    for i in range(0, len(tids), 2000):
        for r in s.run(Q, tids=tids[i:i + 2000]):
            got[r['tid']] = r
drv.close()

cnt = {'rows': len(smp), 'found': 0, 'station_link_bad': 0, 'value_ok': 0, 'value_bad': 0, 'label_ok': 0,
       'label_bad': 0, 'time_ok': 0, 'time_bad': 0}
ex = []
for r in smp.to_dict('records'):
    g1 = got.get(r['tid'])
    if g1 is None:
        continue
    cnt['found'] += 1
    if g1['sid'] != r['sid'] or g1['lsid'] != r['sid']:
        cnt['station_link_bad'] += 1
    for k in COLS:
        a, b = r[k], g1['p'].get(k)
        ok = (b is None) if (a is None or (isinstance(a, float) and math.isnan(a))) else (b is not None and abs(a - b) < 1e-9)
        cnt['value_ok' if ok else 'value_bad'] += 1
        if not ok and len(ex) < 10: ex.append([r['tid'], k, a, b])
    for k in LAB:
        ok = (r[k] or None) == g1['p'].get(k)
        cnt['label_ok' if ok else 'label_bad'] += 1
        if not ok and len(ex) < 10: ex.append([r['tid'], k, r[k], g1['p'].get(k)])
    for k in TIME:
        ok = str(r[k]) == str(g1['o'].get(k))
        cnt['time_ok' if ok else 'time_bad'] += 1
res['observation_check'] = cnt
res['examples'] = ex
json.dump(res, open(f'{ART}/VERIFY_graph_vs_files.json', 'w'), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
