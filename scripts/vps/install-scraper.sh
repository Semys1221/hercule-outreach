#!/usr/bin/env bash
# Install systemd scrape worker + 5-minute heal timer on the VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PRESET="${SCRAPER_PRESET:-cabinets_expertise_comptable}"
DATA_ROOT="${HERCULE_DATA_ROOT:-/var/lib/hercule}"
REPO_ROOT="${VPS_REPO_ROOT:-$ROOT}"
SERVICE_NAME="${VPS_SCRAPER_SERVICE:-hercule-scraper}"
TIMER_NAME="${SERVICE_NAME}-heal.timer"
HEAL_SERVICE="${SERVICE_NAME}-heal.service"
VENV_PYTHON="${VPS_VENV_PYTHON:-$REPO_ROOT/.venv/bin/python}"

echo "[install] repo=$REPO_ROOT data=$DATA_ROOT preset=$PRESET service=$SERVICE_NAME"

mkdir -p "$DATA_ROOT/streamlit_scraper/output/$PRESET"
mkdir -p "$DATA_ROOT/tmp"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "[install] creating venv at $REPO_ROOT/.venv"
  python3 -m venv "$REPO_ROOT/.venv"
  "$REPO_ROOT/.venv/bin/pip" install -q --upgrade pip
  "$REPO_ROOT/.venv/bin/pip" install -q -r "$REPO_ROOT/requirements.txt"
fi

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Hercule scraper worker loop (${PRESET})
After=network.target

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}/scraper
Environment=HERCULE_DATA_ROOT=${DATA_ROOT}
Environment=TMPDIR=${DATA_ROOT}/tmp
Environment=SCRAPER_PRESET=${PRESET}
Environment=VPS_SCRAPER_SERVICE=${SERVICE_NAME}
Environment=PYTHONPATH=${REPO_ROOT}:${REPO_ROOT}/scraper
ExecStart=${VENV_PYTHON} main.py worker-loop --preset ${PRESET} --push-instantly
Restart=always
RestartSec=10
StartLimitIntervalSec=0
KillSignal=SIGTERM
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF

cat > "/etc/systemd/system/${HEAL_SERVICE}" <<EOF
[Unit]
Description=Hercule scraper heal (${PRESET})

[Service]
Type=oneshot
WorkingDirectory=${REPO_ROOT}/scraper
Environment=HERCULE_DATA_ROOT=${DATA_ROOT}
Environment=TMPDIR=${DATA_ROOT}/tmp
Environment=SCRAPER_PRESET=${PRESET}
Environment=VPS_SCRAPER_SERVICE=${SERVICE_NAME}
Environment=PYTHONPATH=${REPO_ROOT}:${REPO_ROOT}/scraper
ExecStart=${VENV_PYTHON} main.py heal --preset ${PRESET} --stale-minutes 3
StandardOutput=append:${DATA_ROOT}/streamlit_scraper/heal-${PRESET}.log
StandardError=append:${DATA_ROOT}/streamlit_scraper/heal-${PRESET}.log
EOF

cat > "/etc/systemd/system/${TIMER_NAME}" <<EOF
[Unit]
Description=Hercule scraper heal timer (${PRESET})

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Unit=${HEAL_SERVICE}

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl enable "${TIMER_NAME}"

# Remove legacy hourly cron heal for this preset (if present).
( crontab -l 2>/dev/null | grep -v "main.py heal --preset ${PRESET}" || true ) | crontab -

systemctl restart "${TIMER_NAME}" || true

echo "[install] systemd unit ${SERVICE_NAME} enabled (Restart=always)."
echo "[install] heal timer ${TIMER_NAME} every 5 min → ${HEAL_SERVICE}."
echo "[install] Start with: systemctl start ${SERVICE_NAME}"
echo "[install] Comptable scraper (sole pipeline):"
echo "  sudo VPS_SCRAPER_SERVICE=hercule-scraper-comptable-fresh-geo SCRAPER_PRESET=cabinets_expertise_comptable_fresh_geo bash scripts/vps/install-scraper.sh"
echo "  sudo systemctl start hercule-scraper-comptable-fresh-geo"
