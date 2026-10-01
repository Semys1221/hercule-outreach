"""Tests for the Outscraper SDK adapter."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from outscraper_client import (  # noqa: E402
    OutscraperClient,
    normalize_maps_search_payload,
    poll_once,
    poll_until_ready,
)


@dataclass
class _Job:
    task_id: str
    submitted_at: float
    last_polled_at: float = 0.0


@dataclass
class _Settings:
    poll_initial_s: float = 0.0
    poll_interval_s: float = 0.01
    poll_slow_s: float = 0.01
    poll_timeout_s: float = 5.0


@pytest.mark.asyncio
async def test_send_async_tasks_returns_task_id():
    mock_sdk = MagicMock()
    mock_sdk._request.return_value = {"id": "task-123", "status": "Pending"}

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    task_id = await client.send_async_tasks(
        ["expert comptable in Paris, France"],
        30,
        total_limit=100,
        skip_places=20,
        filters=["operational_only"],
        language="en",
    )

    assert task_id == "task-123"
    mock_sdk._request.assert_called_once()
    call_kwargs = mock_sdk._request.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["query"] == ["expert comptable in Paris, France"]
    assert payload["limit"] == 30
    assert payload["totalLimit"] == 100
    assert payload["skipPlaces"] == 20
    assert payload["filters"] == ["operational_only"]
    assert payload["extractContacts"] is True
    assert payload["async"] is True


@pytest.mark.asyncio
async def test_send_async_tasks_uses_enrichment_when_provided():
    mock_sdk = MagicMock()
    mock_sdk._request.return_value = {"id": "task-enrich", "status": "Pending"}

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    task_id = await client.send_async_tasks(
        ["expert comptable in Lyon, France"],
        30,
        enrichment=["leads_n_contacts"],
    )

    assert task_id == "task-enrich"
    payload = mock_sdk._request.call_args.kwargs["json"]
    assert payload["enrichment"] == ["leads_n_contacts"]
    assert "extractContacts" not in payload


@pytest.mark.asyncio
async def test_emails_and_contacts_returns_dicts():
    mock_sdk = MagicMock()
    mock_sdk.emails_and_contacts.return_value = [
        {"query": "example.fr", "email": "a@example.fr"},
    ]

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk

    results = await client.emails_and_contacts(["example.fr"])
    assert results == [{"query": "example.fr", "email": "a@example.fr"}]
    mock_sdk.emails_and_contacts.assert_called_once_with(["example.fr"])


@pytest.mark.asyncio
async def test_send_async_tasks_uses_configurable_region():
    mock_sdk = MagicMock()
    mock_sdk._request.return_value = {"id": "task-be", "status": "Pending"}

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    task_id = await client.send_async_tasks(
        ["expert comptable in Brussels, Belgium"],
        30,
        region="BE",
    )

    assert task_id == "task-be"
    payload = mock_sdk._request.call_args.kwargs["json"]
    assert payload["region"] == "BE"


@pytest.mark.asyncio
async def test_send_async_tasks_returns_none_on_sdk_error():
    mock_sdk = MagicMock()
    mock_sdk._request.side_effect = Exception("API error")

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk

    task_id = await client.send_async_tasks(["query"], 10)
    assert task_id is None


@pytest.mark.asyncio
async def test_check_task_status_pending_and_success():
    mock_sdk = MagicMock()
    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    mock_sdk.get_request_archive.return_value = {"status": "Pending"}
    assert await client.check_task_status("task-1") is None

    mock_sdk.get_request_archive.return_value = {
        "status": "Success",
        "data": [[{"name": "Acme", "email": "a@acme.fr"}]],
    }
    results = await client.check_task_status("task-1")
    assert results == [[{"name": "Acme", "email": "a@acme.fr"}]]


@pytest.mark.asyncio
async def test_check_task_status_failed_returns_empty_list():
    mock_sdk = MagicMock()
    mock_sdk.get_request_archive.return_value = {"status": "Failure"}

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    assert await client.check_task_status("task-1") == []


@pytest.mark.asyncio
async def test_cancel_task_uses_transport_delete():
    mock_transport = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_transport.api_request.return_value = mock_response

    client = OutscraperClient("test-key")
    client._sdk = MagicMock(_transport=mock_transport)
    client.qps_delay = 0

    assert await client.cancel_task("task-99") is True
    mock_transport.api_request.assert_called_once_with(
        "DELETE",
        "/requests/task-99",
        use_handle_response=False,
        wait_async=False,
        async_request=False,
    )


@pytest.mark.asyncio
async def test_list_running_requests_extracts_ids():
    mock_sdk = MagicMock()
    mock_sdk.get_requests_history.return_value = [
        {"id": "a"},
        {"id": "b"},
        {"no_id": True},
    ]

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk

    assert await client.list_running_requests() == ["a", "b"]


@pytest.mark.asyncio
async def test_poll_once_timeout():
    client = MagicMock(spec=OutscraperClient)
    job = _Job(task_id="t1", submitted_at=time.time() - 10)
    settings = _Settings(poll_timeout_s=5.0)

    status, results = await poll_once(client, job, settings)
    assert status == "failed"
    assert results == []
    client.check_task_status.assert_not_called()


@pytest.mark.asyncio
async def test_poll_until_ready_success():
    client = MagicMock(spec=OutscraperClient)
    client.check_task_status = AsyncMock(
        side_effect=[None, [{"name": "Lead Co"}]],
    )

    job = _Job(task_id="t1", submitted_at=time.time())
    settings = _Settings(poll_initial_s=0.0, poll_interval_s=0.0)
    logs: list[str] = []

    results = await poll_until_ready(client, job, settings, logs.append)
    assert results == [{"name": "Lead Co"}]


def test_normalize_maps_search_payload_nested() -> None:
    nested = [[{"name": "A"}], [{"name": "B"}]]
    assert normalize_maps_search_payload(nested) == nested
    flat = [{"name": "A"}, {"name": "B"}]
    assert normalize_maps_search_payload(flat) == [flat]


@pytest.mark.asyncio
async def test_google_maps_search_batch_calls_sdk():
    mock_sdk = MagicMock()
    mock_sdk._request.return_value = [[{"name": "Lead Co"}]]

    client = OutscraperClient("test-key")
    client._sdk = mock_sdk
    client.qps_delay = 0

    results = await client.google_maps_search_batch(
        ["kiné in Paris, France"],
        400,
        filters=["operational_only"],
        language="fr",
    )
    assert results == [[{"name": "Lead Co"}]]
    mock_sdk._request.assert_called_once()
    call_kwargs = mock_sdk._request.call_args.kwargs
    assert call_kwargs["wait_async"] is True
    assert call_kwargs["async_request"] is False
    payload = call_kwargs["json"]
    assert payload["dropDuplicates"] is True
    assert payload["limit"] == 400
