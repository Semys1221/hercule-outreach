"""Tests for contact field backfill from raw Outscraper JSONL."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from backfill_contact_from_raw import (  # noqa: E402
    build_contact_index_from_raw,
    contact_fields_from_business,
)


def test_contact_fields_from_business_prefers_formatted_phone() -> None:
    fields = contact_fields_from_business(
        {
            "phone": "+33 1 40 18 30 04",
            "phone_1": "0140183004",
            "rating": 4.5,
            "reviews": 12,
        }
    )
    assert fields["Phone"] == "+33 1 40 18 30 04"
    assert fields["Rating"] == "4.5"
    assert fields["ReviewsCount"] == "12"


def test_build_contact_index_from_raw(tmp_path: Path) -> None:
    jsonl = tmp_path / "outscraper_raw.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "name": "Acme",
                "email": "shop@example.com",
                "phone": "+33 6 12 34 56 78",
                "rating": 4.2,
                "reviews_count": 7,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    index = build_contact_index_from_raw(str(jsonl))
    assert index["shop@example.com"]["Phone"] == "+33 6 12 34 56 78"
    assert index["shop@example.com"]["ReviewsCount"] == "7"
