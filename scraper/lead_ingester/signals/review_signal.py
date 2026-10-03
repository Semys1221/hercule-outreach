"""Review signal — keyword + rating scoring on Outscraper reviews_data."""

from __future__ import annotations

import re
import statistics
from typing import Any

import ftfy

from lead_ingester.models import NEUTRAL, SignalResult


def _find_keywords(text: str, keywords: list[str]) -> list[str]:
    found: list[str] = []
    for kw in keywords:
        word = str(kw).strip().lower()
        if not word:
            continue
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            found.append(kw)
    return found


def score_reviews(row: dict[str, Any], config: dict[str, Any]) -> SignalResult:
    """Score a lead from Outscraper review text + ratings.

    Looks for ``reviews_data`` on the raw place dict, or ``_reviews_data``
    on a CSV-style lead row (preserved by core_logic when INGESTER_ENABLED).
    """
    reviews = row.get("reviews_data") or row.get("_reviews_data") or []
    if not isinstance(reviews, list) or not reviews:
        return NEUTRAL

    parts: list[str] = []
    ratings: list[float] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        blob = f"{review.get('review_text') or ''} {review.get('owner_answer') or ''}"
        parts.append(ftfy.fix_text(blob).lower())
        rating = review.get("review_rating")
        if rating is not None:
            try:
                ratings.append(float(rating))
            except (TypeError, ValueError):
                pass

    text = " ".join(parts)
    avg_rating = statistics.mean(ratings) if ratings else 3.0
    rating_score = (avg_rating - 1.0) / 4.0  # 1–5 → 0.0–1.0

    icp_keywords = list(config.get("INGESTER_REVIEW_ICP_KEYWORDS") or [])
    anti_keywords = list(config.get("INGESTER_REVIEW_ANTI_ICP_KEYWORDS") or [])
    icp_matches = _find_keywords(text, icp_keywords)
    anti_matches = _find_keywords(text, anti_keywords)

    keyword_score = min(len(icp_matches) / 3.0, 1.0)
    penalty = min(len(anti_matches) * 0.2, 0.5)
    score = max(0.0, min(1.0, rating_score * 0.4 + keyword_score * 0.6 - penalty))

    return SignalResult(
        score=score,
        matched_include=icp_matches,
        matched_exclude=anti_matches,
        detail={
            "review_count": len(reviews),
            "avg_rating": round(avg_rating, 2),
        },
    )
