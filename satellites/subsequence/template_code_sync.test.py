"""Tests for subsequence template_code_sync."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from template_code_sync import DEFAULT_TEMPLATES_PATH, sync_e1_bootstrap_default


class SubsequenceTemplateCodeSyncTests(unittest.TestCase):
    def test_sync_e1_bootstrap_default_on_temp_copy(self) -> None:
        marker = "SYNC_TEST_MARKER_UNIQUE_E1"
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "default_templates.py"
            shutil.copy(DEFAULT_TEMPLATES_PATH, target)
            sync_e1_bootstrap_default(f"<p>{marker}</p>", path=target)
            self.assertIn(marker, target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
