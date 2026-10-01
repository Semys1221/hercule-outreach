#!/usr/bin/env python3
"""Prepare niche scrape presets (Instantly + configs) in queue order — does not start workers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
SCRAPER = REPO / "lib" / "backend" / "streamlit_scraper"
load_dotenv(REPO / ".env")
sys.path.insert(0, str(SCRAPER))
sys.path.insert(0, str(REPO / "lib" / "backend"))
sys.path.insert(0, str(REPO))

from bootstrap.provision import provision_preset  # noqa: E402
from bootstrap.vps_control import VpsConfig, _ssh_exec  # noqa: E402
from config_loader import load_config  # noqa: E402
from configs.niche_queue import NICHE_SCRAPE_QUEUE  # noqa: E402


def _stop_vps_scrapers() -> dict[str, str]:
    cfg = VpsConfig.from_env()
    if not cfg:
        return {"vps": "not configured"}
    cmd = (
        "for u in $(systemctl list-units --type=service --all --no-legend 'hercule-scraper*.service' "
        "| awk '{print $1}' | grep -v heal | grep -v exporter); do "
        "sudo systemctl stop \"$u\" 2>/dev/null || true; done; "
        "systemctl list-units --type=service --state=active 'hercule-scraper*.service' --no-pager --plain "
        "| grep -v heal || echo none"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=60)
    return {"stopped": "ok" if code == 0 else err or out, "active_after": out.strip()}


def main() -> int:
    import os

    api_key = str(os.getenv("INSTANTLY_API_KEY") or "").strip()
    if not api_key:
        sample = load_config(NICHE_SCRAPE_QUEUE[0]["preset_id"], require_keys=False)
        api_key = str(sample.get("INSTANTLY_API_KEY") or "").strip()
    if not api_key:
        print("INSTANTLY_API_KEY required", file=sys.stderr)
        return 1

    results: list[dict] = []
    for entry in NICHE_SCRAPE_QUEUE:
        preset_id = entry["preset_id"]
        try:
            result = provision_preset(preset_id, api_key=api_key)
            result["queue_rank"] = entry["rank"]
            result["notes"] = entry["notes"]
            results.append(result)
        except Exception as exc:
            results.append(
                {
                    "preset_id": preset_id,
                    "queue_rank": entry["rank"],
                    "error": str(exc),
                }
            )

    vps = _stop_vps_scrapers()
    print(json.dumps({"provision": results, "vps": vps}, indent=2, default=str))
    failed = any(r.get("error") for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
