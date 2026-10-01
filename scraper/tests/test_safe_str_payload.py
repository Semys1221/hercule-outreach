"""Tests for JSON-safe Instantly lead payloads."""

import json
import math

import pandas as pd

from instantly_client import _lead_payload, _safe_str


def test_safe_str_converts_nan_to_empty() -> None:
    assert _safe_str(float("nan")) == ""
    assert _safe_str(pd.NA) == ""
    assert _safe_str(None) == ""
    assert _safe_str("Acme") == "Acme"


def test_lead_payload_serializes_with_nan_registry_fields() -> None:
    row = {
        "Email": "test@example.com",
        "Company": "Cabinet Test",
        "Website": "https://example.com",
        "Siret": float("nan"),
        "Siren": float("nan"),
        "Effectif": float("nan"),
    }
    payload = _lead_payload(row, "list-id")
    json.dumps(payload)
