"""Recovery reply gate — mirrors lib/ai-reply-agent/reply-gate.ts."""

from __future__ import annotations

from typing import Any, TypedDict

RECOVERY_CONFIDENCE_THRESHOLD = 70

INTERESTED_STATUS = 1
NOT_INTERESTED_STATUS = -1
NO_SHOW_STATUS = -4


class ReplyGateResult(TypedDict):
    allow_reply: bool
    ai_status: str
    reason: str


def is_recovery_interest_tag(status: int | None) -> bool:
    if status in (INTERESTED_STATUS, NOT_INTERESTED_STATUS, NO_SHOW_STATUS):
        return False
    return True


def apply_reply_gate(
    interest_status: int | None,
    decision: dict[str, Any],
) -> ReplyGateResult:
    has_text = bool(decision.get("should_reply") and str(decision.get("reply_text") or "").strip())

    if not has_text:
        return {
            "allow_reply": False,
            "ai_status": "skipped_unsafe",
            "reason": str(decision.get("reason") or ""),
        }

    if not is_recovery_interest_tag(interest_status):
        return {
            "allow_reply": True,
            "ai_status": "auto_replied",
            "reason": str(decision.get("reason") or ""),
        }

    confidence = decision.get("recovery_confidence")
    if confidence is None or not isinstance(confidence, (int, float)):
        return {
            "allow_reply": False,
            "ai_status": "skipped_recovery",
            "reason": "recovery_confidence manquant pour tag Lead",
        }

    confidence_value = float(confidence)
    if confidence_value < RECOVERY_CONFIDENCE_THRESHOLD:
        return {
            "allow_reply": False,
            "ai_status": "skipped_recovery",
            "reason": (
                f"Confiance récupération {round(confidence_value)}% "
                f"< {RECOVERY_CONFIDENCE_THRESHOLD}%"
            ),
        }

    return {
        "allow_reply": True,
        "ai_status": "auto_replied",
        "reason": str(decision.get("reason") or ""),
    }
