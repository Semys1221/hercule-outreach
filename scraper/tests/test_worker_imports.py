"""Smoke test: import every headless worker module (no API calls)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRAPER_DIR = _REPO_ROOT / "scraper"
for path in (_SCRAPER_DIR, _REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


WORKER_MODULES = [
    "audit_filter",
    "category_filter",
    "core_logic",
    "outscraper_client",
    "query_planner",
    "taxonomy_gate",
    "website_verifier",
    "pool_filler",
    "supabase_leads_repo",
    "pappers_validator",
    "instantly_client",
    "scrape_state",
    "scrape_metrics",
    "scrape_log",
    "config_loader",
    "french_cities",
    "french_insee_communes",
    "french_postal_locations",
    "belgian_cities",
    "company_registry",
    "company_registry.validate",
    "lead_ingester",
    "monitoring.exporter",
]


@pytest.mark.parametrize("module_name", WORKER_MODULES)
def test_import_worker_module(module_name: str) -> None:
    importlib.import_module(module_name)
