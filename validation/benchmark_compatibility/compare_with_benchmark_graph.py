"""
compare_with_benchmark_graph.py — check that the 29 original columns of the feature table equal
the graph on which the AirCypher benchmark was defined (built before the additions of this release).

Compares all 1,806 Station/Location nodes in full, and observations for a random sample of 2,000
records plus every record flagged by Stage 4 and every duplicated station-hour. Expect zero
differences. Requires access to that graph (NEO4J_URI/USER/PASS); the released graph and its
benchmark results can instead be checked with bench_impact.py.
Usage: python compare_with_benchmark_graph.py <release_dir>
"""
import json, math, os, sys
import duckdb
from neo4j import GraphDatabase

ART = sys.argv[1]
FEAT = f"{ART}/japaq_fe_v1.0.0.parquet"
c = duckdb.connect(); c.execute("SET threads=32")
drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"]))

def same(a, b):
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None
    if b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return str(a) == str(b)

res = {}
# stations / locations, every property of v1.0.0
st = c.execute(f"""SELECT DISTINCT sid, stationname_en, stationtype_en, prefecture_en, city_en, street_en, pincode, lat, lon
                   FROM '{FEAT}'""").df()
st = st.astype(object).where(st.notna(), None).to_dict("records")
with drv.session() as s:
    g = {r["sid"]: r for r in s.run("""MATCH (n:Station)-[:LOCATED_AT]->(l:Location)
        RETURN n.sid AS sid, n.stationname_en AS stationname_en, n.stationtype_en AS stationtype_en,
               l.prefecture_en AS prefecture_en, l.city_en AS city_en, l.street_en AS street_en,
               l.pincode AS pincode, l.lat AS lat, l.lon AS lon""").data()}
bad = [r["sid"] for r in st if r["sid"] not in g or not all(same(r[k], g[r["sid"]][k]) for k in r)]
res["stations_compared"] = len(st); res["station_mismatch"] = bad[:20]; res["n_station_mismatch"] = len(bad)

c.execute(f"""CREATE TABLE smp AS
  SELECT * FROM '{FEAT}' USING SAMPLE reservoir(2000 ROWS) REPEATABLE (20261104)
  UNION SELECT * FROM '{FEAT}' WHERE coalesce(pm25_flag, no_flag, spm_flag, ox_flag) IS NOT NULL
  UNION SELECT * FROM '{FEAT}' WHERE (sid, obsdate) IN (SELECT sid, obsdate FROM '{FEAT}' GROUP BY ALL HAVING count(*) > 1)""")
smp = c.execute("SELECT * FROM smp").df()
VAL = ["pm25", "so2", "no", "spm", "ox", "pm25_level", "so2_level", "no_level", "spm_level", "ox_level"]
TIM = ["obsdate", "year", "month", "month_name", "weekday_name", "hour", "dayType", "timeCategory", "season"]
Q = """UNWIND $t AS tid MATCH (p:ObservedPollutant {tid: tid})-[:OBSERVED_AT]->(o:ObservationTime)
       MATCH (p)-[:RECORDED_BY]->(s:Station) RETURN tid, s.sid AS sid, properties(p) AS p, properties(o) AS o"""
got = {}
with drv.session() as s:
    tids = smp.tid.tolist()
    for i in range(0, len(tids), 2000):
        for r in s.run(Q, t=tids[i:i + 2000]):
            got[r["tid"]] = r
drv.close()
n = {"records": len(smp), "found": 0, "sid_bad": 0, "value_bad": 0, "time_bad": 0, "values": 0, "times": 0}
ex = []
for r in smp.astype(object).where(smp.notna(), None).to_dict("records"):
    q = got.get(r["tid"])
    if not q:
        continue
    n["found"] += 1
    n["sid_bad"] += int(q["sid"] != r["sid"])
    for k in VAL:
        n["values"] += 1
        if not same(r[k], q["p"].get(k)):
            n["value_bad"] += 1
            if len(ex) < 10: ex.append([r["tid"], k, r[k], q["p"].get(k)])
    for k in TIM:
        n["times"] += 1
        if not same(r[k], q["o"].get(k)):
            n["time_bad"] += 1
            if len(ex) < 10: ex.append([r["tid"], k, r[k], q["o"].get(k)])
res["observations"] = n; res["examples"] = ex
res["flagged_records_in_sample"] = int(smp[["pm25_flag", "no_flag", "spm_flag", "ox_flag"]].notna().any(axis=1).sum())
json.dump(res, open(f"{ART}/VERIFY_original_columns_vs_benchmark_graph.json", "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
