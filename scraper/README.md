# Scraper UI (Streamlit)

Lightweight dashboard to **read scrape history** (VPS SSH + optional n8n API) and **trigger scrapes** via n8n webhook. Pipeline execution lives on the VPS / n8n — not in this repo.

## Run locally

```bash
cd scraper && streamlit run app.py
```

Or from repo root: `make dev-scraper`

## Presets

Niche settings are in `presets.yaml` (migrated from the former `configs/*_config.py` modules). The UI loads `TARGET_LEADS`, `TARGET_MODE`, and Instantly IDs for display and launch guards.

## Environment

| Variable | Purpose |
|----------|---------|
| `VPS_HOST`, `VPS_USER` | SSH read of `scrape_state.json`, `scrape.log`, heartbeat under `HERCULE_DATA_ROOT` |
| `VPS_SSH_PASSWORD` or `VPS_SSH_KEY` | SSH authentication |
| `HERCULE_DATA_ROOT` | Remote data root (default on VPS: `/var/lib/hercule`) |
| `VPS_SCRAPER_SERVICE` | systemd unit name for optional **stop worker** (default `hercule-scraper`) |
| `N8N_SCRAPE_WEBHOOK_URL` | **POST** `{ "keyword", "instantly_list_id", "target_leads", "preset_id?" }` → n8n writes `/var/lib/hercule/scraper-env/<preset>.env` on VPS, reloads systemd drop-in, runs `main.py heal --preset <id>` (default preset: `SCRAPE_DEFAULT_PRESET` / `N8N_DEFAULT_PRESET` / `_adhoc`) |
| `N8N_BASE_URL`, `N8N_API_KEY` | Optional read-only execution history |
| `INSTANTLY_API_KEY` | Injected into preset config for UI checks |
| `INSTANTLY_LIST_ID_<PRESET>` | Per-preset list override (see `config_loader.py`) |

See repo `.env.example` for a full template.

## Data paths

Per preset: `$HERCULE_DATA_ROOT/streamlit_scraper/output/{preset_id}/` — `scrape_state.json`, `scrape.log`, `worker_heartbeat.json`, `cron_events.jsonl`, CSV exports (written by the remote worker).
