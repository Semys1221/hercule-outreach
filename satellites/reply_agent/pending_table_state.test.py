"""Tests for pending draft session-state helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pending_table_state import (
    apply_pending_draft,
    draft_pending_key,
    ensure_draft,
    queue_draft_update,
    reply_draft_key,
)


class PendingDraftStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campaign_id = "camp-1"
        self.lead_email = "hello@stoory.fr"
        self.session: dict[str, object] = {}

    def _patch_session(self):
        return patch(
            "pending_table_state.st.session_state",
            self.session,
        )

    def test_queue_and_apply_pending_draft(self) -> None:
        with self._patch_session():
            queue_draft_update(self.campaign_id, self.lead_email, "Generated reply")

            applied = apply_pending_draft(self.campaign_id, self.lead_email)

        self.assertTrue(applied)
        draft_key = reply_draft_key(self.campaign_id, self.lead_email)
        pending_key = draft_pending_key(self.campaign_id, self.lead_email)
        self.assertEqual(self.session[draft_key], "Generated reply")
        self.assertNotIn(pending_key, self.session)

    def test_apply_pending_draft_returns_false_when_empty(self) -> None:
        with self._patch_session():
            applied = apply_pending_draft(self.campaign_id, self.lead_email)

        self.assertFalse(applied)

    def test_ensure_draft_applies_pending_first(self) -> None:
        with self._patch_session():
            queue_draft_update(self.campaign_id, self.lead_email, "Pending wins")
            ensure_draft(self.campaign_id, self.lead_email, "Default draft")

        draft_key = reply_draft_key(self.campaign_id, self.lead_email)
        self.assertEqual(self.session[draft_key], "Pending wins")

    def test_ensure_draft_keeps_existing_draft(self) -> None:
        draft_key = reply_draft_key(self.campaign_id, self.lead_email)
        self.session[draft_key] = "User edit"

        with self._patch_session():
            ensure_draft(self.campaign_id, self.lead_email, "Default draft")

        self.assertEqual(self.session[draft_key], "User edit")

    def test_ensure_draft_seeds_default_when_missing(self) -> None:
        with self._patch_session():
            ensure_draft(self.campaign_id, self.lead_email, "Default draft")

        draft_key = reply_draft_key(self.campaign_id, self.lead_email)
        self.assertEqual(self.session[draft_key], "Default draft")


if __name__ == "__main__":
    unittest.main()
