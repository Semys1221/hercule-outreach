"""Tests for scraper fleet Prometheus exporter (disk snapshot logic)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from monitoring.exporter import (  # noqa: E402
    HEARTBEAT_STALE_S,
    collect_fleet,
    collect_preset_snapshot,
    derive_worker_status,
    discover_presets,
    resolve_output_base,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_output_base_with_data_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HERCULE_DATA_ROOT", raising=False)
    base = resolve_output_base(str(tmp_path))
    assert base == tmp_path / "streamlit_scraper" / "output"


def test_discover_presets_skips_empty_dirs(tmp_path: Path) -> None:
    output = tmp_path / "output"
    (output / "empty").mkdir(parents=True)
    _write_json(
        output / "medecins" / "worker_heartbeat.json",
        {"preset": "medecins", "status": "running", "last_seen": "2026-01-01T00:00:00+00:00"},
    )
    assert discover_presets(output) == ["medecins"]


def test_derive_worker_status_running_stalled_idle() -> None:
    now = datetime.now(timezone.utc)
    fresh = {"status": "running", "last_seen": now.isoformat()}
    stale = {
        "status": "running",
        "last_seen": (now - timedelta(seconds=HEARTBEAT_STALE_S + 10)).isoformat(),
    }
    assert derive_worker_status(fresh, {"status": "running"})[0] == "running"
    assert derive_worker_status(fresh, {"status": "running"})[2] is True
    assert derive_worker_status(stale, {"status": "running"})[0] == "stalled"
    assert derive_worker_status(None, None)[0] == "idle"
    assert derive_worker_status(
        {"status": "complete", "last_seen": now.isoformat()},
        {"status": "completed"},
    )[0] == "complete"
    assert derive_worker_status(
        {"status": "blocked", "last_seen": now.isoformat()},
        {},
    )[0] == "blocked"


def test_collect_preset_snapshot_progress_modes(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    out = tmp_path / "cabinets_vol"
    _write_json(
        out / "worker_heartbeat.json",
        {"preset": "cabinets_vol", "status": "running", "last_seen": now.isoformat()},
    )
    _write_json(
        out / "scrape_state.json",
        {
            "status": "running",
            "target": 10000,
            "target_mode": "instantly_pushed_run",
            "leads_saved": 500,
            "leads_enriched_valid": 400,
            "leads_enriched_rejected": 50,
            "instantly_pushed": 300,
            "inflight_tasks": ["a", "b"],
            "last_completed_batch_index": 4,
            "batches_total": 40,
            "query_pass": 1,
            "last_updated": now.isoformat(),
        },
    )
    snap = collect_preset_snapshot("cabinets_vol", out)
    assert snap.status == "running"
    assert snap.worker_up is True
    assert snap.progress_leads == 300
    assert snap.progress_ratio == 0.03
    assert snap.leads_saved == 500
    assert snap.inflight_tasks == 2
    assert snap.batch_completed == 5
    assert snap.batches_total == 40
    assert snap.query_pass == 1
    assert snap.state_last_updated_ts is not None


def test_collect_preset_snapshot_csv_mode(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    out = tmp_path / "csv_preset"
    _write_json(
        out / "worker_heartbeat.json",
        {"preset": "csv_preset", "status": "running", "last_seen": now.isoformat()},
    )
    _write_json(
        out / "scrape_state.json",
        {
            "status": "running",
            "target": 100,
            "target_mode": "csv_saved",
            "leads_saved": 40,
            "instantly_pushed": 0,
            "last_updated": now.isoformat(),
        },
    )
    snap = collect_preset_snapshot("csv_preset", out)
    assert snap.progress_leads == 40
    assert snap.progress_ratio == 0.4


def test_collect_fleet(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    for name in ("a", "b"):
        out = tmp_path / name
        _write_json(
            out / "worker_heartbeat.json",
            {"preset": name, "status": "running", "last_seen": now.isoformat()},
        )
        _write_json(
            out / "scrape_state.json",
            {
                "status": "running",
                "target": 10,
                "target_mode": "csv_saved",
                "leads_saved": 1,
                "last_updated": now.isoformat(),
            },
        )
    snaps = collect_fleet(tmp_path)
    assert [s.preset for s in snaps] == ["a", "b"]
