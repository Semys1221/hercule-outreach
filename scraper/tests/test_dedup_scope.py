"""Tests for scrape vs push Instantly dedup scope."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from config_loader import load_config  # noqa: E402
from core_logic import (  # noqa: E402
    scrape_dedup_campaign_ids,
    scrape_dedup_list_ids,
    scrape_dedup_scope,
)


def test_vol_config_list_only_dedup() -> None:
    config = load_config("cabinets_expertise_comptable_fresh_geo", require_keys=False)
    assert scrape_dedup_scope(config) == "list_only"
    assert scrape_dedup_list_ids(config)
    assert scrape_dedup_campaign_ids(config) == []
    assert config.get("INSTANTLY_SKIP_IF_IN_CAMPAIGN") is True


def test_list_and_campaign_scope_includes_campaign_ids() -> None:
    config = {
        "SCRAPE_DEDUP_SCOPE": "list_and_campaign",
        "INSTANTLY_DEDUP_LIST_IDS": ["list-a"],
        "INSTANTLY_DEDUP_CAMPAIGN_IDS": ["camp-b"],
    }
    assert scrape_dedup_list_ids(config) == ["list-a"]
    assert scrape_dedup_campaign_ids(config) == ["camp-b"]


def test_csv_only_scope_skips_instantly_ids() -> None:
    config = {
        "SCRAPE_DEDUP_SCOPE": "csv_only",
        "INSTANTLY_DEDUP_LIST_IDS": ["list-a"],
        "INSTANTLY_DEDUP_CAMPAIGN_IDS": ["camp-b"],
    }
    assert scrape_dedup_list_ids(config) == []
    assert scrape_dedup_campaign_ids(config) == []
