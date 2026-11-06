"""
paper_numbers.py — numbers quoted in the manuscript, recomputed from the release files.
Output: <release_dir>/PAPER_NUMBERS.json
Usage: python validation/paper_numbers.py <release_dir>
"""
import json, sys
import duckdb

ART = sys.argv[1]
F = f"{ART}/japaq_fe_v1.0.0.parquet"
LOG = f"{ART}/japaq_corrections_log_v1.0.0.csv"
RAW = f"{ART}/japaq_raw_hourly_obs_v1.0.0.csv"
STN = f"{ART}/japaq_station_metadata_v1.0.0.csv"
c = duckdb.connect(); c.execute("SET threads=16; SET memory_limit='40GB'")
c.execute(f"CREATE VIEW f AS SELECT * FROM '{F}'")
q = lambda s: c.execute(s).fetchall()
one = lambda s: c.execute(s).fetchone()
N = one("SELECT count(*) FROM f")[0]
R = {"records": N}

# raw file
R["raw_rows"], R["raw_stations"] = one(f"SELECT count(*), count(DISTINCT stationid) FROM read_csv('{RAW}', all_varchar=true)")
R["stations_in_table"] = one("SELECT count(DISTINCT sid) FROM f")[0]

# Table 7: completeness and descriptive statistics
t7 = {}
for col in ["pm25", "so2", "no", "spm", "ox", "ws", "temp", "hum"]:
    n, mean, med, sd, mn, mx, nst = one(f'SELECT count("{col}"), avg("{col}"), median("{col}"), stddev_samp("{col}"), '
                                        f'min("{col}"), max("{col}"), count(DISTINCT sid) FILTER ("{col}" IS NOT NULL) FROM f')
    t7[col] = {"valid": n, "pct_valid": round(100 * n / N, 2), "mean": mean, "median": med, "sd": sd, "min": mn,
               "max": mx, "stations": nst}
R["table7"] = t7

# corrections
R["corrections_by_stage_variable"] = q(f"SELECT stage, variable, rule, count(*) FROM read_csv('{LOG}', all_varchar=true) GROUP BY ALL ORDER BY ALL")
R["corrections_by_stage"] = dict(q(f"SELECT stage, count(*) FROM read_csv('{LOG}', all_varchar=true) GROUP BY 1 ORDER BY 1"))
pol = one(f"SELECT count(*) FROM read_csv('{LOG}', all_varchar=true) WHERE variable IN ('pm25','so2','no','spm','ox')")[0]
R["pollutant_cells_corrected"] = pol
R["pollutant_cells_corrected_pct_of_all_cells"] = round(100 * pol / (5 * N), 3)
raw_nonnull = one(f"""SELECT count(pm25)+count(so2)+count("no")+count(spm)+count(ox) FROM '{F}'""")[0] + pol
R["pollutant_cells_corrected_pct_of_measurements"] = round(100 * pol / raw_nonnull, 3)

# station metadata completeness (stations with observations)
c.execute(f"CREATE TABLE st AS SELECT * FROM read_csv('{STN}', all_varchar=true) WHERE sid IN (SELECT DISTINCT sid FROM f)")
R["station_metadata"] = {
    "by_metadata_source": q("SELECT CASE WHEN metadata_source LIKE 'nies%' THEN 'nies' ELSE metadata_source END, count(*), count(lat), "
                         "count(prefecture_en), count(city_en), count(stationtype_en) FROM st GROUP BY 1 ORDER BY 1"),
    "with_coordinates": one("SELECT count(lat) FROM st")[0],
    "with_prefecture_city": one("SELECT count(*) FILTER (prefecture_en IS NOT NULL AND city_en IS NOT NULL) FROM st")[0],
    "station_types": q("SELECT stationtype_en, count(*) FROM st GROUP BY 1 ORDER BY 2 DESC"),
    "records_without_coordinates": one("SELECT count(*) FROM f WHERE lat IS NULL")[0],
}

# calendar distribution
R["dayType"] = q("SELECT dayType, count(*) FROM f GROUP BY 1 ORDER BY 2 DESC")
R["season_counts"] = q("SELECT season, count(*) FROM f GROUP BY 1 ORDER BY 1")
R["period"] = [str(x) for x in one("SELECT min(obsdate), max(obsdate) FROM f")]

# Table 8: yearly and seasonal means (x1e-3 for gases/SPM, as in the paper)
yr = q("""SELECT "year", avg(pm25), 1000*avg(so2), 1000*avg("no"), 1000*avg(spm), 1000*avg(ox) FROM f GROUP BY 1 ORDER BY 1""")
se = q("""SELECT season, avg(pm25), 1000*avg(so2), 1000*avg("no"), 1000*avg(spm), 1000*avg(ox) FROM f GROUP BY 1
          ORDER BY CASE season WHEN 'Spring' THEN 1 WHEN 'Summer' THEN 2 WHEN 'Autumn' THEN 3 ELSE 4 END""")
R["table8_year"] = yr
R["table8_season"] = se

# severity label distributions
R["labels"] = {col: q(f"SELECT {col}, count(*), round(100.0*count(*)/sum(count(*)) OVER (), 3) FROM f WHERE {col} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
               for col in ["pm25_level", "so2_level", "no_level", "spm_level", "ox_level", "ws_level"]}
R["pm25_unhealthy_or_worse"] = one("SELECT count(*) FILTER (pm25_level IN ('Unhealthy','Very Unhealthy')), "
                                   "round(100.0*count(*) FILTER (pm25_level IN ('Unhealthy','Very Unhealthy'))/count(pm25_level), 3) FROM f")
R["pm25_by_timeCategory"] = q("SELECT timeCategory, avg(pm25) FROM f GROUP BY 1 ORDER BY 2 DESC")
R["compound_pm25_ox_unhealthy"] = q("""SELECT sid, obsdate, pm25, ox FROM f
    WHERE pm25_level IN ('Unhealthy','Very Unhealthy') AND ox_level IN ('Unhealthy','Very Unhealthy')""")

# MOE fiscal-year comparison (FY2022, FY2023), three averaging methods
c.execute("""CREATE TABLE d AS SELECT sid, stationtype_en t, obsdate::TIMESTAMP::DATE dt,
    CASE WHEN month(obsdate::TIMESTAMP) >= 4 THEN year(obsdate::TIMESTAMP) ELSE year(obsdate::TIMESTAMP) - 1 END fy,
    sum(pm25) s, count(pm25) n FROM f WHERE pm25 IS NOT NULL GROUP BY ALL""")
fy = {}
for t in ["General", "Roadside"]:
    for y in [2022, 2023]:
        a = one(f"SELECT count(*), avg(m) FROM (SELECT sid, sum(s)/sum(n) m FROM d WHERE t='{t}' AND fy={y} GROUP BY sid)")
        b = one(f"""SELECT count(*), avg(m) FROM (SELECT sid, avg(s/n) m, count(*) nd FROM d
                   WHERE t='{t}' AND fy={y} AND n >= 20 GROUP BY sid HAVING count(*) >= 250)""")
        cal = one(f"SELECT avg(pm25) FROM f WHERE stationtype_en='{t}' AND \"year\"={y}")
        fy[f"{t}_FY{y}"] = {"station_hourly_mean": [a[0], a[1]], "moe_rule_250d_20h": [b[0], b[1]], "calendar_pooled": cal}
R["moe_fy"] = fy

# Stage 4 flags and ranges excluding flagged values
R["stage4_flags"] = {v: one(f"SELECT count({v}_flag), count(DISTINCT sid) FILTER (WHERE {v}_flag IS NOT NULL) FROM f")
                     for v in ["pm25", "no", "spm", "ox", "ws", "temp", "hum"]}
R["stage4_flag_rules"] = q("SELECT variable, rule, count(*) FROM read_csv('" + LOG + "', all_varchar=true) WHERE stage = '4' GROUP BY ALL ORDER BY ALL")
R["log_rows"] = one("SELECT count(*) FROM read_csv('" + LOG + "', all_varchar=true)")[0]
R["excluding_flagged"] = {v: one(f"SELECT min({v}) FILTER (WHERE {v}_flag IS NULL), max({v}) FILTER (WHERE {v}_flag IS NULL) FROM f")
                          for v in ["pm25", "no", "spm", "ox", "ws", "temp", "hum"]}

json.dump(R, open(f"{ART}/PAPER_NUMBERS.json", "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str)[:12000])
