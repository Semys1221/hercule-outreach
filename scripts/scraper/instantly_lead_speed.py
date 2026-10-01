#!/usr/bin/env python3
"""Sample Instantly live list growth and print a one-line speed summary."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, os.path.join(REPO, "lib", "backend", "streamlit_scraper"))

from config_loader import load_config  # noqa: E402
from scrape_metrics import fetch_instantly_live  # noqa: E402
from verify_vps_helpers import compute_rate_per_hour  # noqa: E402

DEFAULT_PRESET = "cabinets_expertise_comptable_fresh_geo"


def format_speed_line(
    *,
    per_hour: float,
    per_day: float,
    end_count: int,
    delta: int,
    sample_minutes: float,
) -> str:
    """Plain-English one-liner for terminal output."""
    return (
        f"Speed count: {per_hour:.0f} leads/hour on Instantly | "
        f"{per_day:.0f} leads/day "
        f"(list: {end_count}, +{delta} in {sample_minutes:.0f} min)"
    )


def sample_instantly_speed(
    config: dict,
    *,
    sample_minutes: float,
    poll_seconds: float,
) -> dict[str, Any]:
    """Poll Instantly live list count over a window; return rate metrics."""
    duration_s = max(sample_minutes * 60.0, poll_seconds)
    polls = max(int(duration_s / poll_seconds), 1)

    start_count = fetch_instantly_live(config, use_cache=False)
    if start_count is None:
        raise RuntimeError("Could not read Instantly live list count (check API key and list ID).")

    started = time.monotonic()
    end_count = start_count

    for index in range(polls):
        if index + 1 < polls:
            time.sleep(poll_seconds)
        live = fetch_instantly_live(config, use_cache=False)
        if live is not None:
            end_count = live

    elapsed_s = time.monotonic() - started
    if elapsed_s <= 0:
        raise RuntimeError("Sample window too short.")

    delta = end_count - start_count
    per_hour = compute_rate_per_hour(delta, elapsed_s)
    if per_hour is None:
        raise RuntimeError("Could not compute leads per hour.")

    per_day = per_hour * 24.0
    return {
        "preset": str(config.get("PRESET_ID") or ""),
        "list_id": str(config.get("INSTANTLY_LIST_ID") or ""),
        "live_start": start_count,
        "live_end": end_count,
        "delta": delta,
        "elapsed_s": elapsed_s,
        "sample_minutes": elapsed_s / 60.0,
        "per_hour": per_hour,
        "per_day": per_day,
        "line": format_speed_line(
            per_hour=per_hour,
            per_day=per_day,
            end_count=end_count,
            delta=delta,
            sample_minutes=elapsed_s / 60.0,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure Instantly live list growth (leads/hour and leads/day)."
    )
    parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        help=f"Scraper preset (default: {DEFAULT_PRESET})",
    )
    parser.add_argument(
        "--sample-minutes",
        type=float,
        default=5.0,
        help="Sample window in minutes (default: 5)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=30.0,
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of one line")
    args = parser.parse_args()

    if args.sample_minutes <= 0:
        print("sample-minutes must be > 0", file=sys.stderr)
        return 1
    if args.poll_seconds <= 0:
        print("poll-seconds must be > 0", file=sys.stderr)
        return 1

    config = load_config(args.preset, require_keys=False)
    try:
        result = sample_instantly_speed(
            config,
            sample_minutes=args.sample_minutes,
            poll_seconds=args.poll_seconds,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
