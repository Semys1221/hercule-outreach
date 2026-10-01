"""Audit CSV writers for the lead ingester."""

from __future__ import annotations

import csv
import json
import os
from typing import Any

from lead_ingester.models import CompositeResult

AUDIT_COLUMNS = [
    "email",
    "company",
    "website",
    "city",
    "taxonomy_score",
    "taxonomy_include",
    "taxonomy_exclude",
    "website_score",
    "website_text_len",
    "website_include",
    "website_soft_exclude",
    "website_error",
    "review_score",
    "review_count",
    "review_avg_rating",
    "review_icp",
    "review_anti_icp",
    "registry_score",
    "composite_score",
    "verdict",
    "reject_reason",
    "score_breakdown",
]


def build_audit_row(row: dict[str, Any], result: CompositeResult) -> dict[str, Any]:
    """Flatten CompositeResult + lead dict into one CSV-serialisable dict."""
    return {
        "email": row.get("Email") or row.get("email") or "",
        "company": row.get("Company") or row.get("name") or "",
        "website": row.get("Website") or row.get("site") or row.get("website") or "",
        "city": row.get("City") or row.get("city") or "",
        "taxonomy_score": result.taxonomy.score,
        "taxonomy_include": ", ".join(result.taxonomy.matched_include),
        "taxonomy_exclude": ", ".join(result.taxonomy.matched_exclude),
        "website_score": result.website.score,
        "website_text_len": result.website.detail.get("text_len", ""),
        "website_include": ", ".join(result.website.matched_include),
        "website_soft_exclude": ", ".join(result.website.matched_exclude),
        "website_error": result.website.error or "",
        "review_score": result.review.score,
        "review_count": result.review.detail.get("review_count", ""),
        "review_avg_rating": result.review.detail.get("avg_rating", ""),
        "review_icp": ", ".join(result.review.matched_include),
        "review_anti_icp": ", ".join(result.review.matched_exclude),
        "registry_score": result.registry.score,
        "composite_score": result.score,
        "verdict": result.verdict,
        "reject_reason": result.reject_reason,
        "score_breakdown": json.dumps(result.score_breakdown, ensure_ascii=False),
    }


def append_audit_rows(audit_rows: list[dict[str, Any]], audit_path: str) -> None:
    """Append rows to ingester_audit.csv (create with header if missing)."""
    if not audit_rows:
        return
    os.makedirs(os.path.dirname(audit_path) or ".", exist_ok=True)
    write_header = not os.path.isfile(audit_path) or os.path.getsize(audit_path) == 0
    with open(audit_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in audit_rows:
            writer.writerow({col: row.get(col, "") for col in AUDIT_COLUMNS})


_BORDERLINE_COLUMNS = [
    "Email",
    "Company",
    "Website",
    "City",
    "Type",
    "Category",
    "Subtypes",
    "Service",
    "Niche",
    "Subniche",
    "_ingester_score",
    "_ingester_verdict",
]


def append_borderline_rows(rows: list[dict[str, Any]], borderline_path: str) -> None:
    """Append borderline rows (lead dict subset) to borderline.csv."""
    if not rows:
        return
    os.makedirs(os.path.dirname(borderline_path) or ".", exist_ok=True)
    write_header = (
        not os.path.isfile(borderline_path) or os.path.getsize(borderline_path) == 0
    )
    with open(borderline_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BORDERLINE_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in _BORDERLINE_COLUMNS})
