"""Outscraper taxonomy gate — métier filter on type/category/subtypes only."""

from __future__ import annotations

from typing import Any

from category_filter import taxonomy_text, taxonomy_text_from_csv_row

# Trash rate above this threshold triggers a pipeline warning
TAXONOMY_TRASH_RATE_WARN = 0.60  # 60 % of processed places rejected as taxonomy_mismatch


def taxonomy_excluded_keywords(config: dict[str, Any]) -> list[str]:
    """Merge hard-excluded and legacy excluded keyword lists from preset config."""
    hard = [str(k).strip() for k in (config.get("TAXONOMY_HARD_EXCLUDED_KEYWORDS") or []) if str(k).strip()]
    legacy = [str(k).strip() for k in (config.get("TAXONOMY_EXCLUDED_KEYWORDS") or []) if str(k).strip()]
    seen: set[str] = set()
    merged: list[str] = []
    for kw in hard + legacy:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            merged.append(kw)
    return merged


def matches_taxonomy_text(
    text: str,
    included_keywords: list[str],
    excluded_keywords: list[str] | None = None,
) -> tuple[bool, str]:
    """Same rules as matches_taxonomy, on pre-built taxonomy text."""
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False, ""

    if excluded_keywords:
        for keyword in excluded_keywords:
            kw = str(keyword).strip().lower()
            if kw and kw in normalized:
                return False, f"excluded:{kw}"

    for keyword in included_keywords:
        kw = str(keyword).strip().lower()
        if kw and kw in normalized:
            return True, kw

    return False, ""


def matches_taxonomy(
    business: dict[str, Any],
    included_keywords: list[str],
    excluded_keywords: list[str] | None = None,
) -> tuple[bool, str]:
    """Return (match, matched_keyword_or_reason).

    Hard exclusions are checked first: if any excluded keyword appears in the
    taxonomy text the business is immediately rejected (returns False even when
    an included keyword also matches).  This lets the config prune obvious noise
    (stores, schools, wholesalers…) without removing them from the included list.

    Args:
        business: raw Outscraper place dict.
        included_keywords: at least one must match → accept.
        excluded_keywords: any match → reject (beats included).

    Returns:
        (True, matched_keyword) on accept.
        (False, "excluded:<kw>") when a hard exclusion fires.
        (False, "") when no included keyword matches.
    """
    return matches_taxonomy_text(
        taxonomy_text(business),
        included_keywords,
        excluded_keywords=excluded_keywords,
    )


def matches_taxonomy_csv_row(
    row: dict[str, Any],
    included_keywords: list[str],
    excluded_keywords: list[str] | None = None,
) -> tuple[bool, str]:
    """Taxonomy gate for saved CSV rows (Type / Category / Subtypes)."""
    return matches_taxonomy_text(
        taxonomy_text_from_csv_row(row),
        included_keywords,
        excluded_keywords=excluded_keywords,
    )


def taxonomy_trash_rate(
    taxonomy_mismatches: int,
    raw_places: int,
) -> float:
    """Return fraction of raw places rejected due to taxonomy mismatch (0–1)."""
    if raw_places <= 0:
        return 0.0
    return taxonomy_mismatches / raw_places


def is_taxonomy_trash_rate_high(
    taxonomy_mismatches: int,
    raw_places: int,
    threshold: float = TAXONOMY_TRASH_RATE_WARN,
) -> bool:
    """True when taxonomy mismatch rate exceeds *threshold*."""
    return taxonomy_trash_rate(taxonomy_mismatches, raw_places) > threshold
