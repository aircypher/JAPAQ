"""
quickstart.py — first steps with the JAPAQ feature table (no database needed).

Usage: python examples/quickstart.py <path/to/japaq_fe_v1.0.0.parquet>
Needs: pip install duckdb pandas
"""
import sys
import duckdb

F = sys.argv[1]
con = duckdb.connect()

# 1. How big is the table?
print(con.sql(f"SELECT count(*) AS records, count(DISTINCT sid) AS stations FROM '{F}'"))

# 2. Monthly mean PM2.5 in Tokyo, 2023. Use the *_resolved station columns (complete for all
#    stations) and exclude values flagged by quality control (pm25_flag not empty).
print(con.sql(f"""
    SELECT month, round(avg(pm25), 2) AS pm25_mean, count(pm25) AS hours
    FROM '{F}'
    WHERE prefecture_resolved = 'Tokyo' AND year = 2023 AND pm25_flag IS NULL
    GROUP BY month ORDER BY month"""))

# 3. Share of hours per PM2.5 severity label, nationwide, 2023.
print(con.sql(f"""
    SELECT pm25_level, count(*) AS hours, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS percent
    FROM '{F}'
    WHERE year = 2023 AND pm25_level IS NOT NULL AND pm25_flag IS NULL
    GROUP BY pm25_level ORDER BY hours DESC"""))

# 4. One station-day as a pandas DataFrame: pollutants with temperature and wind.
df = con.sql(f"""
    SELECT obsdate, pm25, ox, temp, ws, ws_level
    FROM '{F}'
    WHERE sid = '13101010' AND obsdate LIKE '2023-07-01%'
    ORDER BY obsdate""").df()
print(df.head(12))
