"""
04_recover_missing.py — final metadata for the stations missing from the January 2026 station list.

Priority per field (first available wins), every value traceable to an official source:
  coordinates, name, address : NIES station file (latest FY 2016-2024)               [84 stations]
  municipality               : NIES station file municipality code (current)         [84]
                               else MIC code list: code in station ID (at registration);
                               abolished codes mapped to the successor municipality via
                               the MIC revision list (since 2005) or e-Stat code history [59]
  station type               : NIES station class, else digits 6-7 of the station ID
  romanised municipality     : NIES official romanisation for that municipality code,
                               else Hepburn romanisation of the official MIC kana (pykakasi)

Usage: python stations/04_recover_missing.py <work_dir>
Output: <work_dir>/recovered_stations.csv
"""
import sys
import duckdb
import unicodedata
import pykakasi

WORK = sys.argv[1]
c = duckdb.connect()
c.execute(f"CREATE TABLE off AS SELECT * FROM read_csv('{WORK}/recovered_official.csv', all_varchar=true)")
c.execute(f"CREATE TABLE nm AS SELECT * FROM read_csv('{WORK}/recovered_nies.csv', all_varchar=true)")
c.execute(f"""CREATE TABLE mic AS SELECT * FROM read_csv('{WORK}/mic_lookup.csv', all_varchar=true)""")
c.execute(f"""CREATE TABLE romaji AS SELECT * FROM read_csv('{WORK}/nies_romaji_by_code.csv', all_varchar=true)""")
# Abolished codes whose successor is not on the same row of the MIC revision list:
#   pre-2005 codes from e-Stat (標準地域コード履歴, queried 2026-11-04); the others from the
#   merger notes / 新設 rows of the MIC revision list (000875488.xlsx).
c.execute("""CREATE TABLE estat AS SELECT * FROM (VALUES
  ('05362', '昭和町 (南秋田郡)', '2005-03-22', '05211'),
  ('15563', '青海町 (西頸城郡)', '2005-03-19', '15216'),
  ('38212', '東予市', '2004-11-01', '38206'),
  ('09404', '小川町 (那須郡)', '2005-10-01', '09411'),
  ('16203', '新湊市', '2005-11-01', '16211'),
  ('16381', '小杉町 (射水郡)', '2005-11-01', '16211'),
  ('16362', '婦中町 (婦負郡)', '2005-04-01', '16201')) t(code5, old_name, abolished, successor_code5)""")

c.execute("""
CREATE TABLE fin AS
WITH b AS (
  SELECT o.sid, o.prefecture_en, o.code5 AS id_code5, o.type_from_code, o.code_status, o.city_ja AS id_city_ja,
         nm.fy, nm.city_code AS nies_code5, nm.name_romaji, nm.address_romaji, nm.station_class,
         TRY_CAST(nm.lat AS DOUBLE) lat, TRY_CAST(nm.lon AS DOUBLE) lon,
         coalesce(e.successor_code5, o.successor_code5) AS successor_code5, e.old_name AS estat_old_name
  FROM off o LEFT JOIN nm USING (sid) LEFT JOIN estat e ON e.code5 = o.code5),
k AS (
  SELECT *, CASE WHEN fy IS NOT NULL THEN nies_code5
                 WHEN code_status LIKE 'current%' THEN id_code5
                 ELSE successor_code5 END AS city_code5
  FROM b)
SELECT k.sid,
  k.name_romaji AS stationname_en,
  CASE WHEN k.fy IS NOT NULL THEN CASE k.station_class WHEN '1' THEN 'General' WHEN '2' THEN 'Roadside' ELSE 'Other' END
       ELSE k.type_from_code END AS stationtype_en,
  k.prefecture_en, m.city_ja, m.city_kana, k.city_code5, r.city_romaji,
  k.address_romaji AS street_en, k.lat, k.lon,
  CASE WHEN k.fy IS NOT NULL THEN 'nies_station_file_fy' || k.fy ELSE 'station_code_mic' END AS admin_source,
  CASE WHEN k.fy IS NOT NULL THEN 'NIES station file FY' || k.fy || '; municipality code ' || k.nies_code5
       WHEN k.code_status LIKE 'current%' THEN 'municipality code ' || k.id_code5 || ' from station ID (MIC list 2024-01-01); type from station ID digits 6-7'
       ELSE 'station ID municipality code ' || k.id_code5 || ' (' || coalesce(k.estat_old_name, k.id_city_ja, '') || ') abolished; successor '
            || k.successor_code5 || ' (MIC revision list / e-Stat code history); type from station ID digits 6-7' END AS admin_note
FROM k LEFT JOIN mic m ON m.code5 = k.city_code5 LEFT JOIN romaji r ON r.code5 = k.city_code5
ORDER BY k.sid""")

kks = pykakasi.kakasi()
rows = c.execute("SELECT sid, city_kana FROM fin WHERE city_romaji IS NULL AND city_kana IS NOT NULL").fetchall()
for sid, kana in rows:
    kana = unicodedata.normalize('NFKC', kana)
    if kana.endswith('ク') and 'シ' in kana:                     # ward of a designated city
        city, ward = kana.split('シ', 1)
        rom = (''.join(p['hepburn'] for p in kks.convert(city)).capitalize() + '-shi '
               + ''.join(p['hepburn'] for p in kks.convert(ward[:-1])).capitalize() + '-ku')
        c.execute("UPDATE fin SET city_romaji = ? WHERE sid = ?", [rom, sid])
        continue
    suffix = next((suf for k, suf in [('シ', '-shi'), ('マチ', '-machi'), ('チョウ', '-chou'), ('ムラ', '-mura'), ('ソン', '-son')]
                   if kana.endswith(k)), '')
    stem = kana[:len(kana) - {'-shi': 1, '-machi': 2, '-chou': 3, '-mura': 2, '-son': 2}.get(suffix, 0)]
    rom = ''.join(p['hepburn'] for p in kks.convert(stem)).capitalize() + suffix   # NIES style, e.g. Imizu-shi
    c.execute("UPDATE fin SET city_romaji = ? WHERE sid = ?", [rom, sid])
print("kana romanised with pykakasi:", len(rows))
c.execute(f"COPY fin TO '{WORK}/recovered_stations.csv' (HEADER)")
print(c.execute("""SELECT admin_source LIKE 'nies%' nies, count(*), count(city_ja), count(city_romaji), count(lat),
                   count(stationtype_en) FROM fin GROUP BY 1""").fetchall())
print(c.execute("SELECT sid, city_code5, city_ja, city_romaji, stationtype_en, admin_note FROM fin WHERE admin_source NOT LIKE 'nies%' LIMIT 6").fetchall())
print("missing city:", c.execute("SELECT list(sid) FROM fin WHERE city_ja IS NULL").fetchone())
