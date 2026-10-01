"""Tests for supabase_repo lead reply helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from supabase_repo import get_lead_reply, get_lead_replies_batch, upsert_lead_reply


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class LeadReplyRepoTests(unittest.TestCase):
    @patch("supabase_repo.get_client")
    def test_get_lead_reply_returns_trimmed_text(self, mock_get_client: MagicMock) -> None:
        table = MagicMock()
        chain = table.table.return_value
        chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            _FakeResponse({"ai_reply_agent_1": "  Hello  "})
        )
        mock_get_client.return_value = table

        self.assertEqual(get_lead_reply("camp-1", "Lead@Example.com"), "Hello")

    @patch("supabase_repo.get_client")
    def test_upsert_lead_reply_overwrites(self, mock_get_client: MagicMock) -> None:
        table = MagicMock()
        upsert = table.table.return_value.upsert
        mock_get_client.return_value = table

        upsert_lead_reply("camp-1", "a@b.com", "First draft")
        upsert_lead_reply("camp-1", "a@b.com", "Second draft")

        self.assertEqual(upsert.call_count, 2)
        last_row = upsert.call_args_list[-1][0][0]
        self.assertEqual(last_row["ai_reply_agent_1"], "Second draft")
        self.assertEqual(last_row["lead_email"], "a@b.com")

    @patch("supabase_repo.get_client")
    def test_get_lead_replies_batch(self, mock_get_client: MagicMock) -> None:
        table = MagicMock()
        chain = table.table.return_value
        chain.select.return_value.eq.return_value.in_.return_value.execute.return_value = (
            _FakeResponse(
                [
                    {"lead_email": "a@b.com", "ai_reply_agent_1": "Reply A"},
                    {"lead_email": "c@d.com", "ai_reply_agent_1": ""},
                ]
            )
        )
        mock_get_client.return_value = table

        result = get_lead_replies_batch("camp-1", ["a@b.com", "c@d.com"])
        self.assertEqual(result, {"a@b.com": "Reply A"})


if __name__ == "__main__":
    unittest.main()
