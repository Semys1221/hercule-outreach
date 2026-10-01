#!/usr/bin/env bash
# Install scraper fleet observability on the VPS:
#   - hercule-scraper-exporter.service (Prometheus :9464)
#   - Docker Compose stack (Prometheus, Grafana, Loki, Promtail, node_exporter)
#
# Usage (on VPS, as root):
#   sudo bash scripts/vps/install-monitoring.sh
#
# Access Grafana from your Mac:
#   ssh -L 3000:127.0.0.1:3000 root@201.18.210.83
#   open http://127.0.0.1:3000  (user: admin)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="${VPS_REPO_ROOT:-$ROOT}"
DATA_ROOT="${HERCULE_DATA_ROOT:-/var/lib/hercule}"
VENV_PYTHON="${VPS_VENV_PYTHON:-$REPO_ROOT/.venv/bin/python}"
MONITOR_DIR="$REPO_ROOT/scripts/vps/monitoring"
CRED_DIR="/root/.hercule"
PASSWORD_FILE="$CRED_DIR/grafana-admin-password"
EXPORTER_UNIT="/etc/systemd/system/hercule-scraper-exporter.service"
TEMPLATE="$MONITOR_DIR/hercule-scraper-exporter.service.template"

echo "[install-monitoring] repo=$REPO_ROOT data=$DATA_ROOT"

if [ "$(id -u)" -ne 0 ]; then
  echo "[install-monitoring] must run as root (sudo)" >&2
  exit 1
fi

mkdir -p "$DATA_ROOT/streamlit_scraper/output"
mkdir -p "$CRED_DIR"
chmod 700 "$CRED_DIR"

# --- Grafana admin password ---
if [ ! -f "$PASSWORD_FILE" ]; then
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -d '/+=' | head -c 24 > "$PASSWORD_FILE"
  else
    head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24 > "$PASSWORD_FILE"
  fi
  chmod 600 "$PASSWORD_FILE"
  echo "[install-monitoring] generated Grafana password → $PASSWORD_FILE"
else
  echo "[install-monitoring] reusing Grafana password at $PASSWORD_FILE"
fi

# --- Python exporter deps ---
if [ ! -x "$VENV_PYTHON" ]; then
  echo "[install-monitoring] creating venv at $REPO_ROOT/.venv"
  python3 -m venv "$REPO_ROOT/.venv"
  "$REPO_ROOT/.venv/bin/pip" install -q --upgrade pip
fi
"$REPO_ROOT/.venv/bin/pip" install -q -r "$REPO_ROOT/requirements.txt"

# --- systemd exporter unit ---
if [ ! -f "$TEMPLATE" ]; then
  echo "[install-monitoring] missing template $TEMPLATE" >&2
  exit 1
fi
sed \
  -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
  -e "s|__DATA_ROOT__|$DATA_ROOT|g" \
  -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
  "$TEMPLATE" > "$EXPORTER_UNIT"

systemctl daemon-reload
systemctl enable hercule-scraper-exporter
systemctl restart hercule-scraper-exporter
echo "[install-monitoring] hercule-scraper-exporter enabled and started (:9464)"

# Smoke check exporter
sleep 2
if curl -fsS "http://127.0.0.1:9464/metrics" >/dev/null 2>&1; then
  echo "[install-monitoring] exporter /metrics OK"
else
  echo "[install-monitoring] WARN: exporter not responding yet — check: journalctl -u hercule-scraper-exporter -n 50" >&2
fi

# --- Docker ---
if ! command -v docker >/dev/null 2>&1; then
  echo "[install-monitoring] Docker not found. Install Docker Engine first:" >&2
  echo "  https://docs.docker.com/engine/install/" >&2
  exit 1
fi

COMPOSE=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    echo "[install-monitoring] docker compose plugin missing" >&2
    exit 1
  fi
fi

export HERCULE_DATA_ROOT="$DATA_ROOT"
GRAFANA_ADMIN_PASSWORD="$(tr -d '\n' < "$PASSWORD_FILE")"
export GRAFANA_ADMIN_PASSWORD

cd "$MONITOR_DIR"
"${COMPOSE[@]}" up -d

echo ""
echo "[install-monitoring] stack up."
echo "  Grafana   http://127.0.0.1:3000  (user: admin)"
echo "  Password  cat $PASSWORD_FILE"
echo "  Prometheus http://127.0.0.1:9090"
echo "  Exporter  http://127.0.0.1:9464/metrics"
echo ""
echo "From your Mac:"
echo "  ssh -L 3000:127.0.0.1:3000 root@201.18.210.83"
echo "  open http://127.0.0.1:3000"
echo ""
echo "Dashboard: Hercule → Hercule Scraper Fleet"
