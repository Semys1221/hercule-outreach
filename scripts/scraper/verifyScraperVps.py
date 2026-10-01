#!/usr/bin/env python3
"""Verify VPS scrape workers: heartbeat freshness, count consistency, and speed."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from typing import Any

import httpx
from dotenv import load_dotenv

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, os.path.join(REPO, "lib", "backend", "streamlit_scraper"))

from bootstrap.vps_control import (  # noqa: E402
    VpsConfig,
    load_panel_state,
    remote_csv_lead_count,
    vps_configured,
    worker_status,
)
from config_loader import load_config  # noqa: E402
from scrape_metrics import fetch_instantly_live, heartbeat_age_seconds  # noqa: E402
from scrape_state import target_mode, target_progress_value  # noqa: E402
from verify_vps_helpers import (  # noqa: E402
    DEFAULT_MIN_LIVE_PER_HOUR,
    DEFAULT_PRESET_SPECS,
    PresetSnapshot,
    PresetSpec,
    SpeedSample,
    aggregate_exit_code,
    classify_speed,
    classify_worker_health,
    counts_consistent,
    compute_rate_per_hour,
    outscraper_probe_status,
)

_OUTSCRAPER_BALANCE_URL = "https://api.outscraper.com/profile/balance"


def _parse_preset_specs(preset_args: list[str]) -> list[PresetSpec]:
    if not preset_args:
        return list(DEFAULT_PRESET_SPECS)
    known = {spec.preset_id: spec for spec in DEFAULT_PRESET_SPECS}
    specs: list[PresetSpec] = []
    for preset_id in preset_args:
        if preset_id in known:
            specs.append(known[preset_id])
        else:
            service = os.getenv("VPS_SCRAPER_SERVICE", "hercule-scraper").strip()
            specs.append(PresetSpec(preset_id, service))
    return specs


def _vps_cfg_for_service(base: VpsConfig, service_name: str) -> VpsConfig:
    return VpsConfig(
        host=base.host,
        user=base.user,
        password=base.password,
        repo_root=base.repo_root,
        data_root=base.data_root,
        service_name=service_name,
    )


def probe_outscraper(api_key: str) -> tuple[int | None, str]:
    key = api_key.strip()
    if not key:
        return None, "OUTSCRAPER_API_KEY missing"
    try:
        response = httpx.get(
            _OUTSCRAPER_BALANCE_URL,
            params={"apiKey": key},
            timeout=10.0,
        )
        if response.status_code == 402:
            return 402, response.text[:200]
        return response.status_code, ""
    except httpx.HTTPError as exc:
        return None, str(exc)


def collect_preset_snapshot(spec: PresetSpec, base_cfg: VpsConfig | None) -> PresetSnapshot:
    state, _, _, heartbeat, _ = load_panel_state(spec.preset_id)
    config = load_config(spec.preset_id, require_keys=False)
    mode = target_mode(config)
    live = fetch_instantly_live(config, use_cache=False)
    leads_saved = int(state.get("leads_saved", 0)) if state else 0
    instantly_pushed = int(state.get("instantly_pushed", 0)) if state else 0
    remote_csv = remote_csv_lead_count(spec.preset_id) if base_cfg else None
    scraped = max(leads_saved, remote_csv or 0)
    progress = target_progress_value(
        mode,
        instantly_pushed=instantly_pushed,
        leads_saved=scraped,
        instantly_live=live,
    )
    age = heartbeat_age_seconds(heartbeat)
    status = str((heartbeat or {}).get("status") or "unknown")
    systemd_active = False
    if base_cfg:
        svc = worker_status(cfg=_vps_cfg_for_service(base_cfg, spec.service_name))
        systemd_active = bool(svc.get("active"))
    return PresetSnapshot(
        preset_id=spec.preset_id,
        service_name=spec.service_name,
        systemd_active=systemd_active,
        heartbeat=heartbeat,
        heartbeat_age_s=age,
        heartbeat_status=status,
        state=state,
        leads_saved=leads_saved,
        instantly_pushed=instantly_pushed,
        remote_csv=remote_csv,
        progress=progress,
        instantly_skipped_duplicate=int(state.get("instantly_skipped_duplicate", 0)) if state else 0,
    )


def sample_speed(
    specs: list[PresetSpec],
    *,
    sample_minutes: float,
    poll_seconds: float,
    base_cfg: VpsConfig | None,
) -> SpeedSample:
    duration_s = max(sample_minutes * 60.0, poll_seconds)
    polls = max(int(duration_s / poll_seconds), 1)
    first_live: int | None = None
    last_live: int | None = None
    first_by_preset: dict[str, PresetSnapshot] = {}
    last_by_preset: dict[str, PresetSnapshot] = {}
    started = time.monotonic()

    for index in range(polls):
        config = load_config(specs[0].preset_id, require_keys=False)
        live = fetch_instantly_live(config, use_cache=False)
        if index == 0:
            first_live = live
        last_live = live
        for spec in specs:
            snap = collect_preset_snapshot(spec, base_cfg)
            if index == 0:
                first_by_preset[spec.preset_id] = snap
            last_by_preset[spec.preset_id] = snap
        if index + 1 < polls:
            time.sleep(poll_seconds)

    elapsed_s = time.monotonic() - started
    live_delta = None
    if first_live is not None and last_live is not None:
        live_delta = last_live - first_live
    live_per_hour = (
        compute_rate_per_hour(live_delta, elapsed_s) if live_delta is not None else None
    )

    preset_deltas: dict[str, dict[str, float | int | None]] = {}
    for preset_id, first in first_by_preset.items():
        last = last_by_preset[preset_id]
        pushed_delta = last.instantly_pushed - first.instantly_pushed
        saved_delta = last.leads_saved - first.leads_saved
        skipped_delta = last.instantly_skipped_duplicate - first.instantly_skipped_duplicate
        csv_start = first.remote_csv or 0
        csv_end = last.remote_csv or 0
        preset_deltas[preset_id] = {
            "pushed_delta": pushed_delta,
            "saved_delta": saved_delta,
            "skipped_duplicate_delta": skipped_delta,
            "csv_delta": csv_end - csv_start,
            "pushed_per_hour": compute_rate_per_hour(pushed_delta, elapsed_s),
            "accepted_per_hour": compute_rate_per_hour(saved_delta, elapsed_s),
            "saved_per_hour": compute_rate_per_hour(saved_delta, elapsed_s),
            "csv_per_hour": compute_rate_per_hour(csv_end - csv_start, elapsed_s),
            "progress_delta": last.progress - first.progress,
            "duplicate_skip_rate": (
                skipped_delta / pushed_delta if pushed_delta > 0 else None
            ),
        }

    return SpeedSample(
        elapsed_s=elapsed_s,
        live_start=first_live,
        live_end=last_live,
        live_per_hour=live_per_hour,
        preset_deltas=preset_deltas,
    )


def run_verify(
    *,
    preset_specs: list[PresetSpec],
    sample_minutes: float,
    poll_seconds: float,
    min_live_per_hour: float,
) -> dict[str, Any]:
    checks: dict[str, str] = {}
    base_cfg = VpsConfig.from_env()

    if not vps_configured() or base_cfg is None:
        checks["vps_reachable"] = "FAIL"
        return {
            "checks": checks,
            "error": "VPS disabled (VPS_DISABLED) or SSH unreachable",
            "presets": [],
            "instantly_live": None,
            "outscraper": {"http_status": None, "detail": "skipped"},
            "speed": None,
        }

    probe_cfg = load_config(preset_specs[0].preset_id, require_keys=False)
    http_status, probe_err = probe_outscraper(str(probe_cfg.get("OUTSCRAPER_API_KEY") or ""))
    checks["vps_reachable"] = "PASS" if worker_status().get("reachable", True) else "FAIL"
    checks["outscraper_healthy"] = outscraper_probe_status(http_status, probe_err)

    snapshots = [collect_preset_snapshot(spec, base_cfg) for spec in preset_specs]
    instantly_live = fetch_instantly_live(probe_cfg, use_cache=False)

    systemd_ok = all(s.systemd_active for s in snapshots)
    checks["systemd_active"] = "PASS" if systemd_ok else "WARN"

    heartbeat_results: list[str] = []
    count_results: list[str] = []
    for snap in snapshots:
        delta = 0
        preset_key = snap.preset_id
        hb = classify_worker_health(
            systemd_active=snap.systemd_active,
            heartbeat_age_s=snap.heartbeat_age_s,
            heartbeat_status=snap.heartbeat_status,
            progress_delta=delta,
        )
        heartbeat_results.append(hb)
        count_results.append(
            counts_consistent(
                leads_saved=snap.leads_saved,
                remote_csv=snap.remote_csv,
                instantly_pushed=snap.instantly_pushed,
                instantly_live=instantly_live,
                target_mode=target_mode(load_config(snap.preset_id, require_keys=False)),
            )
        )

    checks["heartbeat_fresh"] = (
        "FAIL" if any(r == "FAIL" for r in heartbeat_results) else "PASS"
    )
    checks["heartbeat_not_blocked"] = (
        "PASS" if all(r != "FAIL" for r in heartbeat_results) else "FAIL"
    )
    checks["counts_consistent"] = (
        "FAIL" if any(r == "FAIL" for r in count_results) else "PASS"
    )

    speed: SpeedSample | None = None
    if sample_minutes > 0:
        speed = sample_speed(
            preset_specs,
            sample_minutes=sample_minutes,
            poll_seconds=poll_seconds,
            base_cfg=base_cfg,
        )
        for preset_id, deltas in speed.preset_deltas.items():
            snap = next(s for s in snapshots if s.preset_id == preset_id)
            progress_delta = int(deltas.get("progress_delta") or 0)
            hb = classify_worker_health(
                systemd_active=snap.systemd_active,
                heartbeat_age_s=snap.heartbeat_age_s,
                heartbeat_status=snap.heartbeat_status,
                progress_delta=progress_delta,
            )
            if hb == "FAIL":
                checks["heartbeat_not_blocked"] = "FAIL"
        checks["speed_sustained"] = classify_speed(
            speed.live_per_hour,
            min_live_per_hour=min_live_per_hour,
            sample_minutes=sample_minutes,
            any_systemd_active=any(s.systemd_active for s in snapshots),
            outscraper_healthy=checks["outscraper_healthy"] == "PASS",
        )
    else:
        checks["speed_sustained"] = "SKIP"

    return {
        "checks": checks,
        "instantly_live": instantly_live,
        "outscraper": {"http_status": http_status, "detail": probe_err},
        "presets": [asdict(s) for s in snapshots],
        "speed": asdict(speed) if speed else None,
        "host": base_cfg.host,
    }


def _print_human_report(result: dict[str, Any]) -> None:
    print("=== Scraper VPS verification ===")
    if result.get("error"):
        print(f"ERROR: {result['error']}")
        return
    print(f"Host: {result.get('host', '?')}")
    print(f"Instantly live (shared): {result.get('instantly_live')}")
    outscraper = result.get("outscraper") or {}
    print(
        f"Outscraper probe: HTTP {outscraper.get('http_status')} "
        f"{outscraper.get('detail') or ''}".rstrip()
    )
    print()
    print(f"{'Preset':<40} {'Service':<32} {'systemd':<8} {'HB age':<10} {'Status':<10} {'Pushed':<8} {'CSV':<8} {'Saved':<8}")
    print("-" * 130)
    for row in result.get("presets") or []:
        age = row.get("heartbeat_age_s")
        age_s = f"{int(age)}s" if age is not None else "—"
        print(
            f"{row.get('preset_id', ''):<40} "
            f"{row.get('service_name', ''):<32} "
            f"{'active' if row.get('systemd_active') else 'off':<8} "
            f"{age_s:<10} "
            f"{row.get('heartbeat_status', '?'):<10} "
            f"{row.get('instantly_pushed', 0):<8} "
            f"{row.get('remote_csv') or '—':<8} "
            f"{row.get('leads_saved', 0):<8}"
        )
    speed = result.get("speed")
    if speed:
        print()
        print(
            f"Speed sample: {speed.get('elapsed_s', 0):.0f}s — "
            f"live {speed.get('live_start')} → {speed.get('live_end')} "
            f"({speed.get('live_per_hour') or 0:.1f} live/h)"
        )
        for preset_id, deltas in (speed.get("preset_deltas") or {}).items():
            dup_rate = deltas.get("duplicate_skip_rate")
            dup_label = f", dup_skip={dup_rate:.0%}" if dup_rate is not None else ""
            print(
                f"  {preset_id}: accepted +{deltas.get('saved_delta')} "
                f"({deltas.get('accepted_per_hour') or 0:.1f}/h), "
                f"pushed +{deltas.get('pushed_delta')} "
                f"({deltas.get('pushed_per_hour') or 0:.1f}/h){dup_label}"
            )
    print()
    print("Checks:")
    for name, status in sorted((result.get("checks") or {}).items()):
        print(f"  [{status}] {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify VPS scrape worker metrics.")
    parser.add_argument(
        "--preset",
        action="append",
        default=[],
        help="Preset id (repeatable). Default: both comptable presets.",
    )
    parser.add_argument(
        "--sample-minutes",
        type=float,
        default=15.0,
        help="Speed sample window in minutes (0 = snapshot only).",
    )
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--min-live-per-hour", type=float, default=DEFAULT_MIN_LIVE_PER_HOUR)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    specs = _parse_preset_specs(args.preset)
    result = run_verify(
        preset_specs=specs,
        sample_minutes=args.sample_minutes,
        poll_seconds=args.poll_seconds,
        min_live_per_hour=args.min_live_per_hour,
    )
    checks = result.get("checks") or {}
    exit_code = aggregate_exit_code(checks)

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human_report(result)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
