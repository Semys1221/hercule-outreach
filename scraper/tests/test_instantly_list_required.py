"""Fail-fast when scrape/push has no Instantly list."""

from __future__ import annotations

import pytest

from bootstrap.validators import require_instantly_list_for_scrape_push


def test_require_instantly_list_rejects_empty() -> None:
    with pytest.raises(ValueError, match="INSTANTLY_LIST_ID is required"):
        require_instantly_list_for_scrape_push(
            {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": ""},
            preset_id="avocats",
        )


def test_require_instantly_list_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError, match="must be a UUID"):
        require_instantly_list_for_scrape_push(
            {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": "not-a-uuid"},
            preset_id="avocats",
        )


def test_require_instantly_list_accepts_valid() -> None:
    list_id = "0010fd68-8e7a-4624-bb65-6216b260bf2c"
    assert (
        require_instantly_list_for_scrape_push(
            {"INSTANTLY_API_KEY": "k", "INSTANTLY_LIST_ID": list_id},
            preset_id="avocats",
        )
        == list_id
    )
