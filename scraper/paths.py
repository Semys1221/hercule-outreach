"""Output paths for scraper preset data (UI + VPS read)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_LIB_DIR)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
from outreach_data import scraper_output_base  # noqa: E402


@dataclass(frozen=True)
class OutputPaths:
    out_dir: str
    csv: str
    raw_jsonl: str
    filter_audit: str
    enrich_audit: str
    metrics: str
    scrape_state: str
    workspace_cache: str
    ingester_audit: str
    borderline: str
    email_recovery: str
    mev_emails: str


def output_paths(preset: str = "biggy_agency") -> OutputPaths:
    out_dir = os.path.join(scraper_output_base(), preset)
    os.makedirs(out_dir, exist_ok=True)
    return OutputPaths(
        out_dir=out_dir,
        csv=os.path.join(out_dir, "outscraper_leads.csv"),
        raw_jsonl=os.path.join(out_dir, "outscraper_raw.jsonl"),
        filter_audit=os.path.join(out_dir, "filter_audit.csv"),
        enrich_audit=os.path.join(out_dir, "enrich_audit.csv"),
        metrics=os.path.join(out_dir, "scrape_metrics.jsonl"),
        scrape_state=os.path.join(out_dir, "scrape_state.json"),
        workspace_cache=os.path.join(out_dir, "workspace_emails.json"),
        ingester_audit=os.path.join(out_dir, "ingester_audit.csv"),
        borderline=os.path.join(out_dir, "borderline.csv"),
        email_recovery=os.path.join(out_dir, "pending_email_recovery.jsonl"),
        mev_emails=os.path.join(out_dir, "mev_emails.csv"),
    )
