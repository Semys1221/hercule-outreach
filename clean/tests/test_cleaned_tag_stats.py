"""Unit tests for cleaned tag counting helpers."""

from __future__ import annotations

from clean_column import (
    CLEANED_KEY,
    CLEANED_VALUE_VALID,
    cleaned_tag_status,
    count_cleaned_tag_on_leads,
)


def test_cleaned_tag_status_valid() -> None:
    assert cleaned_tag_status({CLEANED_KEY: CLEANED_VALUE_VALID}) == "valid"
    assert cleaned_tag_status({CLEANED_KEY: " valid "}) == "valid"


def test_cleaned_tag_status_missing() -> None:
    assert cleaned_tag_status({}) == "missing"
    assert cleaned_tag_status({CLEANED_KEY: ""}) == "missing"
    assert cleaned_tag_status({CLEANED_KEY: "   "}) == "missing"


def test_cleaned_tag_status_other() -> None:
    assert cleaned_tag_status({CLEANED_KEY: "pending"}) == "other"


def test_count_cleaned_tag_on_leads() -> None:
    leads = [
        {"custom_variables": {CLEANED_KEY: CLEANED_VALUE_VALID}},
        {"custom_variables": {}},
        {"custom_variables": {CLEANED_KEY: "x"}},
    ]

    def _merged(lead: dict) -> dict:
        return lead.get("custom_variables") or {}

    stats = count_cleaned_tag_on_leads(leads, merged_vars_for_lead=_merged)
    assert stats == {"total": 3, "missing": 1, "valid": 1, "other": 1}
