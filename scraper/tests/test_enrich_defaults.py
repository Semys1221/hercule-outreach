"""Enrich/SIRET disabled by default — taxonomy-only pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import _enrich_settings, website_required_for_scrape  # noqa: E402
from configs._bases.common import ENRICH_SETTINGS, INGESTER_SETTINGS, REGISTRY_SETTINGS  # noqa: E402


def test_common_defaults_disable_enrich_and_pappers() -> None:
    assert ENRICH_SETTINGS["ENRICH_ENABLED"] is False
    assert REGISTRY_SETTINGS["PAPPERS_ENABLED"] is False
    assert INGESTER_SETTINGS["INGESTER_ENABLED"] is False


def test_enrich_settings_fallback_disabled() -> None:
    settings = _enrich_settings({})
    assert settings["enabled"] is False


def test_website_not_required_when_outscraper_has_only_with_website_filter() -> None:
    config = {"ENRICH_ENABLED": False, "OUTSCRAPER_FILTERS": ["only_with_website"]}
    assert website_required_for_scrape(config) is False


def test_website_required_when_ingester_enabled() -> None:
    config = {"INGESTER_ENABLED": True, "OUTSCRAPER_FILTERS": ["only_with_website"]}
    assert website_required_for_scrape(config) is True
