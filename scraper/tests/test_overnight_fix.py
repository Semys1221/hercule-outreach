"""Tests for resume fingerprint and target-reached throttling."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import _is_target_reached, build_queries  # noqa: E402
from scrape_state import (  # noqa: E402
    build_config_fingerprint,
    build_config_identity_fingerprint,
    build_config_legacy_fingerprint,
    config_fingerprint_compatible,
)


def test_fingerprint_legacy_compatible_after_tuning_change() -> None:
    base = {
        "KEYWORDS": ["expert comptable"],
        "EXPANSION_KEYWORDS": [],
        "LOCATIONS": ["Paris"],
        "EXPANSION_LOCATIONS": [],
        "EXCLUDE_DOMAINS": [],
        "ENRICH_ENABLED": True,
        "TARGET_MODE": "instantly_pushed",
        "OUTSCRAPER_BATCH_SIZE": 200,
        "OUTSCRAPER_CONCURRENCY": 15,
    }
    legacy = build_config_legacy_fingerprint(base)
    tuned = {**base, "OUTSCRAPER_CONCURRENCY": 8}
    assert config_fingerprint_compatible(legacy, tuned)
    base = {
        "KEYWORDS": ["expert comptable"],
        "EXPANSION_KEYWORDS": [],
        "LOCATIONS": ["Paris"],
        "EXPANSION_LOCATIONS": [],
        "EXCLUDE_DOMAINS": [],
        "ENRICH_ENABLED": True,
        "TARGET_MODE": "instantly_pushed",
    }
    tuned = {
        **base,
        "OUTSCRAPER_BATCH_SIZE": 999,
        "OUTSCRAPER_CONCURRENCY": 99,
        "ENRICH_CONCURRENCY": 99,
        "ENRICH_TIMEOUT_MS": 1,
        "SCRAPE_START_QUERY_PASS": 9,
    }
    assert build_config_fingerprint(base) == build_config_fingerprint(tuned)
    assert build_config_identity_fingerprint(base) == build_config_identity_fingerprint(tuned)


def test_is_target_reached_does_not_call_live_every_lead() -> None:
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    with patch("scrape_metrics.fetch_instantly_live") as mock_live:
        assert not _is_target_reached(
            target=10000,
            target_mode="instantly_pushed",
            leads_saved=100,
            instantly_pushed=10,
            config=config,
        )
        mock_live.assert_not_called()


def test_is_target_reached_live_only_near_target() -> None:
    config = {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "list"}
    with patch("scrape_metrics.fetch_instantly_live", return_value=10000) as mock_live:
        assert _is_target_reached(
            target=10000,
            target_mode="instantly_pushed",
            leads_saved=0,
            instantly_pushed=9600,
            config=config,
        )
        mock_live.assert_called_once()


def test_build_queries_department_phase() -> None:
    config = {
        "KEYWORDS": ["expert comptable"],
        "EXPANSION_KEYWORDS": ["expert-comptable"],
        "LOCATIONS": ["Paris"],
        "EXPANSION_LOCATIONS": ["Lyon"],
    }
    queries = build_queries(config, 0, geo_phase="department")
    assert queries
    assert any("departement 75" in q for q in queries)
    assert all("France" in q for q in queries)
