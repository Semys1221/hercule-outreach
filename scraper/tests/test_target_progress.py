"""Tests for TARGET_MODE progress and target-reached logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import _is_target_reached  # noqa: E402
from scrape_state import is_target_reached, target_progress_value  # noqa: E402


def test_instantly_pushed_uses_live_list_for_target():
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    with patch("scrape_metrics.fetch_instantly_live", return_value=5000):
        assert not _is_target_reached(
            target=10000,
            target_mode="instantly_pushed",
            leads_saved=0,
            instantly_pushed=10,
            config=config,
        )


def test_instantly_pushed_checkpoint_ahead_of_live_continues_scrape():
    """Worker progress uses live list; checkpoint can exceed target after 429 defer."""
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    with patch("scrape_metrics.fetch_instantly_live", return_value=3500):
        assert not is_target_reached(
            target=4000,
            mode="instantly_pushed",
            leads_saved=5635,
            instantly_pushed=4211,
            config=config,
        )
        assert not _is_target_reached(
            target=4000,
            target_mode="instantly_pushed",
            leads_saved=5635,
            instantly_pushed=4211,
            config=config,
        )


def test_is_target_reached_live_completes_when_list_at_goal():
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    assert is_target_reached(
        target=4000,
        mode="instantly_pushed",
        leads_saved=0,
        instantly_pushed=4211,
        config=config,
        instantly_live=4000,
    )


def test_instantly_pushed_run_ignores_live_list():
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    with patch("scrape_metrics.fetch_instantly_live", return_value=5000):
        assert _is_target_reached(
            target=10000,
            target_mode="instantly_pushed_run",
            leads_saved=0,
            instantly_pushed=10000,
            config=config,
        )


def test_instantly_pushed_run_under_checkpoint_target():
    assert not _is_target_reached(
        target=100,
        target_mode="instantly_pushed_run",
        leads_saved=500,
        instantly_pushed=99,
        config={},
    )


def test_target_progress_value_modes():
    assert target_progress_value(
        "instantly_pushed",
        instantly_pushed=10,
        instantly_live=5000,
    ) == 5000
    assert target_progress_value(
        "instantly_pushed_run",
        instantly_pushed=42,
        instantly_live=5000,
    ) == 42
    assert target_progress_value("csv_saved", leads_saved=7) == 7
