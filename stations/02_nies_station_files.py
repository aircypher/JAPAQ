"""
02_nies_station_files.py — read the NIES station data files and list the stations to recover.

1. Extracts each TM<FY>0000.zip and converts the station file from Shift_JIS (CP932) to UTF-8.
2. Keeps, for every NIES station code, the record of the latest fiscal year (nies_station_latest.csv).
3. Lists the stations that have at least one valid pollutant value in the hourly observations but
   are not in the January 2026 station list (missing_stations.csv), and their NIES record if any
   (recovered_nies.csv).

Usage: python stations/02_nies_station_files.py <external_dir> <station_snapshot.csv> <japaq_hourly_obs.csv> <work_dir>
"""
import glob
import io
import os
import sys
import zipfile
import duckdb

EXT, SNAP, HOURLY, WORK = sys.argv[1:5]
os.makedirs(f'{WORK}/nies_utf8', exist_ok=True)
for z in sorted(glob.glob(f'{EXT}/nies/TM*0000.zip')):
    with zipfile.ZipFile(z) as f:
        name = [n for n in f.namelist() if n.lower().endswith('.txt')][0]
        text = f.read(name).decode('cp932')
    with open(f'{WORK}/nies_utf8/{os.path.basename(name)[:-4]}.utf8.csv', 'w', encoding='utf-8', newline='') as g:
        g.write(text)

c = duckdb.connect()
files = sorted(glob.glob(f'{WORK}/nies_utf8/*.utf8.csv'))
print('NIES files:', len(files))
c.execute(f"""CREATE TABLE n AS SELECT * FROM read_csv({files}, all_varchar=true, header=true, union_by_name=true, filename=true)""")
c.execute("""CREATE TABLE nl AS
SELECT "国環研局番" sid, "年度" fy, "測定局名" name_ja, "測定局名_ローマ字" name_romaji,
  TRY_CAST("緯度_度" AS DOUBLE) + TRY_CAST("緯度_分" AS DOUBLE)/60 + TRY_CAST("緯度_秒" AS DOUBLE)/3600 lat,
  TRY_CAST("経度_度" AS DOUBLE) + TRY_CAST("経度_分" AS DOUBLE)/60 + TRY_CAST("経度_秒" AS DOUBLE)/3600 lon,
  "都道府県名_ローマ字" pref_romaji, "市区町村コード" city_code, "市区町村名_ローマ字" city_romaji,
  "住所_ローマ字" address_romaji, "住所" address_ja, "測定局区分" station_class, "継続状況" status,
  "廃止_年" closed_year
FROM n QUALIFY row_number() OVER (PARTITION BY "国環研局番" ORDER BY "年度" DESC) = 1""")
c.execute(f"COPY (SELECT * FROM nl ORDER BY sid) TO '{WORK}/nies_station_latest.csv' (HEADER)")
print('NIES stations:', c.execute("SELECT count(*) FROM nl").fetchone()[0])

# stations with observations that are not in the January 2026 station list
c.execute(f"""CREATE TABLE miss AS SELECT DISTINCT lpad(stationid, 8, '0') sid
  FROM read_csv('{HOURLY}', all_varchar=true, header=true)
  WHERE TRY_CAST(pm25 AS DOUBLE) >= 0 OR TRY_CAST(so2 AS DOUBLE) >= 0 OR TRY_CAST("no" AS DOUBLE) >= 0
     OR TRY_CAST(spm AS DOUBLE) >= 0 OR TRY_CAST(ox AS DOUBLE) >= 0
  EXCEPT SELECT sid FROM read_csv('{SNAP}', all_varchar=true, header=true)""")
c.execute(f"COPY (SELECT sid FROM miss ORDER BY sid) TO '{WORK}/missing_stations.csv' (HEADER)")
print('stations to recover:', c.execute("SELECT count(*) FROM miss").fetchone()[0],
      '; found in NIES files:', c.execute("SELECT count(*) FROM miss JOIN nl USING (sid)").fetchone()[0])
r = c.execute(f"""SELECT count(*), median(d) FROM (
  SELECT 111320*sqrt(pow(nl.lat-TRY_CAST(e.lat AS DOUBLE),2) + pow((nl.lon-TRY_CAST(e.lon AS DOUBLE))*cos(radians(nl.lat)),2)) d
  FROM nl JOIN read_csv('{SNAP}', all_varchar=true) e USING (sid))""").fetchone()
print(f'coordinate check vs station list: {r[0]} stations, median distance {r[1]:.0f} m')
c.execute(f"""COPY (SELECT m.sid, nl.* EXCLUDE (sid) FROM miss m LEFT JOIN nl USING (sid) ORDER BY m.sid)
              TO '{WORK}/recovered_nies.csv' (HEADER)""")
