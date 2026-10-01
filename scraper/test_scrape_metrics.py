"""Tests for scrape metrics helpers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from scrape_metrics import (
    fetch_instantly_live,
    heartbeat_age_seconds,
    invalidate_instantly_live_cache,
    load_worker_heartbeat,
)


def test_heartbeat_age_seconds_recent() -> None:
    seen = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    age = heartbeat_age_seconds({"last_seen": seen})
    assert age is not None
    assert 0 <= age < 120


def test_heartbeat_age_seconds_missing() -> None:
    assert heartbeat_age_seconds(None) is None
    assert heartbeat_age_seconds({}) is None


def test_load_worker_heartbeat_missing(tmp_path) -> None:
    assert load_worker_heartbeat(str(tmp_path)) is None


def test_fetch_instantly_live_counts_campaign_when_attached() -> None:
    invalidate_instantly_live_cache()
    config = {
        "INSTANTLY_API_KEY": "key",
        "INSTANTLY_LIST_ID": "list-a",
        "INSTANTLY_CAMPAIGN_ID": "camp-a",
        "INSTANTLY_ATTACH_TO_CAMPAIGN": True,
    }
    with (
        patch("instantly_client.count_leads_in_list", return_value=3) as list_only,
        patch(
            "instantly_client.count_unique_emails_in_list_and_campaign",
            return_value=40,
        ) as both,
    ):
        assert fetch_instantly_live(config, use_cache=False) == 40
        both.assert_called_once_with("key", "list-a", "camp-a")
        list_only.assert_not_called()

        config["INSTANTLY_ATTACH_TO_CAMPAIGN"] = False
        assert fetch_instantly_live(config, use_cache=False) == 3
    invalidate_instantly_live_cache("list-a")
