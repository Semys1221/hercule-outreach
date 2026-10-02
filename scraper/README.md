# Streamlit Scraper

Repo layout: [`scraper/`](.) (this app), [`clean/`](../clean), [`shared/`](../shared), [`satellites/`](../satellites) (prompts / subsequence helpers only).

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

From repo root (see [`Makefile`](../Makefile)):

```bash
make venv
make dev-scraper
```

Or manually:

```bash
cd scraper
pip install -r requirements.txt
streamlit run app.py
```

Required in repo root [`.env`](../.env) (copy from [`.env.example`](../.env.example)):

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
| `N8N_BASE_URL` / `N8N_API_KEY` | Optional read-only n8n execution list on Scrape page |
| `N8N_VIA_VPS` | When `1` (default), call n8n on the VPS via SSH if `N8N_BASE_URL` is unset |
| `N8N_VPS_LOCAL_URL` | Override VPS-local n8n URL for SSH curl (default `http://127.0.0.1:5678`) |

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
- **État & historique** — scrape en cours, table depuis `scrape_state.json`, `scrape.log`, `cron_events.jsonl` (VPS SSH)
- **Contrôles VPS** — démarrer / arrêter le worker systemd (pas de worker local)
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

Long-running presets (e.g. `cabinets_expertise_comptable_fresh_geo`, `courtiers_prevoyance_b2b`) are usually driven with `python main.py worker-loop` on a host where `$HERCULE_DATA_ROOT` is set. Output is isolated per preset under `$HERCULE_DATA_ROOT/streamlit_scraper/output/{preset_id}/` (or `scraper/output/` under the repo when running locally).

#### Funnel comptable — taux d'acceptation et taxonomy

Audit reproductible :

```bash
python main.py audit-filter --preset cabinets_expertise_comptable_fresh_geo
```

Rejet typique : `duplicate company (domain) or email` quand la geo est saturée → relancer un reload geo ou avancer de pass. Inspect `filter_audit.csv` under the preset output dir for taxonomy rejects.

## Resume / checkpoint

- `output/{preset}/scrape_state.json` — batch checkpoint
- `output/{preset}/scrape.log` — persistent worker log
- `output/{preset}/worker_heartbeat.json` — worker liveness (stale → heal)
- `incomplete` runs are **resumable** — use Continue / worker-loop
- Resume blocked only if config fingerprint changed (wipe local first)

## VPS worker (optional)

When `VPS_HOST` / `VPS_USER` are set, the Streamlit **Scrape** page can start or stop a remote worker over SSH (see `.env.example`). Deploy the repo on the host, set `SCRAPER_PRESET` and `HERCULE_DATA_ROOT`, then run `python main.py worker-loop` (or your own systemd unit). Progress uses Instantly live count when configured and won't reset to 0 on rerun.

## Metrics exporter

[`monitoring/exporter.py`](monitoring/exporter.py) exposes Prometheus metrics from `worker_heartbeat.json` and `scrape_state.json`. Local smoke test:

```bash
cd scraper
python -m monitoring.exporter --once --data-root /var/lib/hercule
```

## Output per preset

`output/{preset_id}/` — CSVs, audits, `scrape_state.json`, `scrape.log`, `worker_heartbeat.json`, `cron_events.jsonl`, `onboarding_state.json`

## Legacy

Older group-based presets and Typer `bootstrap create` wizard were removed. Use the Streamlit tabs for all new presets.
