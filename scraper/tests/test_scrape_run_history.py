"""Tests for scrape run history parsing."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from bootstrap.scrape_run_history import (  # noqa: E402
    detect_scrape_running,
    parse_worker_runs_from_log,
)


def test_parse_worker_runs_completed() -> None:
    log = """
[2026-01-01 10:00:00 UTC] Worker loop start — preset=foo, target=5000, mode=instantly_pushed
[2026-01-01 12:00:00 UTC] Target reached — progress 5000/5000 (instantly_pushed).
[2026-01-02 08:00:00 UTC] Worker loop start — preset=foo, target=5000, mode=csv_saved
""".strip()
    runs = parse_worker_runs_from_log(log)
    assert len(runs) == 2
    assert runs[0]["status"] == "running"
    assert runs[0]["preset"] == "foo"
    assert runs[1]["status"] == "completed"


def test_detect_running_vps_heartbeat() -> None:
    running, code, _ = detect_scrape_running(
        "foo",
        state={"status": "running", "preset": "foo"},
        heartbeat={"preset": "foo", "status": "running", "last_seen": "2099-01-01T00:00:00+00:00"},
        vps={"active": True},
    )
    assert running is True
    assert code == "running"
