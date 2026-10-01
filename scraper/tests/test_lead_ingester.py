"""Unit tests for lead_ingester signals and scorer (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from configs._bases.common import INGESTER_SETTINGS  # noqa: E402
from lead_ingester.models import SignalResult  # noqa: E402
from lead_ingester.scorer import compute_score  # noqa: E402
from lead_ingester.signals.review_signal import score_reviews  # noqa: E402
from lead_ingester.signals.taxonomy_signal import score_taxonomy  # noqa: E402
from lead_ingester.signals.website_signal import score_website  # noqa: E402


def test_taxonomy_include_match() -> None:
    result = score_taxonomy(
        {"Type": "Accountant", "Category": "Expert-comptable", "Subtypes": ""},
        {
            "TAXONOMY_INCLUDED_KEYWORDS": ["comptable"],
            "TAXONOMY_HARD_EXCLUDED_KEYWORDS": [],
        },
    )
    assert result.score == 1.0
    assert result.hard_reject is False


def test_taxonomy_hard_exclude() -> None:
    result = score_taxonomy(
        {"type": "Software", "category": "Logiciel comptable", "subtypes": ""},
        {
            "TAXONOMY_INCLUDED_KEYWORDS": ["comptable"],
            "TAXONOMY_HARD_EXCLUDED_KEYWORDS": ["logiciel"],
        },
    )
    assert result.hard_reject is True
    assert result.score == 0.0


def test_reviews_neutral_when_missing() -> None:
    result = score_reviews({}, INGESTER_SETTINGS)
    assert result.score == 0.5


def test_reviews_icp_boost() -> None:
    result = score_reviews(
        {
            "_reviews_data": [
                {"review_text": "Excellent cabinet comptable", "review_rating": 5}
            ]
        },
        INGESTER_SETTINGS,
    )
    assert result.score > 0.5
    assert "cabinet" in result.matched_include


def test_website_hard_exclude() -> None:
    html = (
        "<html><body>"
        + "<p>Notre imprimerie réalise flyer brochure packaging goodies pour vos événements.</p>" * 5
        + "</body></html>"
    )
    result = score_website(
        html,
        {
            "ENRICH_INCLUDED_KEYWORDS": ["imprimerie"],
            "ENRICH_HARD_EXCLUDED_KEYWORDS": ["flyer"],
            "ENRICH_SOFT_EXCLUDED_KEYWORDS": [],
        },
    )
    assert result.hard_reject is True


def test_website_none_is_neutral() -> None:
    result = score_website(None, {}, fetch_error="fetch_timeout")
    assert result.score == 0.5
    assert result.error == "fetch_timeout"


def test_scorer_accept() -> None:
    s = SignalResult(score=0.8)
    result = compute_score(s, s, s, s, INGESTER_SETTINGS)
    assert result.verdict == "ACCEPT"


def test_scorer_hard_reject_bypasses_weights() -> None:
    good = SignalResult(score=1.0)
    bad = SignalResult(score=0.0, hard_reject=True, matched_exclude=["logiciel"])
    result = compute_score(good, bad, good, good, INGESTER_SETTINGS)
    assert result.verdict == "REJECT"
    assert result.reject_reason.startswith("hard_reject:website")
