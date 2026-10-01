#!/usr/bin/env python3
"""CLI — analyze filter_audit.csv for a preset (reason + taxonomy buckets)."""

from __future__ import annotations

import argparse
import os
import sys

_SCRAPER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

from audit_filter import run_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze filter_audit.csv — reason breakdown and taxonomy classification.",
    )
    parser.add_argument(
        "--preset",
        default="cabinets_expertise_comptable_fresh_geo",
        help="Preset id (default: cabinets_expertise_comptable_fresh_geo)",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Override output directory (default: output/{preset})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also write audit_filter_report.json",
    )
    parser.add_argument(
        "--no-review-csv",
        action="store_true",
        help="Skip writing taxonomy_review.csv for borderline rows",
    )
    args = parser.parse_args()

    out_dir = args.out_dir.strip() or None
    try:
        report = run_audit(
            args.preset,
            out_dir=out_dir,
            write_review=not args.no_review_csv,
            write_json=args.json,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(report["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
