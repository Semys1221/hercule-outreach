"""Tests for reply_gate recovery threshold."""

from __future__ import annotations

import unittest

from reply_gate import (
    RECOVERY_CONFIDENCE_THRESHOLD,
    apply_reply_gate,
    is_recovery_interest_tag,
)


class ReplyGateTests(unittest.TestCase):
    def test_recovery_tags(self) -> None:
        self.assertTrue(is_recovery_interest_tag(None))
        self.assertTrue(is_recovery_interest_tag(0))
        self.assertFalse(is_recovery_interest_tag(-1))
        self.assertFalse(is_recovery_interest_tag(1))
        self.assertFalse(is_recovery_interest_tag(-4))

    def test_lead_recovery_below_threshold(self) -> None:
        result = apply_reply_gate(
            None,
            {
                "should_reply": True,
                "reply_text": "Bonjour",
                "reason": "low",
                "recovery_confidence": RECOVERY_CONFIDENCE_THRESHOLD - 1,
            },
        )
        self.assertFalse(result["allow_reply"])
        self.assertEqual(result["ai_status"], "skipped_recovery")

    def test_lead_recovery_at_threshold(self) -> None:
        result = apply_reply_gate(
            None,
            {
                "should_reply": True,
                "reply_text": "Bonjour",
                "reason": "ok",
                "recovery_confidence": RECOVERY_CONFIDENCE_THRESHOLD,
            },
        )
        self.assertTrue(result["allow_reply"])

    def test_interested_bypasses_threshold(self) -> None:
        result = apply_reply_gate(
            1,
            {
                "should_reply": True,
                "reply_text": "Bonjour",
                "reason": "ok",
                "recovery_confidence": 10,
            },
        )
        self.assertTrue(result["allow_reply"])


if __name__ == "__main__":
    unittest.main()
