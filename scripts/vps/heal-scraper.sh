#!/usr/bin/env bash
# Hourly heal — resume scrape when worker stalled and under target.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export HERCULE_DATA_ROOT="${HERCULE_DATA_ROOT:-/var/lib/hercule}"
export PYTHONPATH="${PYTHONPATH:-$ROOT:$ROOT/scraper}"
export SCRAPER_PRESET="${SCRAPER_PRESET:?SCRAPER_PRESET is required}"

cd "$ROOT/scraper"
python3 main.py heal --preset "$SCRAPER_PRESET"
