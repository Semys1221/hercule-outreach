"""INSTANTLY_BACKLOG_PUSH_MIN — push CSV rows missing from Instantly at startup."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from core_logic import (  # noqa: E402
    _backlog_push_min,
    _flush_instantly_buffer,
    _push_csv_backlog_if_needed,
)


def test_backlog_push_min_reads_config() -> None:
    assert _backlog_push_min({"INSTANTLY_BACKLOG_PUSH_MIN": 25}) == 25
    assert _backlog_push_min({"INSTANTLY_PUSH_EVERY": 50}) == 50


@pytest.mark.asyncio
async def test_backlog_push_skips_below_threshold(tmp_path: Path) -> None:
    csv_path = tmp_path / "leads.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Email", "Company", "Website", "Service", "City"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Email": "new@example.com",
                "Company": "Co",
                "Website": "https://example.com",
                "Service": "svc",
                "City": "Paris",
            }
        )

    logs: list[str] = []

    pushed, delta = await _push_csv_backlog_if_needed(
        {"INSTANTLY_BACKLOG_PUSH_MIN": 5, "INSTANTLY_PUSH_EVERY": 100},
        workspace_emails=set(),
        csv_path=str(csv_path),
        state_path=str(tmp_path / "state.json"),
        log_cb=logs.append,
        instantly_pushed=0,
        run_state=None,
    )
    assert pushed == 0
    assert delta == 0
    assert any("Backlog push skip" in line for line in logs)


@pytest.mark.asyncio
async def test_backlog_push_uploads_missing_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "leads.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Email", "Company", "Website", "Service", "City"],
        )
        writer.writeheader()
        for idx in range(3):
            writer.writerow(
                {
                    "Email": f"lead{idx}@example.com",
                    "Company": f"Co {idx}",
                    "Website": f"https://example{idx}.com",
                    "Service": "svc",
                    "City": "Paris",
                }
            )

    flush_mock = AsyncMock(return_value={"pushed": 3, "skipped_duplicate": 0})

    with patch("core_logic._flush_instantly_buffer", flush_mock):
        pushed, delta = await _push_csv_backlog_if_needed(
            {
                "INSTANTLY_BACKLOG_PUSH_MIN": 2,
                "INSTANTLY_PUSH_EVERY": 100,
                "INSTANTLY_API_KEY": "key",
                "INSTANTLY_LIST_ID": "list",
            },
            workspace_emails={"already@example.com"},
            csv_path=str(csv_path),
            state_path=str(tmp_path / "state.json"),
            log_cb=lambda _msg: None,
            instantly_pushed=10,
            run_state={"instantly_pushed": 10},
        )

    assert pushed == 13
    assert delta == 3
    flush_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_backlog_abort_after_duplicate_skip_streak(tmp_path: Path) -> None:
    csv_path = tmp_path / "leads.csv"
    cache_path = tmp_path / "workspace_emails.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Email", "Company"])
        writer.writeheader()
        for idx in range(6):
            writer.writerow({"Email": f"lead{idx}@example.com", "Company": f"Co {idx}"})

    logs: list[str] = []
    workspace: set[str] = set()
    flush_mock = AsyncMock(
        side_effect=[
            {
                "pushed": 0,
                "skipped_duplicate": 2,
                "emails": ["lead0@example.com", "lead1@example.com"],
            },
            {
                "pushed": 0,
                "skipped_duplicate": 2,
                "emails": ["lead2@example.com", "lead3@example.com"],
            },
            {
                "pushed": 2,
                "skipped_duplicate": 0,
                "emails": ["lead4@example.com", "lead5@example.com"],
            },
        ]
    )

    with patch("core_logic._flush_instantly_buffer", flush_mock):
        pushed, delta = await _push_csv_backlog_if_needed(
            {
                "INSTANTLY_BACKLOG_PUSH_MIN": 2,
                "INSTANTLY_PUSH_EVERY": 2,
                "INSTANTLY_DEDUP_LIST_IDS": ["list"],
                "INSTANTLY_DEDUP_CAMPAIGN_IDS": ["camp"],
            },
            workspace_emails=workspace,
            csv_path=str(csv_path),
            state_path=str(tmp_path / "state.json"),
            log_cb=logs.append,
            instantly_pushed=0,
            run_state={"instantly_pushed": 0},
            cache_path=str(cache_path),
        )

    assert pushed == 0
    assert delta == 0
    assert flush_mock.await_count == 2
    assert any("Backlog push abort" in line for line in logs)
    assert "lead5@example.com" in workspace
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["complete"] is True
    assert "lead5@example.com" in cached["emails"]


@pytest.mark.asyncio
async def test_flush_skips_provision_when_nothing_uploaded() -> None:
    logs: list[str] = []
    pending = [{"Email": "dup@example.com", "Company": "Co"}]
    provision = AsyncMock()
    push = AsyncMock(return_value={"pushed": 0, "skipped_duplicate": 1})

    with (
        patch("instantly_client.push_leads_to_list", push),
        patch("link_provision_client.provision_leads_after_push", provision),
        patch("core_logic._sync_mev_emails_sidecar"),
    ):
        stats = await _flush_instantly_buffer(
            pending,
            {
                "INSTANTLY_API_KEY": "key",
                "INSTANTLY_LIST_ID": "list",
                "INSTANTLY_PROVISION_LINKS": True,
            },
            log_cb=logs.append,
        )

    assert stats["pushed"] == 0
    assert stats["skipped_duplicate"] == 1
    provision.assert_not_awaited()
    assert any("Link provision skipped" in line for line in logs)


@pytest.mark.asyncio
async def test_backlog_push_defers_on_instantly_fail_streak(tmp_path: Path) -> None:
    csv_path = tmp_path / "leads.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Email", "Company", "Website", "Service", "City"],
        )
        writer.writeheader()
        for idx in range(4):
            writer.writerow(
                {
                    "Email": f"lead{idx}@example.com",
                    "Company": f"Co {idx}",
                    "Website": f"https://example{idx}.com",
                    "Service": "svc",
                    "City": "Paris",
                }
            )

    logs: list[str] = []
    flush_mock = AsyncMock(
        side_effect=[
            {"pushed": 0, "skipped_duplicate": 0, "failed": 25, "emails": []},
            {"pushed": 0, "skipped_duplicate": 0, "failed": 25, "emails": []},
        ]
    )

    with patch("core_logic._flush_instantly_buffer", flush_mock):
        pushed, delta = await _push_csv_backlog_if_needed(
            {
                "INSTANTLY_BACKLOG_PUSH_MIN": 2,
                "INSTANTLY_PUSH_EVERY": 2,
            },
            workspace_emails=set(),
            csv_path=str(csv_path),
            state_path=str(tmp_path / "state.json"),
            log_cb=logs.append,
            instantly_pushed=0,
            run_state={"instantly_pushed": 0},
        )

    assert pushed == 0
    assert delta == 0
    assert flush_mock.await_count == 2
    assert any("Backlog push defer" in line for line in logs)
