"""Tests for Instantly workspace-wide dedup."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import _process_business  # noqa: E402
from instantly_client import InstantlyClient, fetch_workspace_emails  # noqa: E402


def test_process_business_rejects_email_already_in_seen_set() -> None:
    config = {"TAXONOMY_GATE_ENABLED": False, "EXCLUDE_DOMAINS": []}
    seen_em = {"existing@example.com"}
    row, audit = _process_business(
        {
            "name": "Cabinet Test",
            "site": "https://example.com",
            "email_1": "existing@example.com",
        },
        config,
        seen_domain=set(),
        seen_em=seen_em,
    )
    assert row is None
    assert audit is not None
    assert "duplicate" in audit["Reason"].lower()


def test_fetch_workspace_emails_unions_lists_and_campaigns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=InstantlyClient)
    client.fetch_dedup_emails.return_value = {"a@example.com", "b@example.com"}

    monkeypatch.setattr(
        "instantly_client.InstantlyClient",
        lambda _key: client,
    )
    monkeypatch.setattr(
        "instantly_client.load_workspace_email_cache",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "instantly_client.load_workspace_cache_entry",
        lambda **kwargs: None,
    )
    saved: list[dict] = []

    def _save(emails, **kwargs):
        saved.append({"count": len(emails), **kwargs})

    monkeypatch.setattr("instantly_client.save_workspace_email_cache", _save)

    emails = fetch_workspace_emails(
        "test-key",
        list_ids=["list-a"],
        campaign_ids=["camp-b"],
        use_cache=False,
    )
    assert emails == {"a@example.com", "b@example.com"}
    client.fetch_dedup_emails.assert_called_once()
    assert saved[-1]["complete"] is True
