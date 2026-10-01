# Streamlit Clean

## AI agents

Before editing this app, read:
1. [`.cursor/skills/hercule-streamlit/SKILL.md`](../../../.cursor/skills/hercule-streamlit/SKILL.md) (router)
2. [`.cursor/skills/hercule-streamlit-clean/SKILL.md`](../../../.cursor/skills/hercule-streamlit-clean/SKILL.md) (this app)

Human reference: sections below.

MyEmailVerifier email list cleaner → Instantly campaign push.

## Quick start

```bash
bun run streamlit-clean
# or:
cd lib/backend/streamlit_clean && pip install -r requirements.txt && streamlit run app.py
```

### Headless CLI (Render / cron)

```bash
export PYTHONPATH=/path/to/repo
cd lib/backend/streamlit_clean
python cli.py credits
python cli.py export-mev --list-id <uuid> -o mev_emails.csv
python cli.py audit-list --list-id <uuid>
python cli.py run --list-id <uuid> --campaign-id <uuid> --mode test_50
python cli.py checkpoints
```

See [doc/render-outreach.md](../../doc/render-outreach.md) for Render deployment.

## Environment

Requires in repo root `.env`:

| Variable | Purpose |
|----------|---------|
| `MYEMAILVERIFIER_API_KEY` | Bulk email verification |
| `INSTANTLY_API_KEY` | List fetch, purge, campaign push |

## Pipeline

1. Select source Instantly list
2. Select target campaign
3. Choose run mode (dry / test-50 / full / custom)
4. Execute: quick pre-filter → MyEmailVerifier → optional list purge → push valid leads
5. Review results; workspace duplicate check always on during push

## MyEmailVerifier CSV format

MyEmailVerifier reads the **first column** of uploaded files. Use a single-column CSV:

```csv
email
user@example.com
```

- **Do not** upload Instantly UI exports (first column is `id`, not email).
- Use **Download for MEV** in step 1, or `python cli.py export-mev --list-id <uuid>`.
- The pipeline builds `{prefix}_mev_upload_0.csv` automatically during verification.

## Checkpoint recovery

Interrupted runs can resume via checkpoint UI. See `checkpoint.py` and `recover_checkpoint.py`.
