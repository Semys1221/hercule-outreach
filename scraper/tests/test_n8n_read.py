"""Tests for n8n execution fetch routing (public URL vs VPS SSH)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_SCRAPER_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_ROOT))

from bootstrap import n8n_read  # noqa: E402


def test_fetch_prefers_public_base_url_over_vps(monkeypatch) -> None:
    monkeypatch.setenv("N8N_API_KEY", "test-key")
    monkeypatch.setenv("N8N_BASE_URL", "https://n8n.example.com")
    monkeypatch.setenv("N8N_VIA_VPS", "1")
    monkeypatch.setenv("VPS_HOST", "203.0.113.1")
    monkeypatch.setenv("VPS_USER", "root")

    with patch.object(n8n_read, "_fetch_http", return_value=([{"id": "1"}], None)) as http_mock:
        with patch.object(n8n_read, "_fetch_via_vps_ssh") as vps_mock:
            rows, err = n8n_read.fetch_recent_executions(limit=5)

    assert err is None
    assert rows == [{"id": "1"}]
    http_mock.assert_called_once()
    vps_mock.assert_not_called()


def test_via_vps_default_off_without_base_url(monkeypatch) -> None:
    monkeypatch.delenv("N8N_VIA_VPS", raising=False)
    monkeypatch.delenv("N8N_BASE_URL", raising=False)
    monkeypatch.setenv("N8N_API_KEY", "test-key")

    with patch.object(n8n_read, "_fetch_via_vps_ssh") as vps_mock:
        rows, err = n8n_read.fetch_recent_executions(limit=3)

    assert rows == []
    assert err is None
    vps_mock.assert_not_called()
