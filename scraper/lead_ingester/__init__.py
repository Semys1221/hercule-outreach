"""Lead ingester — second-stage qualification before Instantly push."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from lead_ingester.audit import append_audit_rows, append_borderline_rows, build_audit_row
from lead_ingester.fetcher import HEADERS, fetch_html
from lead_ingester.models import (
    NEUTRAL,
    CompositeResult,
    IngesterResult,
    SignalResult,
)
from lead_ingester.scorer import compute_score
from lead_ingester.signals.review_signal import score_reviews
from lead_ingester.signals.taxonomy_signal import score_taxonomy
from lead_ingester.signals.website_signal import score_website

__all__ = ["ingest_batch", "IngesterResult", "CompositeResult", "SignalResult"]


def _registry_signal(row: dict[str, Any]) -> SignalResult:
    lead_score = row.get("LeadScore")
    if lead_score is None or lead_score == "":
        lead_score = row.get("lead_score")
    if lead_score is None or lead_score == "":
        return NEUTRAL
    try:
        score = float(lead_score) / 100.0
    except (TypeError, ValueError):
        return NEUTRAL
    hard_reject = bool(row.get("_registry_hard_rejected", False))
    return SignalResult(score=max(0.0, min(1.0, score)), hard_reject=hard_reject)


def _website_url(row: dict[str, Any]) -> str:
    return str(
        row.get("Website") or row.get("site") or row.get("website") or ""
    ).strip()


async def _score_one(
    row: dict[str, Any],
    config: dict[str, Any],
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[dict[str, Any], CompositeResult]:
    taxonomy_sig = score_taxonomy(row, config)
    review_sig = score_reviews(row, config)

    url = _website_url(row)
    timeout = float(config.get("INGESTER_FETCH_TIMEOUT", 8.0))
    if url:
        html, err = await fetch_html(url, client, sem, timeout=timeout)
    else:
        html, err = None, "no_html"
    website_sig = score_website(html, config, err)
    registry_sig = _registry_signal(row)

    result = compute_score(
        taxonomy_sig, website_sig, review_sig, registry_sig, config
    )
    return row, result


def _collate(
    scored: list[tuple[dict[str, Any], CompositeResult] | BaseException],
    output_paths: Any,
) -> IngesterResult:
    accepted: list[dict] = []
    borderline: list[dict] = []
    rejected: list[dict] = []
    audit_rows: list[dict] = []

    for item in scored:
        if isinstance(item, BaseException):
            # Should not happen often — treat as reject with error reason
            continue
        row, result = item
        audit_rows.append(build_audit_row(row, result))
        row_copy = {
            **row,
            "_ingester_score": result.score,
            "_ingester_verdict": result.verdict,
        }
        if result.verdict == "ACCEPT":
            accepted.append(row_copy)
        elif result.verdict == "BORDERLINE":
            borderline.append(row_copy)
        else:
            row_copy["_ingester_reason"] = result.reject_reason
            rejected.append(row_copy)

    audit_path = getattr(output_paths, "ingester_audit", "") or ""
    borderline_path = getattr(output_paths, "borderline", "") or ""
    if audit_path:
        append_audit_rows(audit_rows, audit_path)
    if borderline_path:
        append_borderline_rows(borderline, borderline_path)

    return IngesterResult(
        accepted=accepted,
        borderline=borderline,
        rejected=rejected,
        audit_rows=audit_rows,
    )


async def ingest_batch(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    output_paths: Any,
) -> IngesterResult:
    """Score a batch of scraped leads and split into accept / borderline / reject."""
    if not rows:
        return IngesterResult(accepted=[], borderline=[], rejected=[], audit_rows=[])

    concurrency = max(int(config.get("INGESTER_CONCURRENCY", 10)), 1)
    sem = asyncio.Semaphore(concurrency)
    timeout = float(config.get("INGESTER_FETCH_TIMEOUT", 8.0))
    client_timeout = httpx.Timeout(timeout)

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=client_timeout,
    ) as client:
        tasks = [_score_one(row, config, client, sem) for row in rows]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return _collate(list(results), output_paths)
