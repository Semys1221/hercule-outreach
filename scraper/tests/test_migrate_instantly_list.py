"""Tests for Instantly list migration helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from instantly_client import lead_item_to_row  # noqa: E402
from migrate_instantly_list import migrate_instantly_list  # noqa: E402


def test_lead_item_to_row_maps_fields() -> None:
    row = lead_item_to_row(
        {
            "id": "lead-1",
            "email": "Test@Example.com",
            "first_name": "Acme",
            "company_name": "Acme SAS",
            "website": "https://acme.fr",
            "phone": "+33123456789",
            "custom_variables": {"city": "Paris"},
        },
        "list-abc",
    )
    assert row is not None
    assert row["email"] == "test@example.com"
    assert row["company_name"] == "Acme SAS"
    assert row["source_list_id"] == "list-abc"
    assert row["instantly_lead_id"] == "lead-1"
    assert row["custom_variables"] == {"city": "Paris"}


def test_lead_item_to_row_skips_missing_email() -> None:
    assert lead_item_to_row({"company_name": "No Email Co"}, "list-abc") is None


def test_migrate_instantly_list_dry_run() -> None:
    sample_leads = [{"id": "1", "email": "a@example.com", "company_name": "A"}]
    with patch("migrate_instantly_list.count_leads_in_list", return_value=1), patch(
        "migrate_instantly_list.paginate_list_leads",
        return_value=sample_leads,
    ), patch(
        "migrate_instantly_list.export_list_leads_to_supabase",
        return_value={
            "instantly_total": 1,
            "exportable": 1,
            "skipped": 0,
            "upserted": 0,
            "supabase_total": 0,
        },
    ), patch("migrate_instantly_list.purge_leads_from_list") as purge_mock:
        report = migrate_instantly_list("key", "list-abc", dry_run=True)
        assert report["dry_run"] is True
        assert report["instantly_before"] == 1
        assert report["exportable"] == 1
        purge_mock.assert_not_called()


def test_migrate_instantly_list_execute_purges_after_export() -> None:
    with patch("migrate_instantly_list.count_leads_in_list", side_effect=[2, 0]), patch(
        "migrate_instantly_list.paginate_list_leads",
        return_value=[{"id": "1", "email": "a@example.com"}],
    ), patch(
        "migrate_instantly_list.export_list_leads_to_supabase",
        return_value={
            "instantly_total": 1,
            "exportable": 1,
            "skipped": 0,
            "upserted": 1,
            "supabase_total": 1,
        },
    ), patch(
        "migrate_instantly_list.purge_leads_from_list",
        return_value=2,
    ) as purge_mock:
        report = migrate_instantly_list("key", "list-abc", dry_run=False)
        assert report["purge_deleted"] == 2
        assert report["instantly_after"] == 0
        purge_mock.assert_called_once()
