"""Tests for vol throughput helpers (Outscraper filters, geo advance)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import (  # noqa: E402
    _process_business,
    batch_duplicate_saturated,
    outscraper_filters,
    outscraper_request_language,
    website_required_for_scrape,
)


def test_outscraper_filters_from_config() -> None:
    config = {"OUTSCRAPER_FILTERS": ["only_with_website", "operational_only"]}
    assert outscraper_filters(config) == ["only_with_website", "operational_only"]


def test_website_not_required_when_outscraper_filter_set() -> None:
    config = {
        "ENRICH_ENABLED": False,
        "OUTSCRAPER_FILTERS": ["only_with_website"],
        "EXCLUDE_DOMAINS": [],
        "TAXONOMY_GATE_ENABLED": False,
    }
    assert website_required_for_scrape(config) is False
    row, audit = _process_business(
        {
            "name": "Cabinet Test",
            "email": "contact@cabinet-test.fr",
            "type": "Expert-comptable",
            "category": "Cabinet d'expertise comptable",
        },
        config,
        seen_domain=set(),
        seen_em=set(),
    )
    assert row is not None
    assert audit is not None
    assert audit["Verdict"] == "accepted"


def test_outscraper_request_language_uses_en_with_filters() -> None:
    assert outscraper_request_language({"OUTSCRAPER_FILTERS": ["only_with_website"]}) == "en"
    assert outscraper_request_language({"OUTSCRAPER_FILTERS": []}) == "fr"


def test_batch_duplicate_saturated() -> None:
    assert batch_duplicate_saturated(10, 90, 50) is True
    assert batch_duplicate_saturated(40, 60, 40) is False
    assert batch_duplicate_saturated(1, 1, 1) is False
    assert batch_duplicate_saturated(
        10, 90, 35, config={"DUPLICATE_GEO_ADVANCE_RATE": 0.30}
    ) is True
    assert batch_duplicate_saturated(
        10, 90, 25, config={"DUPLICATE_GEO_ADVANCE_RATE": 0.30}
    ) is False


def test_fresh_geo_config_duplicate_rate_and_taxonomy() -> None:
    from config_loader import load_config

    config = load_config("cabinets_expertise_comptable_fresh_geo", require_keys=False)
    assert config.get("DUPLICATE_GEO_ADVANCE_RATE") == 0.30
    assert "tax advisor" in (config.get("TAXONOMY_INCLUDED_KEYWORDS") or [])
    assert config.get("OUTSCRAPER_ENRICHMENT") == ["leads_n_contacts"]


def test_cif_config_skip_phase_disabled() -> None:
    from config_loader import load_config
    import query_planner

    config = load_config("cabinets_conseiller_financier", require_keys=False)
    assert config.get("SCRAPE_SKIP_PHASE_ENABLED") is False
    assert config.get("SCRAPE_CONTINUOUS_MAX_ZERO_CYCLES") == 3
    slots = query_planner.build_slots(config)
    assert len(slots) > 0
