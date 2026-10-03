"""Data contracts for the lead ingester pipeline. No project imports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignalResult:
    score: float  # 0.0–1.0 normalised
    hard_reject: bool = False  # True → reject regardless of composite score
    matched_include: list[str] = field(default_factory=list)
    matched_exclude: list[str] = field(default_factory=list)
    error: str | None = None  # "fetch_timeout", "parse_error", etc.
    detail: dict = field(default_factory=dict)  # signal-specific extras


NEUTRAL = SignalResult(score=0.5)  # sentinel for missing signal


@dataclass
class CompositeResult:
    score: float  # 0.0–1.0
    verdict: str  # "ACCEPT" | "BORDERLINE" | "REJECT"
    reject_reason: str  # "" if accept; machine-readable code otherwise
    score_breakdown: dict  # {"taxonomy": 0.18, "website": 0.32, ...}
    taxonomy: SignalResult = field(default_factory=lambda: NEUTRAL)
    website: SignalResult = field(default_factory=lambda: NEUTRAL)
    review: SignalResult = field(default_factory=lambda: NEUTRAL)
    registry: SignalResult = field(default_factory=lambda: NEUTRAL)


@dataclass
class IngesterResult:
    accepted: list[dict]  # rows ready for Instantly
    borderline: list[dict]  # soft zone — export to borderline.csv
    rejected: list[dict]  # rows with `_ingester_reason` key injected
    audit_rows: list[dict]  # one flat dict per lead for ingester_audit.csv
