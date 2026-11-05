#!/usr/bin/env bash
# 01_download_sources.sh — download the third-party files used to recover station metadata:
#   NIES station data files (TM), fiscal years 2016-2024, and the two MIC local-government code lists.
# The files are not redistributed in this repository. Their SHA-256 checksums at the time of the
# JAPAQ build are in inputs/external_sha256.txt; a mismatch means the provider has updated a file.
# Usage: bash stations/01_download_sources.sh <external_dir>
set -euo pipefail
OUT="${1:-external}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$OUT/nies" "$OUT/mic"
cd "$OUT/nies"
curl -s -c ck -b ck https://tenbou.nies.go.jp/download/ -o /dev/null          # session cookie
for y in 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
  curl -s -b ck -X POST https://tenbou.nies.go.jp/download/api/archivedownload.php \
       -d type=tm -d file="TM${y}0000.zip" -o "TM${y}0000.zip"
done
rm -f ck
cd ../mic
curl -s -o mic_codes_current_R6-01-01.xlsx      https://www.soumu.go.jp/main_content/000925835.xlsx
curl -s -o mic_code_revisions_since_H17.xlsx    https://www.soumu.go.jp/main_content/000875488.xlsx
cd ..
if sha256sum -c "$HERE/inputs/external_sha256.txt"; then
  echo "All downloaded files match the versions used for JAPAQ."
else
  echo "WARNING: some files differ from the versions used for JAPAQ (see above); results may differ." >&2
fi
