"""Tests for editor history SQLite layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db import (
    DOMAIN_REPLY_PROMPT,
    DOMAIN_SUBSEQUENCE,
    ensure_seeded_from_current,
    insert_version,
    list_versions,
    promote_version,
    resolve_niche_key,
    set_active_version,
)


class EditorHistoryDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_resolve_niche_key_prefers_preset(self) -> None:
        self.assertEqual(resolve_niche_key("camp-1", "avocats"), "avocats")
        self.assertEqual(resolve_niche_key("camp-1", None), "campaign:camp-1")

    def test_insert_and_list_versions(self) -> None:
        vid = insert_version(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="avocats",
            item_key="interested_email1",
            body_text="<p>E1</p>",
            campaign_id="camp-1",
            label="v1",
            db_path=self.db_path,
        )
        self.assertGreater(vid, 0)
        rows = list_versions(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="avocats",
            item_key="interested_email1",
            db_path=self.db_path,
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_active"])
        self.assertEqual(rows[0]["body_text"], "<p>E1</p>")

    def test_set_active_version_single_active(self) -> None:
        v1 = insert_version(
            domain=DOMAIN_REPLY_PROMPT,
            niche_key="comptables",
            item_key="buyer",
            body_text="Prompt A",
            db_path=self.db_path,
        )
        v2 = insert_version(
            domain=DOMAIN_REPLY_PROMPT,
            niche_key="comptables",
            item_key="buyer",
            body_text="Prompt B",
            db_path=self.db_path,
        )
        set_active_version(v1, db_path=self.db_path)
        rows = list_versions(
            domain=DOMAIN_REPLY_PROMPT,
            niche_key="comptables",
            item_key="buyer",
            db_path=self.db_path,
        )
        active_ids = [r["id"] for r in rows if r["is_active"]]
        self.assertEqual(active_ids, [v1])

        row_v2 = next(r for r in rows if r["id"] == v2)
        self.assertFalse(row_v2["is_active"])

    def test_promote_calls_push_and_sets_active(self) -> None:
        v1 = insert_version(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="jum",
            item_key="interested_email2",
            body_text="Old E2",
            db_path=self.db_path,
        )
        insert_version(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="jum",
            item_key="interested_email2",
            body_text="New E2",
            db_path=self.db_path,
        )
        pushed: list[dict] = []

        def push(row: dict) -> None:
            pushed.append(dict(row))

        promote_version(v1, push_to_prod=push, db_path=self.db_path)
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]["body_text"], "Old E2")
        rows = list_versions(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="jum",
            item_key="interested_email2",
            db_path=self.db_path,
        )
        active = [r for r in rows if r["is_active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], v1)

    def test_ensure_seeded_skips_when_history_exists(self) -> None:
        insert_version(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="x",
            item_key="interested_email1",
            body_text="a",
            db_path=self.db_path,
        )
        seeded = ensure_seeded_from_current(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="x",
            item_key="interested_email1",
            body_text="b",
            db_path=self.db_path,
        )
        self.assertFalse(seeded)
        rows = list_versions(
            domain=DOMAIN_SUBSEQUENCE,
            niche_key="x",
            item_key="interested_email1",
            db_path=self.db_path,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["body_text"], "a")

    def test_ensure_seeded_imports_when_empty(self) -> None:
        seeded = ensure_seeded_from_current(
            domain=DOMAIN_REPLY_PROMPT,
            niche_key="y",
            item_key="seller",
            body_text="Initial",
            db_path=self.db_path,
        )
        self.assertTrue(seeded)
        rows = list_versions(
            domain=DOMAIN_REPLY_PROMPT,
            niche_key="y",
            item_key="seller",
            db_path=self.db_path,
        )
        self.assertEqual(rows[0]["label"], "Import automatique")


if __name__ == "__main__":
    unittest.main()
