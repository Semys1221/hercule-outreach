#!/usr/bin/env python3
"""Push all preset CSV backlog to Instantly (duplicate skip, no link provision)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "lib" / "backend" / "streamlit_scraper"))

from config_loader import PRESETS, load_config  # noqa: E402
from instantly_client import push_csv_to_instantly  # noqa: E402

DEFAULT_PRESETS = [
    "agences_ecommerce",
    "boutiques_ecommerce",
    "btp_pme",
    "cabinets_conseiller_financier",
    "cabinets_expertise_comptable_fresh_geo",
    "chirurgiens_dentistes",
    "courtiers_prevoyance_b2b",
    "medecins_generalistes",
    "restaurants_independants",
    "terrassement_vrd",
]
VOL_CSV_PRESET = "cabinets_expertise_comptable_fresh_geo"
VOL_CSV_DIR = "cabinets_expertise_comptable_vol"


def output_base() -> Path:
    root = os.getenv("HERCULE_DATA_ROOT", "/var/lib/hercule").strip()
    return Path(root) / "streamlit_scraper" / "output"


def log(message: str) -> None:
    print(message, flush=True)


async def push_preset(preset: str, *, provision_links: bool) -> dict[str, int] | None:
    csv_path = output_base() / preset / "outscraper_leads.csv"
    if not csv_path.is_file():
        log(f"SKIP {preset} — no CSV")
        return None

    config = load_config(preset, require_keys=False)
    config["INSTANTLY_PROVISION_LINKS"] = provision_links
    log(f"--- {preset} → list {config.get('INSTANTLY_LIST_ID', '')[:8]}… ---")
    summary = await push_csv_to_instantly(
        str(csv_path),
        config["INSTANTLY_API_KEY"],
        config["INSTANTLY_LIST_ID"],
        log_cb=log,
        provision_config=config,
    )
    log(
        f"RESULT {preset}: pushed={summary.get('pushed', 0)} "
        f"skipped={summary.get('skipped_duplicate', 0)} "
        f"failed={summary.get('failed', 0)}"
    )
    return summary


async def push_vol_csv(*, provision_links: bool) -> dict[str, int] | None:
    csv_path = output_base() / VOL_CSV_DIR / "outscraper_leads.csv"
    if not csv_path.is_file():
        log("SKIP vol CSV — file missing")
        return None

    config = load_config(VOL_CSV_PRESET, require_keys=False)
    config["INSTANTLY_PROVISION_LINKS"] = provision_links
    log(f"--- {VOL_CSV_DIR} (via {VOL_CSV_PRESET}) ---")
    summary = await push_csv_to_instantly(
        str(csv_path),
        config["INSTANTLY_API_KEY"],
        config["INSTANTLY_LIST_ID"],
        log_cb=log,
        provision_config=config,
    )
    log(
        f"RESULT vol: pushed={summary.get('pushed', 0)} "
        f"skipped={summary.get('skipped_duplicate', 0)} "
        f"failed={summary.get('failed', 0)}"
    )
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        action="append",
        dest="presets",
        help="Preset to push (repeatable). Default: all presets with CSV on disk.",
    )
    parser.add_argument(
        "--include-vol",
        action="store_true",
        help="Also push deprecated comptable vol CSV via fresh-geo list.",
    )
    parser.add_argument(
        "--provision-links",
        action="store_true",
        help="Provision tracking links after push (slow; off by default).",
    )
    args = parser.parse_args()

    if args.presets:
        presets = [p for p in args.presets if p in PRESETS]
        unknown = [p for p in args.presets if p not in PRESETS]
        for preset in unknown:
            log(f"WARN unknown preset {preset!r}")
    else:
        presets = [p for p in sorted(PRESETS) if (output_base() / p / "outscraper_leads.csv").is_file()]

    totals = {"pushed": 0, "skipped_duplicate": 0, "failed": 0}
    for preset in presets:
        summary = await push_preset(preset, provision_links=args.provision_links)
        if summary:
            for key in totals:
                totals[key] += int(summary.get(key) or 0)

    if args.include_vol:
        summary = await push_vol_csv(provision_links=args.provision_links)
        if summary:
            for key in totals:
                totals[key] += int(summary.get(key) or 0)

    log(
        f"TOTAL: pushed={totals['pushed']} "
        f"skipped={totals['skipped_duplicate']} failed={totals['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
