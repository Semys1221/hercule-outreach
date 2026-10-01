"""Tests for Instantly subsequence condition matching."""

from instantly_client import (
    DEFAULT_INTERESTED_CONDITIONS,
    find_subsequence,
    subsequence_conditions_equal,
)


def test_subsequence_conditions_equal_ignores_instantly_default_fields() -> None:
    api_conditions = {
        "crm_status": [1],
        "lead_activity": [],
        "reply_contains": "",
    }
    assert subsequence_conditions_equal(api_conditions, DEFAULT_INTERESTED_CONDITIONS)


def test_find_subsequence_matches_by_crm_status_despite_different_name() -> None:
    items = [
        {
            "id": "sub-1",
            "name": "Interested bypass — Runbook Test",
            "conditions": {
                "crm_status": [1],
                "lead_activity": [],
                "reply_contains": "",
            },
        }
    ]
    match = find_subsequence(
        items,
        name="Hercule — Runbook Test — Interested",
        conditions=DEFAULT_INTERESTED_CONDITIONS,
    )
    assert match is not None
    assert match["id"] == "sub-1"
