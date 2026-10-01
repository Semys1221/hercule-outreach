#!/usr/bin/env bash
# Run Outscraper scrape headlessly (Render / local).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
if [ -z "${RENDER:-}" ] && [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-$ROOT:$ROOT/scraper}"
export HERCULE_DATA_ROOT="${HERCULE_DATA_ROOT:-/var/data}"

cd "$ROOT/scraper"

TARGET="${SCRAPER_TARGET:-5000}"
PRESET="${SCRAPER_PRESET:?SCRAPER_PRESET is required}"

args=(scrape --preset "$PRESET" --target "$TARGET" --resume)
if [ "${SCRAPER_PUSH_INSTANTLY:-1}" = "1" ]; then
  args+=(--push-instantly)
fi

echo "[run-scraper] preset=$PRESET target=$TARGET data_root=$HERCULE_DATA_ROOT"
python main.py "${args[@]}"
