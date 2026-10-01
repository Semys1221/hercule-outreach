"""Stamp cleaned=valid on final-clean leads (CSV column + Instantly custom_variables)."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

CLEANED_KEY = "cleaned"
CLEANED_VALUE_VALID = "valid"


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
