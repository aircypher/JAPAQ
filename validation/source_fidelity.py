"""
source_fidelity.py — check the pollutant values stored in the graph against the raw hourly file.

A: 10,000 uniformly random observation records: values not set to null by Stages 1-3 must equal the
   raw value, values set to null must be null with a null label, and values missing in the raw file
   must be null.
B: 1,000 random nulled values per pollutant from the corrections log: must be null in the graph, and
   the logged original value must equal the raw value.
Values flagged by Stage 4 are kept and therefore count as unchanged.

Usage (with NEO4J_URI, NEO4J_USER, NEO4J_PASS):
  python validation/source_fidelity.py <japaq_raw_hourly_obs_v1.0.0.csv> <japaq_corrections_log_v1.0.0.csv> <result_dir>
"""
import os, random, json, sys, duckdb, pandas as pd
from neo4j import GraphDatabase
RAW, LOGF, OUT = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)
POLS = ["pm25", "so2", "no", "spm", "ox"]
drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"]))
Q = """UNWIND $tids AS t MATCH (p:ObservedPollutant {tid:t})-[:OBSERVED_AT]->(o:ObservationTime), (p)-[:RECORDED_BY]->(s:Station)
RETURN t AS tid, s.sid AS sid, toString(o.obsdate) AS obsdate, o.year AS year, """ + \
    ", ".join(f"p.{c} AS g_{c}, p.{c}_level AS g_{c}_level" for c in POLS)
def fetch(tids):
    rows = []
    with drv.session() as s:
        for i in range(0, len(tids), 1000):
            rows += [r.data() for r in s.run(Q, tids=tids[i:i+1000])]
    df = pd.DataFrame(rows); df["obsdate"] = df.obsdate.str.replace("T", " ").str[:19]; return df
random.seed(20261104)
A = fetch([f"T{n:09d}" for n in random.sample(range(1, 110328515), 10000)])
con = duckdb.connect()
con.execute(f"""CREATE TABLE log AS SELECT lpad(CAST(sid AS VARCHAR),8,'0') sid, tid, CAST(obsdate AS VARCHAR) obsdate,
  variable pol, original_value ov FROM read_csv_auto('{LOGF}', all_varchar=true)
  WHERE action = 'nulled' AND variable IN ('pm25', 'so2', 'no', 'spm', 'ox')""")
B_keys = con.execute("SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY pol ORDER BY hash(tid||pol||'20261104')) rn FROM log) WHERE rn<=1000").df()
B = fetch(sorted(set(B_keys.tid)))
keys = pd.concat([A[["sid","obsdate"]], B[["sid","obsdate"]]]).drop_duplicates()
con.register("keys", keys)
cols = ", ".join(f"TRY_CAST(r.{c} AS DOUBLE) r_{c}" for c in POLS)
raw = con.execute(f"""SELECT k.sid, k.obsdate, {cols}, count(*) OVER (PARTITION BY k.sid, k.obsdate) dup
 FROM read_csv_auto('{RAW}', all_varchar=true) r
 JOIN keys k ON lpad(r.stationid,8,'0') = k.sid AND r.obsdate = k.obsdate""").df()
logset = set(map(tuple, con.execute("SELECT tid, pol FROM log").df().values.tolist()))
def compare(df, name):
    m = df.merge(raw, on=["sid","obsdate"], how="left", indicator=True)
    res = {"records": len(df), "records_without_raw_match": int((m._merge=="left_only").sum()), "raw_duplicates": int((m.dup>1).sum()), "by_pollutant": {}}
    bad = []
    for c in POLS:
        g, r = m[f"g_{c}"], m[f"r_{c}"]; logged = pd.Series([(t, c) in logset for t in m.tid])
        unchanged = ~logged & r.notna()
        ok_unch = unchanged & g.notna() & ((g - r).abs() < 1e-9)
        ok_corr = logged & g.isna() & m[f"g_{c}_level"].isna()
        raw_null_ok = ~logged & r.isna() & g.isna()
        res["by_pollutant"][c] = {"unchanged_cells": int(unchanged.sum()), "unchanged_match": int(ok_unch.sum()),
            "corrected_cells": int(logged.sum()), "corrected_null_in_graph": int(ok_corr.sum()),
            "raw_missing_cells": int((~logged & r.isna()).sum()), "raw_missing_null_in_graph": int(raw_null_ok.sum())}
        bad.append(m[(unchanged & ~ok_unch) | (logged & ~ok_corr) | (~logged & r.isna() & ~raw_null_ok)].assign(pollutant=c))
    pd.concat(bad).to_csv(f"{OUT}/{name}_mismatches.csv", index=False)
    return res, m
resA, mA = compare(A, "sampleA_random")
resA["years"] = A.year.value_counts().sort_index().to_dict(); resA["stations"] = int(A.sid.nunique())
resB, mB = compare(B, "sampleB_corrected")
# For corrected cells: logged original value must equal raw value
chk = B_keys.merge(mB[["tid"] + [f"r_{c}" for c in POLS]], on="tid", how="left")
chk["raw"] = [row[f"r_{row.pol}"] for _, row in chk.iterrows()]
chk["match"] = (chk.raw - chk.ov.astype(float)).abs() < 1e-9
resB["log_original_value_equals_raw"] = {p: [int(g.match.sum()), len(g)] for p, g in chk.groupby("pol")}
chk[~chk.match].to_csv(f"{OUT}/sampleB_log_vs_raw_mismatches.csv", index=False)
json.dump({"sampleA_random": resA, "sampleB_corrected": resB}, open(f"{OUT}/results.json", "w"), indent=2, default=str)
print(json.dumps({"sampleA_random": resA, "sampleB_corrected": resB}, indent=2, default=str))
