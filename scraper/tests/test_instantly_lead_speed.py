"""Tests for Instantly lead speed CLI helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "scraper"
    / "instantly_lead_speed.py"
)
_spec = importlib.util.spec_from_file_location("instantly_lead_speed", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

format_speed_line = _mod.format_speed_line
sample_instantly_speed = _mod.sample_instantly_speed


def test_format_speed_line() -> None:
    line = format_speed_line(
        per_hour=42.7,
        per_day=42.7 * 24,
        end_count=1336,
        delta=14,
        sample_minutes=5.0,
    )
    assert line == (
        "Speed count: 43 leads/hour on Instantly | 1025 leads/day "
        "(list: 1336, +14 in 5 min)"
    )


def test_per_day_is_per_hour_times_24() -> None:
    line = format_speed_line(
        per_hour=100.0,
        per_day=100.0 * 24.0,
        end_count=500,
        delta=10,
        sample_minutes=6.0,
    )
    assert "2400 leads/day" in line
    assert "100 leads/hour" in line


def test_sample_instantly_speed_with_mock(monkeypatch) -> None:
    poll_values = [1000, 1050]

    def fake_fetch(_config: dict, *, use_cache: bool = True) -> int | None:
        if poll_values:
            return poll_values.pop(0)
        return 1050

    monkeypatch.setattr(_mod, "fetch_instantly_live", fake_fetch)
    monkeypatch.setattr(_mod.time, "sleep", lambda _s: None)

    clock = iter([0.0, 3600.0])
    monkeypatch.setattr(_mod.time, "monotonic", lambda: next(clock))

    result = sample_instantly_speed(
        {"PRESET_ID": "test", "INSTANTLY_LIST_ID": "list-1"},
        sample_minutes=1.0,
        poll_seconds=30.0,
    )
    assert result["live_start"] == 1000
    assert result["live_end"] == 1050
    assert result["delta"] == 50
    assert result["per_hour"] == 50.0
    assert result["per_day"] == 1200.0
