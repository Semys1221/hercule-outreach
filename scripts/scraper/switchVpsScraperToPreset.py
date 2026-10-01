#!/usr/bin/env python3
"""Stop all VPS scrape workers and start one preset (rsync + install if needed)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
SCRAPER = REPO / "lib" / "backend" / "streamlit_scraper"
load_dotenv(REPO / ".env")
sys.path.insert(0, str(SCRAPER))
sys.path.insert(0, str(REPO / "lib" / "backend"))

from bootstrap.vps_control import VpsConfig, _ssh_exec  # noqa: E402

PRESET_SERVICES = {
    "avocats": "hercule-scraper-avocats",
    "agences_immobilieres": "hercule-scraper-agences-immobilieres",
    "hotels_independants": "hercule-scraper-hotels-independants",
    "medecine_esthetique": "hercule-scraper-medecine-esthetique",
    "cabinets_expertise_comptable_fresh_geo": "hercule-scraper-comptable-fresh-geo",
}


def stop_all_scrapers(cfg: VpsConfig) -> str:
    cmd = (
        "for u in $(systemctl list-unit-files 'hercule-scraper*.service' --no-legend "
        "| awk '{print $1}' | grep -v heal | grep -v exporter); do "
        "systemctl stop \"$u\" 2>/dev/null || true; done; "
        "systemctl list-units --type=service --state=active 'hercule-scraper*.service' "
        "--no-pager --plain | grep -v heal || echo none"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=90)
    if code != 0:
        raise RuntimeError(err or out or f"stop failed exit {code}")
    return out.strip()


def ensure_worker(cfg: VpsConfig, preset: str, service: str) -> str:
    repo = cfg.repo_root
    data = cfg.data_root
    install = (
        f"sudo VPS_SCRAPER_SERVICE={service} SCRAPER_PRESET={preset} "
        f"HERCULE_DATA_ROOT={data} VPS_REPO_ROOT={repo} "
        f"bash {repo}/scripts/vps/install-scraper.sh"
    )
    code, out, err = _ssh_exec(cfg, install, timeout=180)
    if code != 0:
        raise RuntimeError(err or out or "install failed")
    start = f"systemctl restart {service} && systemctl is-active {service}"
    code, out, err = _ssh_exec(cfg, start, timeout=60)
    if code != 0:
        raise RuntimeError(err or out or "start failed")
    return out.strip()


def rsync_scraper(cfg: VpsConfig) -> None:
    host = cfg.host
    user = cfg.user
    remote = f"{cfg.repo_root}/scraper/"
    local = str(SCRAPER) + "/"
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    cmd = [
        "rsync",
        "-az",
        "--exclude",
        ".pytest_cache",
        "--exclude",
        "output",
        "--exclude",
        "__pycache__",
        "-e",
        " ".join(ssh),
        local,
        f"{user}@{host}:{remote}",
    ]
    subprocess.run(cmd, check=True, cwd=str(REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset", choices=sorted(PRESET_SERVICES.keys()))
    parser.add_argument("--no-rsync", action="store_true")
    args = parser.parse_args()

    cfg = VpsConfig.from_env()
    if not cfg:
        print("VPS disabled (VPS_DISABLED) or SSH config unavailable", file=sys.stderr)
        return 1

    service = PRESET_SERVICES[args.preset]
    result: dict[str, object] = {"preset": args.preset, "service": service}
    try:
        if not args.no_rsync:
            rsync_scraper(cfg)
            result["rsync"] = "ok"
        result["stopped"] = stop_all_scrapers(cfg)
        result["worker"] = ensure_worker(cfg, args.preset, service)
        log_tail_cmd = (
            f"tail -8 {cfg.data_root}/streamlit_scraper/output/{args.preset}/scrape.log 2>/dev/null "
            "|| echo '(no log yet)'"
        )
        _, log_tail, _ = _ssh_exec(cfg, log_tail_cmd, timeout=30)
        result["log_tail"] = log_tail
    except Exception as exc:
        result["error"] = str(exc)
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
