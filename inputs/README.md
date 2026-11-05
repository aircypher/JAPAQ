# Inputs

| File | What it is | Terms |
|---|---|---|
| `station_en_snapshot_2026-01.csv` | The Soramame station list of January 2026 (1,682 stations), geocoded with OpenStreetMap Nominatim by `stations/00_geocode_station_list.py`. Because OpenStreetMap changes over time, the pipeline uses this fixed result. | Station identifiers, names, types and coordinates: Ministry of the Environment, Japan (Public Data License 1.0). `city_en`, `street_en`, `pincode`: © OpenStreetMap contributors, Open Database License 1.0 (https://opendatacommons.org/licenses/odbl/1-0/). This file is **not** covered by the MIT licence of the code. |
| `external_sha256.txt` | SHA-256 checksums of the third-party files used for JAPAQ (NIES station files FY2016–2024, MIC code lists), downloaded by `stations/01_download_sources.sh`. | — |

The hourly observations and the Japanese station list are taken from the Zenodo record of the dataset
(`japaq_hourly_obs_v1.0.0.csv`, `japaq_station_info_v1.0.0.csv`).
