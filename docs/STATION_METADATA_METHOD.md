# Station metadata for the 143 stations missing from the station list snapshot

143 of the 1,806 stations with observations in 2018–2025 are not in the Soramame station list
downloaded in January 2026 (stations closed or renumbered before the snapshot). Their metadata
were recovered only from official sources, in this order.

## 1. NIES station data files — 84 stations

National Institute for Environmental Studies, The Environmental Observatory, Air Pollution
Monitoring Data File, station data (TM files), FY2016–FY2024 (https://tenbou.nies.go.jp/download/,
accessed 2026-11-04). Matched on the 8-digit station code (国環研局番), which is the same code
used by Soramame. The latest fiscal year in which each station appears is used.

Fields taken: coordinates (World Geodetic System, per the NIES format document TM_manu.pdf),
romanised station name and address, station class, municipality code and romanised name.

Check: for 1,650 stations present in both NIES and the Soramame snapshot, the coordinates
differ by a median of 79 m.

## 2. Station code + official municipality code lists — 59 stations

These 59 stations do not appear in any NIES station file from FY2016 to FY2024.

The station code is defined by the Ministry of the Environment (NIES, "測定局について — 測定局コード",
https://tenbou.nies.go.jp/download/explain_measuring_station.html):
- digits 1–2: prefecture code, MIC Standard Area Code;
- digits 3–5: municipality code, MIC Standard Area Code *at the time the station was
  registered* (not changed after later mergers);
- digits 6–7: station number — 01–50 general, 51–80 roadside, 81–99 other;
- digit 8: sub-number.

Municipality names were looked up as follows:
- codes still in use: MIC list of local government codes as of 2024-01-01
  (https://www.soumu.go.jp/denshijiti/code.html) — 51 stations;
- codes abolished since 2005: successor municipality from the MIC code revision list
  (since 2005-04-01) — 5 stations;
- codes abolished before 2005: e-Stat Standard Area Code history
  (https://www.e-stat.go.jp/municipalities/cities/areacodesearch, accessed 2026-11-04) — 3 stations
  (05362 昭和町 → 潟上市; 15563 青海町 → 糸魚川市; 38212 東予市 → 西条市).

Where the registration-time municipality has since merged, the current (successor)
municipality is reported, and the original code and name are kept in `metadata_note`.
Romanised names use the NIES romanisation for the same municipality code where available,
otherwise Hepburn romanisation of the official MIC kana.

These 59 stations have no coordinates; no official source for them was found.

## Validation of the station-code rules (1,682 stations with known metadata)

| Rule | Agreement |
|---|---|
| Prefecture from digits 1–2 | 1,682 / 1,682 (100%) |
| Station type from digits 6–7 | 1,649 / 1,682 (98.0%); differences are stations whose type changed after registration |
| Municipality code from digits 3–5 = current NIES municipality code | 1,340 / 1,650; most differences are later mergers, as the code definition states |

## Result

| Source | Stations | Prefecture | Municipality | Type | Coordinates |
|---|---|---|---|---|---|
| Soramame snapshot (Jan 2026) | 1,682 | yes | yes (OSM) | yes | yes |
| NIES station files | 84 | yes | yes | yes | yes |
| Station code + MIC / e-Stat | 59 | yes | yes | yes (98% rule) | no |

The values are in `japaq_station_en_v1.0.0.csv` (`metadata_source`, `metadata_note`). The scripts that produce them
(`nies_match.py`, `admin_codes.py`, `admin_final.py`) are in the code repository.
