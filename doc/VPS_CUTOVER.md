# VPS cutover (monorepo → hercule-outreach)

Data under `HERCULE_DATA_ROOT` (e.g. `/var/lib/hercule/streamlit_scraper/output/`) is unchanged.

1. Clone on VPS: `git clone <repo-url> /root/hercule-outreach`
2. `cd /root/hercule-outreach && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
3. Copy `.env` from old checkout or sync secrets (`OUTSCRAPER_API_KEY`, `INSTANTLY_API_KEY`, Supabase, `CRM_BACKEND_URL`, etc.)
4. Reinstall systemd (per preset):

```bash
cd /root/hercule-outreach
sudo VPS_REPO_ROOT=/root/hercule-outreach SCRAPER_PRESET=<preset> VPS_SCRAPER_SERVICE=<unit> bash scripts/vps/install-scraper.sh
sudo systemctl restart <unit>
```

5. Update operator laptop `.env`: `VPS_REPO_ROOT=/root/hercule-outreach`
6. Optional monitoring: `sudo bash scripts/vps/install-monitoring.sh`

Verify: `python scripts/scraper/verifyScraperVps.py` (from repo root with `PYTHONPATH` set).
