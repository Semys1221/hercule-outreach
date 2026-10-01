"""Dedup fetch heartbeat and partial cache resume."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from instantly_client import (  # noqa: E402
    fetch_workspace_emails,
    load_workspace_cache_entry,
    load_workspace_email_cache,
    save_workspace_email_cache,
)
from scrape_metrics import wrap_progress_with_heartbeat  # noqa: E402


def test_wrap_progress_with_heartbeat_throttles_callback() -> None:
    progress_calls: list[int] = []
    heartbeat_calls: list[int] = []

    wrapped = wrap_progress_with_heartbeat(
        progress_calls.append,
        lambda: heartbeat_calls.append(1),
        interval_s=1000.0,
    )
    wrapped(1)
    wrapped(2)
    assert progress_calls == [1, 2]
    assert heartbeat_calls == [1]


def test_partial_cache_resume_skips_completed_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "workspace_emails.json"
    save_workspace_email_cache(
        {"a@example.com"},
        list_ids=["list-a", "list-b"],
        campaign_ids=[],
        complete=False,
        completed_scopes=["list:list-a"],
        cache_path=str(cache_path),
    )

    partial = load_workspace_cache_entry(
        list_ids=["list-a", "list-b"],
        campaign_ids=[],
        cache_path=str(cache_path),
        allow_partial=True,
    )
    assert partial is not None
    assert partial["emails"] == {"a@example.com"}
    assert partial["completed_scopes"] == ["list:list-a"]
    assert load_workspace_email_cache(
        list_ids=["list-a", "list-b"],
        campaign_ids=[],
        cache_path=str(cache_path),
    ) is None

    client = MagicMock()
    client.fetch_dedup_emails.return_value = {"a@example.com", "b@example.com"}

    monkeypatch.setattr("instantly_client.InstantlyClient", lambda _key: client)

    emails = fetch_workspace_emails(
        "test-key",
        list_ids=["list-a", "list-b"],
        campaign_ids=[],
        cache_path=str(cache_path),
        use_cache=True,
    )
    assert emails == {"a@example.com", "b@example.com"}
    client.fetch_dedup_emails.assert_called_once()
    kwargs = client.fetch_dedup_emails.call_args.kwargs
    assert kwargs["initial_emails"] == {"a@example.com"}
    assert kwargs["skip_scopes"] == {"list:list-a"}

    complete = load_workspace_email_cache(
        list_ids=["list-a", "list-b"],
        campaign_ids=[],
        cache_path=str(cache_path),
    )
    assert complete == {"a@example.com", "b@example.com"}
    with cache_path.open(encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["complete"] is True
