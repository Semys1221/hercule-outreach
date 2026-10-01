#!/usr/bin/env bash
# Install supercronic and start scheduled outreach jobs on a background worker.
set -euo pipefail

SUPERCRONIC_VERSION="${SUPERCRONIC_VERSION:-v0.2.33}"
SUPERCRONIC_URL="https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64"
SUPERCRONIC_BIN="/usr/local/bin/supercronic"

if [ ! -x "$SUPERCRONIC_BIN" ]; then
  curl -fsSL -o "$SUPERCRONIC_BIN" "$SUPERCRONIC_URL"
  chmod +x "$SUPERCRONIC_BIN"
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CRONTAB="${ROOT}/scripts/render/${WORKER_CRONTAB:-scraper-crontab}"

echo "[worker-entrypoint] supercronic $CRONTAB HERCULE_DATA_ROOT=${HERCULE_DATA_ROOT:-/var/data}"
exec "$SUPERCRONIC_BIN" "$CRONTAB"
