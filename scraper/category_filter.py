"""Taxonomy-based lead qualification — type/category/subtypes only (not company name)."""

from __future__ import annotations

import json
import re
from typing import Any

AUTO_SEA_RE = re.compile(
    r"(?<![a-z])sea(?![a-z]).{0,40}(automobile|exploitation|vhu|garage)|"
    r"(automobile|exploitation|vhu|garage).{0,40}(?<![a-z])sea(?![a-z])",
    re.I,
)


def _normalize_subtypes(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if item]
        return ", ".join(parts)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return ", ".join(str(item).strip() for item in parsed if item)
            except json.JSONDecodeError:
                pass
        return text
    return str(value).strip()


def taxonomy_text(business: dict[str, Any]) -> str:
    """Concatenate Outscraper type, category, subtypes (excludes company name)."""
    raw_parts = [
        str(business.get("type") or "").strip(),
        str(business.get("category") or "").strip(),
        _normalize_subtypes(business.get("subtypes")),
    ]
    return " | ".join(part for part in raw_parts if part).lower()


def taxonomy_text_from_csv_row(row: dict[str, Any]) -> str:
    """Rebuild taxonomy text from exported CSV columns."""
    raw_parts = [
        str(row.get("Type") or "").strip(),
        str(row.get("Category") or "").strip(),
        _normalize_subtypes(row.get("Subtypes")),
    ]
    return " | ".join(part for part in raw_parts if part).lower()


def taxonomy_fields(business: dict[str, Any]) -> dict[str, str]:
    """Separate Outscraper taxonomy fields for CSV and Instantly custom variables."""
    return {
        "Type": str(business.get("type") or "").strip(),
        "Category": str(business.get("category") or "").strip(),
        "Subtypes": _normalize_subtypes(business.get("subtypes")),
    }


def format_category_display(business: dict[str, Any]) -> str:
    """Human-readable category for CSV export."""
    raw_parts = [
        str(business.get("type") or "").strip(),
        str(business.get("category") or "").strip(),
        _normalize_subtypes(business.get("subtypes")),
    ]
    return " | ".join(part for part in raw_parts if part)


def _service_keyword_matches(text_lower: str, keyword: str) -> bool:
    kw = str(keyword).lower()
    if kw == "sea":
        return bool(re.search(r"(?<![a-z])sea(?![a-z])", text_lower)) and not AUTO_SEA_RE.search(
            text_lower
        )
    return kw in text_lower


def _service_rules(config: dict) -> list[dict[str, Any]]:
    rules = config.get("SERVICE_RULES") or []
    return [rule for rule in rules if isinstance(rule, dict)]


def detect_service_match(text: str, config: dict) -> str | None:
    """Return the first matching service label, or None if no rule matched."""
    text_lower = str(text).lower()
    for rule in _service_rules(config):
        label = str(rule.get("label") or "").strip()
        if not label:
            continue
        for keyword in rule.get("keywords") or []:
            if _service_keyword_matches(text_lower, str(keyword)):
                return label
    return None


def detect_service(text: str, config: dict) -> str:
    """Return matched service label, or SERVICE_DEFAULT when no rule matches."""
    match = detect_service_match(text, config)
    if match:
        return match
    return str(config.get("SERVICE_DEFAULT") or "Marketing Digital")


def detect_service_from_taxonomy(text: str) -> str:
    """Backward-compatible alias for biggy_agency marketing rules."""
    return detect_service(
        text,
        {
            "SERVICE_DEFAULT": "Marketing Digital",
            "SERVICE_RULES": [
                {"label": "SEO", "keywords": ["référencement", "referencement", "seo"]},
                {"label": "Google Ads", "keywords": ["google ads", "sea"]},
                {"label": "Facebook Ads", "keywords": ["facebook ads", "meta ads"]},
            ],
        },
    )
