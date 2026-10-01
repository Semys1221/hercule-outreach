#!/usr/bin/env python3
"""Recover MEV statuses from an interrupted single-email run (terminal log)."""

from __future__ import annotations

import argparse
import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from checkpoint import recover_checkpoint_from_log  # noqa: E402
from paths import data_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover verification checkpoint from legacy terminal output.",
    )
    parser.add_argument("log_path", help="Path to terminal log file")
    parser.add_argument(
        "--prefix",
        required=True,
        help="Artifact prefix for the interrupted job (e.g. 20260902_104321)",
    )
    parser.add_argument(
        "--total-target",
        type=int,
        default=None,
        help="Total emails in the job (for progress display)",
    )
    parser.add_argument(
        "--source-artifact",
        default=None,
        help="Path to quick_clean CSV for this job",
    )
    args = parser.parse_args()

    log_path = os.path.abspath(args.log_path)
    if not os.path.isfile(log_path):
        raise SystemExit(f"Log file not found: {log_path}")

    source_artifact = args.source_artifact
    if source_artifact is None:
        candidate = os.path.join(data_dir(), f"{args.prefix}_quick_clean.csv")
        if os.path.isfile(candidate):
            source_artifact = candidate

    path, status_map = recover_checkpoint_from_log(
        log_path,
        args.prefix,
        total_target=args.total_target,
        source_artifact=source_artifact,
    )
    print(f"Recovered {len(status_map)} verified email(s)")
    print(f"Checkpoint saved to: {path}")


if __name__ == "__main__":
    main()
