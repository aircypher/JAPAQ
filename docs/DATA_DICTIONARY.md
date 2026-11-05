# Data dictionary

## Feature table — `japaq_feature_obs_v1.0.0` (CSV and Parquet, 110,328,514 rows, 48 columns)

One row per station and hour with at least one valid value of the five pollutants. Empty = missing in
the source, or set to null by quality control (the corrections log says which).

### Identifiers

| Column | Type | Meaning |
|---|---|---|
| `sid` | text (8 digits) | Station code of the Ministry of the Environment: digits 1–2 prefecture, 3–5 municipality at registration, 6–7 station number (01–50 general, 51–80 roadside) |
| `tid` | text | Observation identifier, `T` + 9 digits; the same in the graph and the corrections log |

### Station (original columns, as in the January 2026 station list; empty for 143 closed stations)

| Column | Meaning |
|---|---|
| `stationname_en` | Station name, romanised |
| `stationtype_en` | `General` (ambient) or `Roadside` |
| `prefecture_en`, `city_en`, `street_en`, `pincode` | Address (city, street, and postal code from OpenStreetMap) |
| `lat`, `lon` | Coordinates (WGS84, degrees) |

### Station (resolved columns — complete; use these)

| Column | Meaning |
|---|---|
| `stationname_resolved`, `stationtype_resolved`, `prefecture_resolved`, `city_resolved`, `street_resolved`, `lat_resolved`, `lon_resolved` | Same fields for all stations: the station list where available, otherwise recovered from NIES station files or from the station code; Japanese-script addresses romanised. Equal to the columns of `japaq_station_en_v1.0.0.csv`. 59 stations have no coordinates, street, or name (no official source) |
| `source` | Key into `sources.csv` (`AEROS`: the measurements come from the Soramame system) |

### Time (Japan Standard Time; the timestamp marks the end of the hour)

| Column | Meaning |
|---|---|
| `obsdate` | `YYYY-MM-DD HH:MM:SS`; hour 24 of a day is written as 00:00 of the next day |
| `year`, `month`, `hour` | From `obsdate` |
| `month_name`, `weekday_name` | English names |
| `dayType` | `Weekday`, `Weekend`, `Holiday` (Japanese public holidays), `Unknown` (1 January 2026 00:00) |
| `timeCategory` | `Early Morning` 05–08, `Morning` 09–11, `Afternoon` 12–16, `Evening` 17–20, `Night` 21–04 |
| `season` | `Spring` Mar–May, `Summer` Jun–Aug, `Autumn` Sep–Nov, `Winter` Dec–Feb |

### Pollutants (hourly values)

| Column | Pollutant | Unit |
|---|---|---|
| `pm25` | Fine particulate matter, PM2.5 | µg/m³ |
| `so2` | Sulphur dioxide | ppm |
| `no` | Nitric oxide | ppm |
| `spm` | Suspended particulate matter | mg/m³ |
| `ox` | Photochemical oxidants | ppm |
| `pm25_level`, `so2_level`, `no_level`, `spm_level`, `ox_level` | Severity label: `Safe`, `Moderate`, `Slightly Unhealthy`, `Unhealthy`, `Very Unhealthy`; empty when the value is empty | — |
| `pm25_flag`, `no_flag`, `spm_flag`, `ox_flag` | Stage 4 quality flag: name of the rule (`physical_cap`, `stuck_run`, `instrument_ceiling`, `short_burst`, `reviewed_event`); empty = not flagged. SO2 is not screened | — |

| Pollutant | Safe | Moderate | Slightly Unhealthy | Unhealthy | Very Unhealthy |
|---|---|---|---|---|---|
| PM2.5 (µg/m³) | <15 | 15–35 | 35–55 | 55–150 | ≥150 |
| SO2 (ppm) | <0.04 | 0.04–0.1 | 0.1–0.2 | 0.2–1.0 | ≥1.0 |
| NO (ppm) | <0.02 | 0.02–0.06 | 0.06–0.20 | 0.20–1.0 | ≥1.0 |
| SPM (mg/m³) | <0.10 | 0.10–0.20 | 0.20–0.40 | 0.40–1.0 | ≥1.0 |
| Ox (ppm) | <0.06 | 0.06–0.12 | 0.12–0.24 | 0.24–0.40 | ≥0.40 |

The labels are descriptive: standards defined on daily, 24-hour, or annual averages are applied to
hourly values, and NO has no standard. The basis of each boundary is given in the article.

### Meteorology (measured at a subset of stations)

| Column | Meaning | Unit |
|---|---|---|
| `ws` | Wind speed (1,038 stations) | m/s |
| `temp` | Air temperature (310 stations) | °C |
| `hum` | Relative humidity (293 stations) | % |
| `ws_level` | Beaufort class of the Japan Meteorological Agency (`Calm` … `Hurricane force`) | — |
| `ws_flag`, `temp_flag`, `hum_flag` | Stage 4 quality flag (`stuck_run`, `neighbour_check`); empty = not flagged | — |

## Corrections log — `japaq_corrections_log_v1.0.0.csv` (2,473,666 rows)

| Column | Meaning |
|---|---|
| `sid`, `tid`, `obsdate` | Station, observation, time |
| `variable` | `pm25`, `so2`, `no`, `spm`, `ox`, `ws`, `temp`, `hum` |
| `original_value` | Value in the raw file |
| `stage` | `1` negative, `2` fill code, `3` station or event artifact, `4` implausible (flag), `W` meteorological range |
| `rule` | Rule name |
| `action` | `nulled` (value removed in the feature table and graph) or `flagged` (value kept, `*_flag` set) |

## Raw file — `japaq_hourly_obs_v1.0.0.csv` (114,237,726 rows)

`stationid, obsdate, so2, no, spm, ox, pm25, ws, temp, hum`, exactly as downloaded, including negative
values and fill codes. It contains every downloaded row, also rows without any valid pollutant value
(not in the feature table).

## Station table — `japaq_station_en_v1.0.0.csv` (1,825 stations)

`sid, stationname_en, stationtype_en, prefecture_en, city_en, street_en, pincode, lat, lon` (complete
values, as the `*_resolved` columns of the feature table), `metadata_source`
(`station_metadata_snapshot`, `nies_station_file_fy<year>`, or `station_code_mic`), `metadata_note`
(how each field was obtained), `source` (keys into `sources.csv`).

## Other files

- `japaq_station_info_v1.0.0.csv` — the Soramame station list (Japanese), with the variables measured at
  each station.
- `japaq_romanisation_log_v1.0.0.csv` — `sid, field, original, new, method` for every romanised address.
- `sources.csv` — `source_id, citation, url, version, licence, covers` for AEROS, OSM, NIES, MIC.

## Coverage gaps

No station has records for 12–31 July 2019, 29–31 March 2021, 27–30 September 2022, and
1 October – 31 December 2024 (absent from the source files).
