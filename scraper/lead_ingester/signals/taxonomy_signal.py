"""Taxonomy signal — wraps taxonomy_gate into a scored SignalResult."""

from __future__ import annotations

from typing import Any

from category_filter import taxonomy_text, taxonomy_text_from_csv_row
from lead_ingester.models import SignalResult
from taxonomy_gate import matches_taxonomy_text, taxonomy_excluded_keywords


def score_taxonomy(row: dict[str, Any], config: dict[str, Any]) -> SignalResult:
    """Score Google Maps taxonomy fields (type / category / subtypes).

    Accepts either a raw Outscraper place dict or a CSV-style lead row
    (Type / Category / Subtypes).
    """
    included = [
        str(k).strip()
        for k in (config.get("TAXONOMY_INCLUDED_KEYWORDS") or [])
        if str(k).strip()
    ]
    excluded = taxonomy_excluded_keywords(config)

    # Prefer CSV columns when present (post-_process_business rows)
    if any(row.get(k) for k in ("Type", "Category", "Subtypes")):
        text = taxonomy_text_from_csv_row(row)
    else:
        text = taxonomy_text(row)

    if not text.strip():
        if config.get("TAXONOMY_STRICT"):
            return SignalResult(score=0.3, error="empty_taxonomy")
        return SignalResult(score=0.7, error="empty_taxonomy")

    ok, matched = matches_taxonomy_text(text, included, excluded_keywords=excluded or None)

    if matched and str(matched).startswith("excluded:"):
        kw = str(matched)[9:]
        return SignalResult(
            score=0.0,
            hard_reject=True,
            matched_exclude=[kw],
            detail={"taxonomy_text": text},
        )

    if ok:
        return SignalResult(
            score=1.0,
            matched_include=[matched] if matched else [],
            detail={"taxonomy_text": text},
        )

    # No include match and no exclude match
    if config.get("TAXONOMY_STRICT"):
        return SignalResult(score=0.3, detail={"taxonomy_text": text})
    return SignalResult(score=0.7, detail={"taxonomy_text": text})
