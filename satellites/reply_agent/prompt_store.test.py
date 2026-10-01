"""Tests for prompt_store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prompt_store import (
    can_push_prompt_to_prod,
    prompt_file_path,
    save_prompt,
    write_prompt_file,
)


class PromptStoreTests(unittest.TestCase):
    def test_write_prompt_file_creates_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            import prompt_store as module

            original = module.prompts_dir
            module.prompts_dir = lambda: prompts_dir  # type: ignore[assignment]
            try:
                write_prompt_file("comptables", "buyer", "Test prompt body")
                path = prompt_file_path("comptables", "buyer")
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_text(encoding="utf-8"), "Test prompt body")
            finally:
                module.prompts_dir = original  # type: ignore[assignment]

    def test_can_push_prompt_to_prod_active_campaign(self) -> None:
        config = {
            "status": "waiting_for_replies",
            "initialized_at": "2026-01-01T00:00:00Z",
            "prompt_key": "comptables_buyer",
            "niche_preset_id": "comptables",
            "target_type": "buyer",
            "webhook_id": "wh1",
            "ooo_webhook_id": "wh2",
        }
        ok, reason = can_push_prompt_to_prod(
            config,
            "campaign-1",
            "comptables",
            "buyer",
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_can_push_prompt_to_prod_rejects_inactive(self) -> None:
        config = {
            "status": "not_initialized",
            "prompt_key": "comptables_buyer",
        }
        ok, reason = can_push_prompt_to_prod(
            config,
            "campaign-1",
            "comptables",
            "buyer",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "not_active")

    def test_save_prompt_writes_file_only_when_not_pushable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            import prompt_store as module

            original_prompts_dir = module.prompts_dir
            original_save_config = module.save_config
            module.prompts_dir = lambda: prompts_dir  # type: ignore[assignment]
            module.save_config = lambda row: None  # type: ignore[assignment]
            try:
                result = save_prompt(
                    "comptables",
                    "buyer",
                    "Draft prompt",
                    campaign_id="campaign-1",
                    config={"status": "not_initialized", "prompt_key": "comptables_buyer"},
                )
                self.assertTrue(result["file"])
                self.assertFalse(result["prod"])
                self.assertEqual(result["reason"], "not_active")
            finally:
                module.prompts_dir = original_prompts_dir  # type: ignore[assignment]
                module.save_config = original_save_config  # type: ignore[assignment]

    def test_save_prompt_pushes_prod_for_active_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            import prompt_store as module

            original_prompts_dir = module.prompts_dir
            original_save_config = module.save_config
            saved_rows: list[dict] = []

            module.prompts_dir = lambda: prompts_dir  # type: ignore[assignment]

            def capture_save(row: dict) -> None:
                saved_rows.append(dict(row))

            module.save_config = capture_save  # type: ignore[assignment]
            try:
                config = {
                    "campaign_id": "campaign-1",
                    "status": "waiting_for_replies",
                    "initialized_at": "2026-01-01T00:00:00Z",
                    "prompt_key": "comptables_buyer",
                    "niche_preset_id": "comptables",
                    "target_type": "buyer",
                    "prompt_snapshot": "Old prompt",
                }
                result = save_prompt(
                    "comptables",
                    "buyer",
                    "Updated prod prompt",
                    campaign_id="campaign-1",
                    config=config,
                )
                self.assertTrue(result["file"])
                self.assertTrue(result["prod"])
                self.assertIsNone(result["reason"])
                self.assertEqual(len(saved_rows), 1)
                self.assertEqual(saved_rows[0]["prompt_snapshot"], "Updated prod prompt")
                self.assertEqual(
                    (prompts_dir / "comptables_buyer.md").read_text(encoding="utf-8"),
                    "Updated prod prompt",
                )
            finally:
                module.prompts_dir = original_prompts_dir  # type: ignore[assignment]
                module.save_config = original_save_config  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
