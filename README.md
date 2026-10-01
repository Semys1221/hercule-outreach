# hercule-outreach

Standalone operator tools for **Outscraper lead scraping** and **MyEmailVerifier list cleaning**. Separate git repo from the Hercule Next.js app; only HTTP integration is `CRM_BACKEND_URL` (link provision on hercule.dev).

## Stack

- Python 3.11+
- Streamlit (two apps)
- One venv, one `requirements.txt`, root `.env`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill keys
```

## Run locally

```bash
make dev-scraper   # port 8501 by default
make dev-clean     # second terminal if needed
```

Or:

```bash
export PYTHONPATH="$PWD:$PWD/scraper:$PWD/clean"
cd scraper && python main.py ui
cd clean && streamlit run app.py
```

## VPS worker

Persistent scrape state stays under `HERCULE_DATA_ROOT` (default `/var/lib/hercule/streamlit_scraper/output/…`).

```bash
sudo SCRAPER_PRESET=your_preset bash scripts/vps/install-scraper.sh
sudo systemctl start hercule-scraper
```

Set `VPS_REPO_ROOT` to this repo path on the server (default: directory containing `scripts/vps/install-scraper.sh`).

## Tests

```bash
make test
```

## Layout

| Path | Role |
|------|------|
| `scraper/` | Outscraper pipeline, onboarding, worker CLI |
| `clean/` | MEV verification funnel |
| `shared/` | Instantly client, MEV CSV, link provision client |
| `satellites/` | Subsequence + reply-agent modules for scraper onboarding |
| `scripts/` | VPS install + maintenance scripts |
