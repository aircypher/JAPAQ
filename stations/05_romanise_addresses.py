"""
05_romanise_addresses.py — remove Japanese script from the English station metadata.

OpenStreetMap/Nominatim returned some street (and one city) names in Japanese. For every value
of station_en.csv that contains kana or kanji:
  * Japanese punctuation only (e.g. the middle dot ･) -> normalised (NFKC; middle dot -> " / ");
  * station present in the NIES station files -> NIES official romanised address (street_en) or
    romanised municipality name (city_en);
  * otherwise -> Hepburn romanisation of the Japanese text (pykakasi).
Each change is recorded in admin_note and in romanisation_log.csv.

Usage: python stations/05_romanise_addresses.py <station_snapshot.csv> <work_dir>/nies_station_latest.csv <work_dir>
Output: <work_dir>/station_en_romanised.csv, <work_dir>/romanisation_log.csv
"""
import re
import sys
import unicodedata
import pandas as pd
import pykakasi

SRC, NIES, OUT = sys.argv[1:4]
JP = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")      # kana, kanji, half-width kana
DOTS = re.compile(r"[・･]")                                 # ・ and ･
kks = pykakasi.kakasi()

def hepburn(t):
    t = unicodedata.normalize("NFKC", t)
    return " ".join(w["hepburn"].capitalize() for w in kks.convert(t) if w["hepburn"].strip()).strip()

def strip_suffix(city):
    # NIES style "Yabuki-machi" -> "Yabuki", matching the OSM style used for city_en
    return re.sub(r"-(shi|machi|cho|chou|mura|son|ku)\b.*$", "", city or "").strip() or city

st = pd.read_csv(SRC, dtype=str)
nies = pd.read_csv(NIES, dtype=str).set_index("sid")
st["admin_note"] = "Soramame station list (January 2026 snapshot); English address from OpenStreetMap/Nominatim"
log = []
for i, r in st.iterrows():
    notes = []
    for col in ("street_en", "city_en"):
        v = r[col]
        if not isinstance(v, str) or not (JP.search(v) or DOTS.search(v)):
            continue
        if not JP.search(DOTS.sub("", v)):
            new, how = re.sub(r"\s+", " ", DOTS.sub(" / ", unicodedata.normalize("NFKC", v))).strip(), "punctuation normalised"
        elif r["sid"] in nies.index and isinstance(nies.at[r["sid"], "address_romaji" if col == "street_en" else "city_romaji"], str):
            n = nies.at[r["sid"], "address_romaji" if col == "street_en" else "city_romaji"]
            new, how = (n, "NIES romanised address") if col == "street_en" else (strip_suffix(n), "NIES romanised municipality")
        else:
            new, how = hepburn(v), "Hepburn romanisation of OSM value"
        st.at[i, col] = new
        log.append({"sid": r["sid"], "field": col, "original": v, "new": new, "method": how})
        notes.append(f"{col}: {how}")
    if notes:
        st.at[i, "admin_note"] += "; " + "; ".join(notes)

st.to_csv(f"{OUT}/station_en_romanised.csv", index=False)
lg = pd.DataFrame(log)
lg.to_csv(f"{OUT}/romanisation_log.csv", index=False)
print(lg.groupby(["field", "method"]).size().to_string())
left = st[["street_en", "city_en", "stationname_en"]].fillna("").apply(lambda c: c.map(lambda x: bool(JP.search(x)))).sum()
print("remaining values with Japanese script:", left.to_dict())
