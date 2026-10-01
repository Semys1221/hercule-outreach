#!/usr/bin/env bash
# Run scrape worker loop on VPS (foreground).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export HERCULE_DATA_ROOT="${HERCULE_DATA_ROOT:-/var/lib/hercule}"
export PYTHONPATH="${PYTHONPATH:-$ROOT:$ROOT/scraper}"
export SCRAPER_PRESET="${SCRAPER_PRESET:?SCRAPER_PRESET is required}"

cd "$ROOT/scraper"
python3 main.py worker-loop --preset "$SCRAPER_PRESET" --target "${SCRAPER_TARGET:-5000}" --push-instantly
