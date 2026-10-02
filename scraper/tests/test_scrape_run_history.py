"""Tests for scrape run history parsing."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from bootstrap.n8n_read import (  # noqa: E402
    execution_to_run_row,
    niche_from_n8n_execution,
    n8n_execution_matches_preset,
)
from bootstrap.scrape_run_history import (  # noqa: E402
    detect_scrape_running,
    duration_hours,
    history_to_dataframe_rows,
    leads_per_hour_label,
    merge_n8n_into_history,
    parse_worker_runs_from_log,
)


def test_parse_worker_runs_completed() -> None:
    log = """
[2026-01-01 10:00:00 UTC] Worker loop start — preset=foo, target=5000, mode=instantly_pushed
[2026-01-01 11:00:00 UTC] Batch 1 processed. Scraped: 1200 | Enriched: 900 | Instantly: 800/5000
[2026-01-01 12:00:00 UTC] Target reached — progress 5000/5000 (instantly_pushed).
[2026-01-02 08:00:00 UTC] Worker loop start — preset=foo, target=5000, mode=csv_saved
""".strip()
    runs = parse_worker_runs_from_log(log)
    assert len(runs) == 2
    assert runs[0]["status"] == "running"
    assert runs[0]["preset"] == "foo"
    assert runs[1]["status"] == "completed"
    assert runs[1]["leads_saved"] == 1200
    assert runs[1]["instantly_pushed"] == 800


def test_detect_running_vps_heartbeat() -> None:
    running, code, _ = detect_scrape_running(
        "foo",
        state={"status": "running", "preset": "foo"},
        heartbeat={"preset": "foo", "status": "running", "last_seen": "2099-01-01T00:00:00+00:00"},
        vps={"active": True},
    )
    assert running is True
    assert code == "running"


def test_history_to_dataframe_rows_columns_and_rate() -> None:
    rows = history_to_dataframe_rows(
        [
            {
                "source": "checkpoint",
                "preset": "medecins",
                "started_at": "2026-01-01T10:00:00+00:00",
                "ended_at": "2026-01-01T12:00:00+00:00",
                "leads_saved": 1000,
                "instantly_pushed": 900,
            }
        ]
    )
    assert list(rows[0].keys()) == [
        "Niche",
        "Début",
        "Fin",
        "Scrapés",
        "Poussés Instantly",
        "Débit /h",
    ]
    assert rows[0]["Niche"] == "medecins"
    assert rows[0]["Scrapés"] == "1 000"
    assert rows[0]["Poussés Instantly"] == "900"
    assert rows[0]["Débit /h"] == "500/h"


def test_duration_and_rate_helpers() -> None:
    assert duration_hours("2026-01-01T10:00:00+00:00", "2026-01-01T11:00:00+00:00") == 1.0
    assert duration_hours("2026-01-01T11:00:00+00:00", "2026-01-01T10:00:00+00:00") is None
    assert leads_per_hour_label(120, "2026-01-01T10:00:00+00:00", "2026-01-01T11:30:00+00:00") == "80/h"


def test_n8n_execution_niche_and_merge() -> None:
    execution = {
        "startedAt": "2026-03-01T08:00:00.000Z",
        "stoppedAt": "2026-03-01T09:00:00.000Z",
        "status": "success",
        "workflowData": {"name": "Hercule scrape chirurgiens_dentistes"},
        "customData": {"leads_saved": 42, "instantly_pushed": 40},
    }
    assert niche_from_n8n_execution(execution) == "chirurgiens_dentistes"
    assert n8n_execution_matches_preset(execution, "chirurgiens_dentistes")
    row = execution_to_run_row(execution)
    assert row["leads_saved"] == 42
    assert row["instantly_pushed"] == 40
    merged = merge_n8n_into_history([], [execution], preset_id="chirurgiens_dentistes")
    assert len(merged) == 1
    assert merged[0]["source"] == "n8n"
