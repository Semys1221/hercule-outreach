# Streamlit Scraper

## AI agents

Before editing this app, read:
1. [`.cursor/skills/hercule-streamlit/SKILL.md`](../../../.cursor/skills/hercule-streamlit/SKILL.md) (router)
2. [`.cursor/skills/hercule-streamlit-scraper/SKILL.md`](../../../.cursor/skills/hercule-streamlit-scraper/SKILL.md)

## Architecture

```
repo .env  →  config_loader.py  →  configs/{preset}_config.py
                                        ↓
                                   core_logic.py
                                    ↙         ↘
                              main.py      app.py (st.navigation)
                                        ↓
                          output/{preset}/outscraper_leads.csv
                          output/{preset}/mev_emails.csv
                          output/{preset}/onboarding_state.json
```

Presets are **flat** (no niche groups). Each preset lives in [`configs/`](configs/) as `{preset_id}_config.py`.

## Setup

```bash
cd lib/backend/streamlit_scraper
pip install -r requirements.txt
pnpm streamlit-scraper
```

Required in repo root [`.env`](../../.env):

| Variable | Purpose |
|----------|---------|
| `OUTSCRAPER_API_KEY` | Outscraper Google Maps API |
| `INSTANTLY_API_KEY` | Instantly list/campaign/push |
| `CRON_SECRET` / `INSTANTLY_BYPASS_WEBHOOK_SECRET` | Subsequence webhook (tab 5); CIF post-push link provision |
| `CRM_BACKEND_URL` | Hercule API base for auto link provision (default `https://www.hercule.dev`) |

Optional VPS remote control (Scrape page):

| Variable | Purpose |
|----------|---------|
| `VPS_HOST` | SSH host for scrape worker |
| `VPS_USER` | SSH user (e.g. `root`) |
| `VPS_SSH_PASSWORD` | Password (optional if SSH keys work) |
| `VPS_REPO_ROOT` | Repo path on VPS (default `/root/hercule.dev`) |
| `HERCULE_DATA_ROOT` | Persistent data dir (default `/var/lib/hercule`) |
| `VPS_SCRAPER_SERVICE` | systemd unit name (default `hercule-scraper`) |

## Onboarding (Streamlit UI)

Two sidebar pages via **`st.navigation`** in [`app.py`](app.py) — **Onboarding** and **Scrape** (sidebar navigation).

### Onboarding (tabs 1–6)

| Tab | Action |
|-----|--------|
| **1 Config** | Select existing or **Create new** — full form, Save writes `configs/{id}_config.py` (no Instantly IDs yet) |
| **2 Liste** | Select or create Instantly lead list |
| **3 Campagne** | Select or create Instantly campaign (stays **draft**) |
| **4 2 emails** | Write 2 cold-email steps → PATCH campaign sequences |
| **5 E1–E3** | Write subsequence emails → Instantly + Supabase templates + webhook init |
| **6 Prompt buyer** | Write reply-agent buyer prompt → file + Supabase when campaign is active |

When tab 6 completes onboarding, a caption points to the **Scrape** page in the sidebar.

Technical defaults (Outscraper batch, SIRENE, target 5 000) come from [`configs/_bases/common.py`](configs/_bases/common.py).

### Scrape page (always accessible)

- Own preset dropdown — lists only presets with **completed onboarding** (tabs 1–6)
- If no preset is ready, the page stays open with an info message
- **Contrôles** bar at top: **Démarrer / Continuer**, **Pause**, **Actualiser** (worker start/stop via SSH/systemd or local)
- Live metrics panel auto-refreshes every 5s
- Read-only config summary (collapsed by default)
- **Push CSV to Instantly** and **Wipe local** in secondary sections

## CLI

```bash
python -m bootstrap list
python -m bootstrap validate
python -m bootstrap validate my_preset --dry-run
python -m bootstrap cleanup-empty-instantly          # dry-run: delete 0-lead lists/campaigns
python -m bootstrap cleanup-empty-instantly --execute
python main.py dry-run --preset <id>
python main.py scrape --preset <id> --target 5000 --push-instantly --resume
python main.py worker-loop --preset <id> --push-instantly   # loop until target progress ≥ TARGET_LEADS
python main.py heal --preset <id>                           # cron watchdog (resume if stale)
python main.py audit-filter --preset cabinets_expertise_comptable_fresh_geo   # analyze filter_audit.csv
python main.py sirene-build --check
```

`cleanup-empty-instantly` scans the **whole Instantly workspace** for lists/campaigns with 0 leads. Review dry-run output before `--execute`.

## Pipeline

1. **Scrape (Outscraper)** — email + website gates, dedup; optional **taxonomy gate** (`type` / `category` / `subtypes`); empty batches retry up to 3×
2. **Enrich** — website keyword include/exclude (skipped when `ENRICH_ENABLED=false`)
3. **SIRET / effectif** — `company_registry` (skipped when `PAPPERS_ENABLED=false`)
4. **Push (Instantly)** — target `TARGET_LEADS` (default 5 000)

Pass 2+ geo uses [`query_planner.py`](query_planner.py) (skip/limit per slot, SDK batching).

**TARGET_MODE** (see [`scrape_state.py`](scrape_state.py)):

| Mode | Progress / worker stop |
|------|------------------------|
| `csv_saved` | Rows in `outscraper_leads.csv` |
| `mev_emails.csv` | Single-column MEV upload file (auto-regenerated; header `email`) |
| `instantly_pushed` | **Instantly live** list count (API) for worker progress and `is_target_reached` |
| `instantly_pushed_run` | **Checkpoint** `instantly_pushed` in `scrape_state.json` — pipe vol (shared list) |

Checkpoint `instantly_pushed` = pushes credited to **this preset run** only.

For `instantly_pushed`, the worker and pipeline completion both use **live-first** semantics: `target_progress_value` prefers the live list count when the API responds. The checkpoint can exceed `TARGET_LEADS` (e.g. partial pushes before Instantly 429 defer, list purges) without stopping Outscraper; the run completes only when **live ≥ target** (or checkpoint ≥ target if live is unavailable).

### Pipeline comptable (VPS)

Single worker — postal + INSEE communes, taxonomy gate on Outscraper `type` / `category` / `subtypes`:

| systemd unit | Preset | Target |
|--------------|--------|--------|
| `hercule-scraper-comptable-fresh-geo` | `cabinets_expertise_comptable_fresh_geo` | `instantly_pushed_run` (10K checkpoint) |

List Instantly : `bfb0fc90-ec59-4d49-b266-3891f59d3ea8`. Tuning recommandé dans l'unité systemd : `OUTSCRAPER_CONCURRENCY=16`, `OUTSCRAPER_POLL_INITIAL_S=10`.

```bash
sudo VPS_SCRAPER_SERVICE=hercule-scraper-comptable-fresh-geo \
     SCRAPER_PRESET=cabinets_expertise_comptable_fresh_geo \
     bash lib/backend/scripts/vps/install-scraper.sh
sudo systemctl start hercule-scraper-comptable-fresh-geo
```

### Courtiers prévoyance B2B (VPS)

| systemd unit | Preset | Filtering | Target |
|--------------|--------|-----------|--------|
| `hercule-scraper-prevoyance` | `courtiers_prevoyance_b2b` | Taxonomy anti-retail / réseaux | `instantly_pushed` (10K live list) |

```bash
sudo VPS_SCRAPER_SERVICE=hercule-scraper-prevoyance \
     SCRAPER_PRESET=courtiers_prevoyance_b2b \
     bash lib/backend/scripts/vps/install-scraper.sh
sudo systemctl start hercule-scraper-prevoyance
```

Output is isolated per preset under `$HERCULE_DATA_ROOT/streamlit_scraper/output/{preset_id}/`. Heal cron is per-preset (`heal-{preset}.log`).

#### Funnel comptable — taux d'acceptation et taxonomy

Audit reproductible :

```bash
python main.py audit-filter --preset cabinets_expertise_comptable_fresh_geo
```

Rejet typique : `duplicate company (domain) or email` quand la geo est saturée → relancer un reload geo ou avancer de pass. Revue manuelle : [`docs/taxonomy_review_manual.md`](docs/taxonomy_review_manual.md).

## Resume / checkpoint

- `output/{preset}/scrape_state.json` — batch checkpoint
- `output/{preset}/scrape.log` — persistent worker log
- `output/{preset}/worker_heartbeat.json` — worker liveness (stale → heal)
- `incomplete` runs are **resumable** — use Continue / worker-loop
- Resume blocked only if config fingerprint changed (wipe local first)

## VPS worker

On the VPS (once repo is deployed):

```bash
export SCRAPER_PRESET=cabinets_expertise_comptable
export HERCULE_DATA_ROOT=/var/lib/hercule
sudo bash lib/backend/scripts/vps/install-scraper.sh
sudo systemctl start hercule-scraper
```

From your Mac: open sidebar **Scrape** → **Continue / Start worker**. Progress uses Instantly live count and won't reset to 0 on rerun.

Helper scripts: [`lib/backend/scripts/vps/install-scraper.sh`](../../scripts/vps/install-scraper.sh), `heal-scraper.sh`, `run-worker-loop.sh`.

## Monitoring (Grafana fleet dashboard)

Read-only observability for all scrapers on the VPS — **no control**, replaces SSH polling for the multi-scraper view. Streamlit Scrape page stays for start/stop.

### Stack

| Component | Role | Port (localhost) |
|-----------|------|------------------|
| `hercule-scraper-exporter` (systemd) | Reads `worker_heartbeat.json` + `scrape_state.json` → Prometheus metrics | `:9464` |
| Prometheus | Time series (15d retention) | `:9090` |
| Grafana | Dashboards | `:3000` |
| Loki + Promtail | Tail `scrape.log` per preset | `:3100` |
| node_exporter | CPU / RAM / disk | `:9100` |

Code: [`monitoring/exporter.py`](monitoring/exporter.py) · Compose: [`lib/backend/scripts/vps/monitoring/`](../../scripts/vps/monitoring/)

### Install (on VPS)

Requires Docker Engine + Compose plugin.

```bash
export HERCULE_DATA_ROOT=/var/lib/hercule
export VPS_REPO_ROOT=/root/hercule.dev   # if different
sudo bash lib/backend/scripts/vps/install-monitoring.sh
```

This installs/enables `hercule-scraper-exporter`, generates a Grafana admin password at `/root/.hercule/grafana-admin-password`, and starts the Compose stack (bound to `127.0.0.1` only).

### Access from your Mac

```bash
ssh -L 3000:127.0.0.1:3000 $VPS_USER@$VPS_HOST
# password: ssh $VPS_USER@$VPS_HOST 'cat /root/.hercule/grafana-admin-password'
open http://127.0.0.1:3000
```

Login: `admin` / password from the file above. Dashboard: **Hercule → Hercule Scraper Fleet**.

### Metrics exposed

```
scraper_heartbeat_age_seconds{preset}
scraper_worker_up{preset}                 # 1 if heartbeat age < 15 min
scraper_status_info{preset,status}        # running|stalled|idle|complete|blocked
scraper_target_leads / scraper_progress_leads / scraper_progress_ratio
scraper_leads_saved / scraper_leads_enriched_* / scraper_instantly_pushed
scraper_inflight_tasks / scraper_batch_* / scraper_query_pass
scraper_systemd_active{service}
```

Progress uses checkpoint fields only (no Instantly live API) — same as `TARGET_MODE=instantly_pushed_run` semantics for shared lists.

### Troubleshooting

| Symptom | Check |
|---------|--------|
| Empty fleet table | `curl -s localhost:9464/metrics \| grep scraper_` — exporter up? presets under `$HERCULE_DATA_ROOT/streamlit_scraper/output/`? |
| Exporter down | `journalctl -u hercule-scraper-exporter -n 50` · `systemctl restart hercule-scraper-exporter` |
| No logs in Grafana | Promtail mounts data root — confirm `HERCULE_DATA_ROOT` matches install · `docker logs hercule-promtail` |
| Disk gauge red | node_exporter — free space under `/` or `/var/lib/hercule` |
| Restart stack | `cd lib/backend/scripts/vps/monitoring && HERCULE_DATA_ROOT=… GRAFANA_ADMIN_PASSWORD=$(cat /root/.hercule/grafana-admin-password) docker compose up -d` |

Local smoke test (no Docker):

```bash
cd lib/backend/streamlit_scraper
python -m monitoring.exporter --once --data-root /var/lib/hercule
```

## Output per preset

`output/{preset_id}/` — CSVs, audits, `scrape_state.json`, `scrape.log`, `worker_heartbeat.json`, `cron_events.jsonl`, `onboarding_state.json`

## Legacy

Older group-based presets and Typer `bootstrap create` wizard were removed. Use the Streamlit tabs for all new presets.
