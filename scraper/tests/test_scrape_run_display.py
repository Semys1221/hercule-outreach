"""Tests for scrape run context merge (Suivi en cours banner)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRAPER_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_ROOT))

from bootstrap.ui_helpers import merge_scrape_run_display  # noqa: E402


def test_merge_prefers_session_over_empty_state() -> None:
    display = merge_scrape_run_display(
        "_adhoc",
        state={"leads_saved": 10},
        config=None,
        session_ctx={
            "preset_id": "_adhoc",
            "keyword": "dentiste Paris",
            "instantly_list_id": "abc-123",
            "instantly_list_name": "Ma liste",
            "target_leads": 2000,
        },
    )
    assert display["keyword"] == "dentiste Paris"
    assert display["instantly_list_id"] == "abc-123"
    assert display["instantly_list_name"] == "Ma liste"
    assert display["target_leads"] == 2000


def test_merge_state_metadata_when_session_missing_fields() -> None:
    display = merge_scrape_run_display(
        "_adhoc",
        state={
            "keyword": "from-vps",
            "instantly_list_id": "list-vps",
            "target_leads": 1500,
        },
        config=None,
        session_ctx={},
    )
    assert display["keyword"] == "from-vps"
    assert display["instantly_list_id"] == "list-vps"
    assert display["target_leads"] == 1500


def test_merge_ignores_session_for_other_preset() -> None:
    display = merge_scrape_run_display(
        "avocats",
        state={"keyword": "vps-only"},
        config=None,
        session_ctx={
            "preset_id": "_adhoc",
            "keyword": "adhoc-session",
            "instantly_list_id": "x",
            "target_leads": 100,
        },
    )
    assert display["keyword"] == "vps-only"
    assert display["instantly_list_id"] == ""
