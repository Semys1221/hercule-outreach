"""Tests for shared/mev_export.py"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from shared.mev_export import (
    extract_emails_from_dataframe,
    sync_mev_csv_from_leads_csv,
    validate_mev_upload_emails,
    write_mev_csv,
)

import pandas as pd


class MevExportTests(unittest.TestCase):
    def test_write_mev_csv_single_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mev.csv"
            count = write_mev_csv(
                ["User@Example.com", "bad", "user@example.com", "other@test.fr"],
                path,
            )
            self.assertEqual(count, 2)
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["email"])
            self.assertEqual(rows[1], ["user@example.com"])
            self.assertEqual(rows[2], ["other@test.fr"])

    def test_extract_from_instantly_style_export(self) -> None:
        df = pd.DataFrame(
            {
                "id": ["uuid-1"],
                "contact": ["dup@example.com"],
                "email": ["good@example.com"],
            }
        )
        emails = extract_emails_from_dataframe(df)
        self.assertEqual(emails, ["good@example.com"])

    def test_sync_from_scraper_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            leads = Path(tmp) / "outscraper_leads.csv"
            leads.write_text(
                "Email,Company\n"
                "Alpha@Example.COM,Acme\n"
                "invalid,Bad Co\n",
                encoding="utf-8",
            )
            count = sync_mev_csv_from_leads_csv(leads)
            self.assertEqual(count, 1)
            with (Path(tmp) / "mev_emails.csv").open(encoding="utf-8") as handle:
                mev_rows = list(csv.reader(handle))
            self.assertEqual(mev_rows, [["email"], ["alpha@example.com"]])

    def test_validate_mev_upload_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            validate_mev_upload_emails(["", "not-an-email"])


if __name__ == "__main__":
    unittest.main()
