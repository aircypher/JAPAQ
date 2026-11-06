"""
00_geocode_station_list.py
==========================
Reads the Soramame station list (japaq_raw_station_list_v1.0.0.csv), romanizes station names with
pykakasi, reverse-geocodes each station's lat/lon via OpenStreetMap Nominatim, and writes the
English station list. The output used for JAPAQ (January 2026) is provided as
inputs/station_en_snapshot_2026-01.csv; because OpenStreetMap changes over time, a new run can
return different addresses, so the later steps use the provided file.

Inputs:
  STATION_INFO_CSV : station_info.csv  (1,683 rows)

Output:
  OUT_CSV          : station_en.csv    (1,682 rows, 9 columns)
    sid, stationname_en, stationtype_en, prefecture_en,
    city_en, street_en, pincode, lat, lon

Usage:
  python stations/00_geocode_station_list.py <japaq_raw_station_list_v1.0.0.csv> <out.csv>

Note: Nominatim ToS requires max 1 request/second. With 1,682 stations
      this takes ~30 minutes. Output is saved to disk so it only needs
      to run once.
"""

import csv
import re
import time
from pathlib import Path

import pykakasi
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from tqdm import tqdm

# =============================================================================
# PATHS
# =============================================================================
import sys
STATION_INFO_CSV = sys.argv[1]
OUT_CSV          = sys.argv[2]

# =============================================================================
# GEOCODING SETTINGS
# =============================================================================
NOMINATIM_USER_AGENT = "japaq_kg_pipeline"
NOMINATIM_TIMEOUT    = 10    # seconds per request
NOMINATIM_RETRIES    = 3
NOMINATIM_DELAY      = 1.1   # seconds between requests (Nominatim ToS: max 1 req/s)

# =============================================================================
# PREFECTURE MAP  (first 2 digits of stationid → English name)
# =============================================================================
PREFECTURE_MAP = {
    "01": "Hokkaido",   "02": "Aomori",    "03": "Iwate",     "04": "Miyagi",
    "05": "Akita",      "06": "Yamagata",  "07": "Fukushima", "08": "Ibaraki",
    "09": "Tochigi",    "10": "Gunma",     "11": "Saitama",   "12": "Chiba",
    "13": "Tokyo",      "14": "Kanagawa",  "15": "Niigata",   "16": "Toyama",
    "17": "Ishikawa",   "18": "Fukui",     "19": "Yamanashi", "20": "Nagano",
    "21": "Gifu",       "22": "Shizuoka",  "23": "Aichi",     "24": "Mie",
    "25": "Shiga",      "26": "Kyoto",     "27": "Osaka",     "28": "Hyogo",
    "29": "Nara",       "30": "Wakayama",  "31": "Tottori",   "32": "Shimane",
    "33": "Okayama",    "34": "Hiroshima", "35": "Yamaguchi", "36": "Tokushima",
    "37": "Kagawa",     "38": "Ehime",     "39": "Kochi",     "40": "Fukuoka",
    "41": "Saga",       "42": "Nagasaki",  "43": "Kumamoto",  "44": "Oita",
    "45": "Miyazaki",   "46": "Kagoshima", "47": "Okinawa",
}

STATIONTYPE_MAP = {"一般局": "General", "自排局": "Roadside"}

_GEO_RE = re.compile(r"\(?\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)?")


# =============================================================================
# HELPERS
# =============================================================================

def romanize(text: str, kks) -> str:
    """Romanize Japanese text to title-cased Hepburn romaji using pykakasi."""
    if not text or not text.strip():
        return ""
    parts = [item["hepburn"] for item in kks.convert(text)]
    merged: list[str] = []
    for p in parts:
        if p.isdigit() and merged and merged[-1].isdigit():
            merged[-1] += p
        else:
            merged.append(p)
    return " ".join(p.capitalize() for p in merged if p.strip())


def parse_geolocation(val: str):
    """Parse '(lon, lat)' string → (lat, lon). Returns (None, None) on failure."""
    if not val:
        return None, None
    m = _GEO_RE.match(val.strip())
    if not m:
        return None, None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


def reverse_geocode(geolocator, lat: float, lon: float):
    """
    Call Nominatim reverse geocoding for (lat, lon).
    Returns (city_en, street_en, pincode). Retries on timeout/error.
    """
    for attempt in range(NOMINATIM_RETRIES):
        try:
            location = geolocator.reverse(
                (lat, lon),
                language="en",
                timeout=NOMINATIM_TIMEOUT,
            )
            if not location:
                return "", "", ""

            addr = location.raw.get("address", {})

            city_en = (
                addr.get("city") or
                addr.get("town") or
                addr.get("village") or
                addr.get("county") or
                addr.get("state_district") or
                ""
            )
            street_en = (
                addr.get("road") or
                addr.get("suburb") or
                addr.get("neighbourhood") or
                ""
            )
            pincode = addr.get("postcode", "")

            return city_en, street_en, pincode

        except (GeocoderTimedOut, GeocoderServiceError):
            if attempt < NOMINATIM_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return "", "", ""

    return "", "", ""


# =============================================================================
# MAIN
# =============================================================================

def main():
    print(f"Input : {STATION_INFO_CSV}")
    print(f"Output: {OUT_CSV}")

    kks = pykakasi.kakasi()
    geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT)

    with open(STATION_INFO_CSV, newline="", encoding="utf-8") as f:
        stations = list(csv.DictReader(f))

    print(f"\nColumns: {list(stations[0].keys())}")
    print(f"Stations to process: {len(stations)}")
    print(f"Estimated time: ~{len(stations) * NOMINATIM_DELAY / 60:.0f} minutes\n")

    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)

    n_skipped = n_geocoded = n_geocode_failed = 0

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout)
        writer.writerow([
            "sid", "stationname_en", "stationtype_en", "prefecture_en",
            "city_en", "street_en", "pincode", "lat", "lon",
        ])

        for row in tqdm(stations, desc="Geocoding stations", unit="station"):
            sid = row.get("stationid", "").strip()

            if sid == "S" or not sid:
                n_skipped += 1
                continue

            stationname_en = romanize(row.get("stationname", "").strip(), kks)
            stationtype_en = STATIONTYPE_MAP.get(row.get("stationtype", "").strip(), "Other")
            prefecture_en  = PREFECTURE_MAP.get(sid[:2], "")
            lat, lon       = parse_geolocation(row.get("geolocation", ""))

            city_en = street_en = pincode = ""
            if lat is not None and lon is not None:
                city_en, street_en, pincode = reverse_geocode(geolocator, lat, lon)
                if city_en:
                    n_geocoded += 1
                else:
                    n_geocode_failed += 1
                time.sleep(NOMINATIM_DELAY)

            writer.writerow([
                sid, stationname_en, stationtype_en, prefecture_en,
                city_en, street_en, pincode,
                lat if lat is not None else "",
                lon if lon is not None else "",
            ])

    total = len(stations) - n_skipped
    print(f"\nDone.")
    print(f"  Written       : {total} stations → {OUT_CSV}")
    print(f"  Geocoded      : {n_geocoded}")
    print(f"  Geocode failed: {n_geocode_failed}")
    print(f"  Skipped       : {n_skipped} (malformed sid)")


if __name__ == "__main__":
    main()
