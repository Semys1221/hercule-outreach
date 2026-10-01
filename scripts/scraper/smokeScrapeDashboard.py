#!/usr/bin/env python3
"""One-shot Playwright smoke test for Streamlit Scrape page (VPS remote metrics)."""

from __future__ import annotations

import os
import re
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, os.path.join(REPO, "lib", "backend", "streamlit_scraper"))

from bootstrap.vps_control import remote_csv_lead_count, vps_configured, worker_status  # noqa: E402
from vps_defaults import DEFAULT_VPS_HOST, vps_ssh_target  # noqa: E402
from config_loader import load_config  # noqa: E402
from scrape_metrics import fetch_instantly_live  # noqa: E402


def main() -> int:
    preset = "cabinets_expertise_comptable"
    base_url = os.getenv("STREAMLIT_SCRAPER_URL", "http://localhost:8504")
    scrape_url = f"{base_url}/Scrape?preset={preset}"

    cfg = load_config(preset, require_keys=False)
    expected_live = fetch_instantly_live(cfg)
    expected_csv = remote_csv_lead_count(preset)
    vps = worker_status()

    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(base_url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(3000)
        scrape_link = page.get_by_role("link", name=re.compile("Scrape", re.I))
        if scrape_link.count():
            scrape_link.first.click()
            page.wait_for_timeout(3000)
        if preset:
            preset_select = page.locator('[data-testid="stSelectbox"] >> nth=0')
            if preset_select.count():
                preset_select.click()
                page.get_by_text(preset, exact=False).first.click()
        try:
            page.get_by_text("Instantly (live)", exact=False).first.wait_for(timeout=90_000)
        except Exception:
            try:
                page.get_by_text("Contrôles", exact=False).first.wait_for(timeout=30_000)
            except Exception:
                page.wait_for_timeout(45_000)

        body = page.locator("body").inner_text()

        if vps_ssh_target() not in body and DEFAULT_VPS_HOST not in body:
            errors.append("VPS host caption missing from Scrape page")
        if "Scrape — operations panel" not in body:
            errors.append("Scrape panel title missing")
        if expected_live is not None and str(expected_live) not in body.replace(",", "").replace(" ", ""):
            errors.append(f"Instantly live {expected_live} not visible in UI")
        if expected_csv:
            body_nums = body.replace(",", "")
            if (
                str(expected_csv) not in body_nums
                and str(expected_csv - 1) not in body_nums
                and str(expected_csv + 1) not in body_nums
            ):
                errors.append(f"Remote CSV count ~{expected_csv} not visible in UI")
        if vps.get("active") and "Running on VPS" not in body:
            errors.append("Expected 'Running on VPS' worker status")

        refresh = page.get_by_role("button", name="Actualiser")
        if refresh.count() == 0:
            errors.append("Actualiser button not found")
        else:
            refresh.first.click()
            page.wait_for_timeout(3000)

        vps_after_pause = vps
        pause = page.get_by_role("button", name="Pause")
        if pause.count() == 0:
            errors.append("Pause button not found")
        else:
            pause.first.click()
            page.wait_for_timeout(12_000)
            vps_after_pause = worker_status()
            if vps_after_pause.get("active"):
                errors.append("VPS worker still active after Pause click")

        start = page.get_by_role("button", name="Démarrer / Continuer")
        if start.count() == 0:
            errors.append("Démarrer / Continuer button not found")
        elif not vps_after_pause.get("active"):
            start.first.click()
            page.wait_for_timeout(8_000)
            vps_after_start = worker_status()
            if not vps_after_start.get("active"):
                errors.append("VPS worker not active after Démarrer / Continuer click")
        else:
            errors.append("Skipped start test because Pause did not stop worker")

        if "Push CSV to Instantly" in body and vps_configured():
            errors.append("Push CSV button should be hidden when VPS is configured")

        browser.close()

    print("=== Scrape dashboard smoke ===")
    print(f"URL: {scrape_url}")
    print(f"Instantly live (API): {expected_live}")
    print(f"Remote CSV: {expected_csv}")
    print(f"VPS active: {vps.get('active')}")
    if errors:
        debug_path = "/tmp/scrape-dashboard-smoke.txt"
        with open(debug_path, "w", encoding="utf-8") as handle:
            handle.write(body[:8000])
        print(f"Debug body saved to {debug_path}")
        print("FAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("PASS — UI matches VPS metrics; controls exercised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
