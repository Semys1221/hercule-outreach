"""Tests for verify_vps_helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from verify_vps_helpers import (  # noqa: E402
    classify_speed,
    classify_worker_health,
    compute_rate_per_hour,
    counts_consistent,
    outscraper_probe_status,
)


def test_classify_worker_health_active_fresh() -> None:
    assert (
        classify_worker_health(
            systemd_active=True,
            heartbeat_age_s=30.0,
            heartbeat_status="running",
        )
        == "PASS"
    )


def test_classify_worker_health_blocked_no_progress() -> None:
    assert (
        classify_worker_health(
            systemd_active=True,
            heartbeat_age_s=10.0,
            heartbeat_status="blocked",
            progress_delta=0,
        )
        == "FAIL"
    )


def test_classify_worker_health_blocked_with_progress_warns() -> None:
    assert (
        classify_worker_health(
            systemd_active=True,
            heartbeat_age_s=10.0,
            heartbeat_status="blocked",
            progress_delta=5,
        )
        == "WARN"
    )


def test_classify_worker_health_stale() -> None:
    assert (
        classify_worker_health(
            systemd_active=True,
            heartbeat_age_s=200.0,
            heartbeat_status="running",
        )
        == "FAIL"
    )


def test_counts_consistent_ok() -> None:
    assert (
        counts_consistent(
            leads_saved=100,
            remote_csv=100,
            instantly_pushed=50,
            instantly_live=200,
        )
        == "PASS"
    )


def test_counts_consistent_checkpoint_above_live_warns_for_run_mode() -> None:
    assert (
        counts_consistent(
            leads_saved=100,
            remote_csv=100,
            instantly_pushed=500,
            instantly_live=100,
            target_mode="instantly_pushed_run",
        )
        == "WARN"
    )
    assert (
        counts_consistent(
            leads_saved=100,
            remote_csv=90,
            instantly_pushed=50,
            instantly_live=200,
        )
        == "FAIL"
    )


def test_compute_rate_per_hour() -> None:
    assert compute_rate_per_hour(30, 3600.0) == 30.0
    assert compute_rate_per_hour(15, 1800.0) == 30.0


def test_classify_speed_pass() -> None:
    assert (
        classify_speed(
            40.0,
            min_live_per_hour=30.0,
            sample_minutes=15.0,
            any_systemd_active=True,
            outscraper_healthy=True,
        )
        == "PASS"
    )


def test_classify_speed_skip_when_no_sample() -> None:
    assert (
        classify_speed(
            None,
            sample_minutes=0.0,
            any_systemd_active=True,
            outscraper_healthy=True,
        )
        == "SKIP"
    )


def test_outscraper_probe_status() -> None:
    assert outscraper_probe_status(402) == "FAIL"
    assert outscraper_probe_status(200) == "PASS"
    assert outscraper_probe_status(None, "timeout") == "WARN"
