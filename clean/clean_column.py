"""Stamp cleaned=valid on final-clean leads (CSV column + Instantly custom_variables)."""

from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

CLEANED_KEY = "cleaned"
CLEANED_VALUE_VALID = "valid"


def cleaned_tag_status(merged: dict[str, Any]) -> str:
    """Return ``valid``, ``missing``, or ``other`` for Instantly custom_variables merged dict."""
    value = merged.get(CLEANED_KEY)
    if value is None:
        return "missing"
    text = str(value).strip()
    if not text:
        return "missing"
    if text == CLEANED_VALUE_VALID:
        return "valid"
    return "other"


def count_cleaned_tag_on_leads(
    leads: list[dict[str, Any]],
    *,
    merged_vars_for_lead: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, int]:
    """Count leads by cleaned tag state (missing / valid / other)."""
    counts = {"total": len(leads), "missing": 0, "valid": 0, "other": 0}
    for lead in leads:
        status = cleaned_tag_status(merged_vars_for_lead(lead))
        counts[status] += 1
    return counts


def merge_custom_variables(value: Any) -> dict[str, Any]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return dict(parsed)
        except json.JSONDecodeError:
            pass
    return {}


def stamp_cleaned_valid(df: pd.DataFrame) -> pd.DataFrame:
    """Add flat `cleaned` column and set custom_variables['cleaned'] = valid on each row."""
    if df.empty:
        out = df.copy()
        out[CLEANED_KEY] = pd.Series(dtype=str)
        return out

    out = df.copy()
    custom_vars: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        cv = merge_custom_variables(row.get("custom_variables"))
        cv[CLEANED_KEY] = CLEANED_VALUE_VALID
        custom_vars.append(cv)
    out["custom_variables"] = custom_vars
    out[CLEANED_KEY] = CLEANED_VALUE_VALID
    return out


def stamp_verified_cleaned_column(
    verified_df: pd.DataFrame,
    allowed_statuses: list[str],
) -> pd.DataFrame:
    """Add `cleaned` column on verified artifact: valid when status is allowed, else empty."""
    out = verified_df.copy()
    status_col = "Verification_Status"
    if status_col not in out.columns:
        out[CLEANED_KEY] = ""
        return out
    allowed = set(allowed_statuses)
    out[CLEANED_KEY] = out[status_col].apply(
        lambda s: CLEANED_VALUE_VALID if s in allowed else ""
    )
    return out
