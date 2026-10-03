"""Weighted composite scorer — pure function, no I/O."""

from __future__ import annotations

from typing import Any

from lead_ingester.models import CompositeResult, SignalResult

_DEFAULT_WEIGHTS = {
    "taxonomy": 0.20,
    "website": 0.40,
    "review": 0.25,
    "registry": 0.15,
}


def compute_score(
    taxonomy: SignalResult,
    website: SignalResult,
    review: SignalResult,
    registry: SignalResult,
    config: dict[str, Any],
) -> CompositeResult:
    """Combine four SignalResults into a CompositeResult with ACCEPT/BORDERLINE/REJECT."""
    signals = {
        "taxonomy": taxonomy,
        "website": website,
        "review": review,
        "registry": registry,
    }

    for name, sig in signals.items():
        if sig.hard_reject:
            exclude_hint = ",".join(sig.matched_exclude) if sig.matched_exclude else ""
            reason = f"hard_reject:{name}"
            if exclude_hint:
                reason = f"{reason}:{exclude_hint}"
            return CompositeResult(
                score=0.0,
                verdict="REJECT",
                reject_reason=reason,
                score_breakdown={},
                taxonomy=taxonomy,
                website=website,
                review=review,
                registry=registry,
            )

    weights = dict(config.get("INGESTER_SIGNAL_WEIGHTS") or _DEFAULT_WEIGHTS)
    # Normalise in case preset weights don't sum to 1
    total_w = sum(float(weights.get(k, 0.0)) for k in _DEFAULT_WEIGHTS) or 1.0
    breakdown: dict[str, float] = {}
    composite = 0.0
    for name, sig in signals.items():
        w = float(weights.get(name, _DEFAULT_WEIGHTS[name])) / total_w
        contribution = w * float(sig.score)
        breakdown[name] = round(contribution, 4)
        composite += contribution

    composite = max(0.0, min(1.0, composite))
    min_score = float(config.get("INGESTER_MIN_SCORE", 0.60))
    borderline_min = float(config.get("INGESTER_BORDERLINE_MIN", 0.40))

    if composite >= min_score:
        verdict = "ACCEPT"
        reject_reason = ""
    elif composite >= borderline_min:
        verdict = "BORDERLINE"
        reject_reason = f"score:{composite:.2f}"
    else:
        verdict = "REJECT"
        reject_reason = f"score:{composite:.2f}"

    return CompositeResult(
        score=round(composite, 4),
        verdict=verdict,
        reject_reason=reject_reason,
        score_breakdown=breakdown,
        taxonomy=taxonomy,
        website=website,
        review=review,
        registry=registry,
    )
