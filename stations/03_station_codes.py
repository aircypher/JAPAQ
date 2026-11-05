"""
03_station_codes.py — recover administrative area and station type for the stations missing
from the January 2026 station list, using official references only.

References (downloaded by 01_download_sources.sh):
  * NIES, "測定局について — 測定局コード" (tenbou.nies.go.jp/download/explain_measuring_station.html):
    the 8-digit station code assigned by MOE. Digits 1-2 = prefecture code and digits 3-5 =
    municipality code of the MIC Standard Area Code at registration (not changed after
    mergers); digits 6-7 = station number: 01-50 general, 51-80 roadside, 81-99 other.
  * MIC, 全国地方公共団体コード, list as of 2024-01-01 (000925835.xlsx) and revision list
    since 2005-04-01 (000875488.xlsx), https://www.soumu.go.jp/denshijiti/code.html
  * NIES station data files (TM, FY2016-2024): official romanised municipality names.

Validation: the same rules are applied to the 1,682 stations with known metadata and
compared with their recorded prefecture, municipality (NIES files) and station type.

Usage: python stations/03_station_codes.py <external_dir> <station_snapshot.csv> <work_dir>
Output (in work_dir): mic_lookup.csv, nies_romaji_by_code.csv, recovered_official.csv,
                      method_check_official.txt
"""
import glob
import sys
import duckdb
import pandas as pd

EXT, SNAP, WORK = sys.argv[1:4]
c = duckdb.connect()

# ── MIC code tables (5-digit code = first 5 of the 6-digit code with check digit) ─────────
cur = pd.concat(pd.read_excel(f'{EXT}/mic/mic_codes_current_R6-01-01.xlsx', sheet_name=None, header=None, dtype=str).values())
cur = cur[cur[0].str.fullmatch(r'\d{6}', na=False)]
cur = pd.DataFrame({'code5': cur[0].str[:5], 'pref_ja': cur[1], 'city_ja': cur[2], 'city_kana': cur[4],
                    'valid': 'current (2024-01-01)'}).drop_duplicates('code5')
rev = pd.read_excel(f'{EXT}/mic/mic_code_revisions_since_H17.xlsx', header=None, dtype=str)
rev = rev[rev[5].str.fullmatch(r'\d{6}', na=False)]
old = pd.DataFrame({'code5': rev[5].str[:5], 'pref_ja': rev[4].ffill(), 'city_ja': rev[6], 'city_kana': rev[7],
                    'valid': 'abolished; ' + rev[12].fillna('') + ' ' + rev[13].fillna('').str[:10],
                    'successor_code5': rev[9].str[:5]})
old = old[~old.code5.isin(cur.code5)].drop_duplicates('code5')
c.register('cur', cur); c.register('old', old)
c.execute("CREATE TABLE mic AS SELECT code5, pref_ja, city_ja, city_kana, valid, NULL AS successor_code5 FROM cur "
          "UNION ALL SELECT code5, pref_ja, city_ja, city_kana, valid, successor_code5 FROM old")

# ── NIES official romanisation per municipality code, prefecture names ────────────────────
files = sorted(glob.glob(f'{WORK}/nies_utf8/*.utf8.csv'))
c.execute(f"""CREATE TABLE nies AS SELECT * FROM read_csv({files}, all_varchar=true, header=true, union_by_name=true)""")
c.execute("""CREATE TABLE romaji AS SELECT "市区町村コード" code5, any_value("市区町村名_ローマ字") city_romaji
             FROM nies WHERE "市区町村コード" IS NOT NULL GROUP BY 1""")
c.execute("""CREATE TABLE nies_st AS SELECT "国環研局番" sid, any_value("市区町村コード" ORDER BY "年度" DESC) code5_now,
             any_value("測定局区分" ORDER BY "年度" DESC) cls FROM nies GROUP BY 1""")

PREF_EN = {'01': 'Hokkaido', '02': 'Aomori', '03': 'Iwate', '04': 'Miyagi', '05': 'Akita', '06': 'Yamagata',
           '07': 'Fukushima', '08': 'Ibaraki', '09': 'Tochigi', '10': 'Gunma', '11': 'Saitama', '12': 'Chiba',
           '13': 'Tokyo', '14': 'Kanagawa', '15': 'Niigata', '16': 'Toyama', '17': 'Ishikawa', '18': 'Fukui',
           '19': 'Yamanashi', '20': 'Nagano', '21': 'Gifu', '22': 'Shizuoka', '23': 'Aichi', '24': 'Mie',
           '25': 'Shiga', '26': 'Kyoto', '27': 'Osaka', '28': 'Hyogo', '29': 'Nara', '30': 'Wakayama',
           '31': 'Tottori', '32': 'Shimane', '33': 'Okayama', '34': 'Hiroshima', '35': 'Yamaguchi',
           '36': 'Tokushima', '37': 'Kagawa', '38': 'Ehime', '39': 'Kochi', '40': 'Fukuoka', '41': 'Saga',
           '42': 'Nagasaki', '43': 'Kumamoto', '44': 'Oita', '45': 'Miyazaki', '46': 'Kagoshima', '47': 'Okinawa'}
c.execute(f"COPY mic TO '{WORK}/mic_lookup.csv' (HEADER)")
c.execute(f"COPY romaji TO '{WORK}/nies_romaji_by_code.csv' (HEADER)")
c.execute("CREATE TABLE pref AS SELECT * FROM (VALUES " + ",".join(f"('{k}','{v}')" for k, v in PREF_EN.items()) + ") t(code2, prefecture_en)")

def recover(table):
    return f"""
    SELECT s.sid, substr(s.sid,1,2) code2, p.prefecture_en, substr(s.sid,1,5) code5,
      m.pref_ja, m.city_ja, m.city_kana, r.city_romaji, m.valid AS code_status, m.successor_code5,
      CASE WHEN substr(s.sid,6,2)::INT BETWEEN 1 AND 50 THEN 'General'
           WHEN substr(s.sid,6,2)::INT BETWEEN 51 AND 80 THEN 'Roadside' ELSE 'Other' END AS type_from_code
    FROM {table} s LEFT JOIN pref p ON p.code2 = substr(s.sid,1,2)
    LEFT JOIN mic m ON m.code5 = substr(s.sid,1,5) LEFT JOIN romaji r ON r.code5 = substr(s.sid,1,5)"""

# ── Validation on the 1,682 known stations ───────────────────────────────────────────────
c.execute(f"CREATE TABLE known AS SELECT * FROM read_csv('{SNAP}', all_varchar=true)")
c.execute(f"CREATE TABLE kr AS {recover('known')}")
out = []
out.append("VALIDATION on stations with known metadata (n=%d)" % c.execute("SELECT count(*) FROM known").fetchone()[0])
out.append("  prefecture from digits 1-2 = recorded prefecture_en: %s" % (c.execute(
    "SELECT count(*) FILTER (kr.prefecture_en = k.prefecture_en), count(*) FROM kr JOIN known k USING (sid)").fetchone(),))
out.append("  municipality code (digits 1-5) found in MIC list: %s" % (c.execute(
    "SELECT count(city_ja), count(*) FROM kr").fetchone(),))
out.append("  digits 1-5 = NIES municipality code of the station (latest FY): %s" % (c.execute(
    "SELECT count(*) FILTER (kr.code5 = n.code5_now), count(*) FROM kr JOIN nies_st n USING (sid)").fetchone(),))
out.append("  ... mismatches explained by a later merger (code abolished in MIC list): %s" % (c.execute(
    "SELECT count(*) FILTER (kr.code_status LIKE 'abolished%'), count(*) FROM kr JOIN nies_st n USING (sid) WHERE kr.code5 <> n.code5_now").fetchone(),))
out.append("  station type from digits 6-7 = recorded stationtype_en: %s" % (c.execute(
    "SELECT count(*) FILTER (kr.type_from_code = k.stationtype_en), count(*) FROM kr JOIN known k USING (sid)").fetchone(),))
out.append("  type mismatches: %s" % (c.execute(
    "SELECT kr.type_from_code, k.stationtype_en, count(*) FROM kr JOIN known k USING (sid) WHERE kr.type_from_code <> k.stationtype_en GROUP BY ALL").fetchall(),))

# ── The 143 stations ─────────────────────────────────────────────────────────────────────
c.execute(f"CREATE TABLE miss AS SELECT DISTINCT sid FROM read_csv('{WORK}/missing_stations.csv', all_varchar=true)")
c.execute(f"CREATE TABLE mr AS {recover('miss')}")
c.execute(f"COPY (SELECT * FROM mr ORDER BY sid) TO '{WORK}/recovered_official.csv' (HEADER)")
out.append("\nTHE STATIONS TO RECOVER")
out.append("  prefecture recovered: %s" % (c.execute("SELECT count(prefecture_en), count(*) FROM mr").fetchone(),))
out.append("  municipality code in MIC list (current / abolished / not found): %s" % (c.execute(
    "SELECT count(*) FILTER (code_status LIKE 'current%'), count(*) FILTER (code_status LIKE 'abolished%'), count(*) FILTER (city_ja IS NULL) FROM mr").fetchone(),))
out.append("  official romanised name from NIES files: %s" % (c.execute("SELECT count(city_romaji), count(*) FROM mr").fetchone(),))
out.append("  station type from code: %s" % (c.execute("SELECT type_from_code, count(*) FROM mr GROUP BY 1 ORDER BY 1").fetchall(),))
out.append("  not found in MIC list: %s" % (c.execute("SELECT list(sid) FROM mr WHERE city_ja IS NULL").fetchone(),))
open(f'{WORK}/method_check_official.txt', 'w').write("\n".join(out) + "\n")
print("\n".join(out))
