"""Prometheus exporter for VPS scraper fleet (read-only disk state).

Scans $HERCULE_DATA_ROOT/streamlit_scraper/output/*/ for worker_heartbeat.json
and scrape_state.json, exposes gauges on :9464/metrics.

No Instantly API calls — progress uses checkpoint fields only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow `python -m monitoring.exporter` from lib/backend/streamlit_scraper
_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from scrape_metrics import heartbeat_age_seconds, load_worker_heartbeat  # noqa: E402
from scrape_state import target_progress_value  # noqa: E402

HEARTBEAT_STALE_S = 900.0
DEFAULT_PORT = 9464
DEFAULT_REFRESH_S = 10.0
STATUS_LABELS = ("running", "stalled", "idle", "complete", "blocked")


@dataclass(frozen=True)
class PresetSnapshot:
    preset: str
    status: str
    heartbeat_age_s: float | None
    worker_up: bool
    target_leads: int
    progress_leads: int
    progress_ratio: float
    leads_saved: int
    leads_enriched_valid: int
    leads_enriched_rejected: int
    instantly_pushed: int
    inflight_tasks: int
    batch_completed: int
    batches_total: int
    query_pass: int
    state_last_updated_ts: float | None


def resolve_output_base(data_root: str | None = None) -> Path:
    """Return streamlit_scraper/output directory."""
    root = (data_root or os.environ.get("HERCULE_DATA_ROOT", "")).strip()
    if root:
        return Path(root) / "streamlit_scraper" / "output"
    return _LIB / "output"


def discover_presets(output_base: Path) -> list[str]:
    if not output_base.is_dir():
        return []
    presets: list[str] = []
    for entry in sorted(output_base.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "scrape_state.json").is_file() or (entry / "worker_heartbeat.json").is_file():
            presets.append(entry.name)
    return presets


def _load_json_dict(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_iso_timestamp(raw: str) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        seen = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        return seen.timestamp()
    except ValueError:
        return None


def derive_worker_status(
    heartbeat: dict[str, Any] | None,
    state: dict[str, Any] | None,
    *,
    stale_s: float = HEARTBEAT_STALE_S,
) -> tuple[str, float | None, bool]:
    """Return (status_label, age_seconds, worker_up)."""
    age = heartbeat_age_seconds(heartbeat)
    hb_status = str((heartbeat or {}).get("status") or "").strip().lower()
    state_status = str((state or {}).get("status") or "").strip().lower()

    if hb_status == "complete" or state_status == "completed":
        return "complete", age, False
    if hb_status == "blocked":
        return "blocked", age, False
    if age is None:
        return "idle", None, False
    if age >= stale_s:
        return "stalled", age, False
    return "running", age, True


def collect_preset_snapshot(
    preset: str,
    out_dir: Path,
    *,
    stale_s: float = HEARTBEAT_STALE_S,
) -> PresetSnapshot:
    heartbeat = load_worker_heartbeat(str(out_dir))
    state = _load_json_dict(out_dir / "scrape_state.json") or {}

    status, age, worker_up = derive_worker_status(heartbeat, state, stale_s=stale_s)

    mode = str(state.get("target_mode") or "csv_saved").strip()
    target = int(state.get("target") or 0)
    leads_saved = int(state.get("leads_saved") or 0)
    instantly_pushed = int(state.get("instantly_pushed") or 0)
    progress = target_progress_value(
        mode,
        instantly_pushed=instantly_pushed,
        leads_saved=leads_saved,
        instantly_live=None,
    )
    ratio = min(progress / target, 1.0) if target > 0 else 0.0
    last_batch = int(state.get("last_completed_batch_index", -1) or -1)
    batches_total = int(state.get("batches_total") or 0)
    inflight = state.get("inflight_tasks") or []
    inflight_n = len(inflight) if isinstance(inflight, list) else 0

    return PresetSnapshot(
        preset=preset,
        status=status,
        heartbeat_age_s=age,
        worker_up=worker_up,
        target_leads=target,
        progress_leads=progress,
        progress_ratio=ratio,
        leads_saved=leads_saved,
        leads_enriched_valid=int(state.get("leads_enriched_valid") or 0),
        leads_enriched_rejected=int(state.get("leads_enriched_rejected") or 0),
        instantly_pushed=instantly_pushed,
        inflight_tasks=inflight_n,
        batch_completed=max(last_batch + 1, 0),
        batches_total=batches_total,
        query_pass=int(state.get("query_pass") or 0),
        state_last_updated_ts=_parse_iso_timestamp(str(state.get("last_updated") or "")),
    )


def collect_fleet(output_base: Path, *, stale_s: float = HEARTBEAT_STALE_S) -> list[PresetSnapshot]:
    return [
        collect_preset_snapshot(preset, output_base / preset, stale_s=stale_s)
        for preset in discover_presets(output_base)
    ]


def list_systemd_scraper_services() -> list[tuple[str, bool]]:
    """Return (unit_name, is_active) for hercule-scraper* services (exclude heal/exporter)."""
    try:
        proc = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    results: list[tuple[str, bool]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        unit = parts[0]
        if not unit.startswith("hercule-scraper"):
            continue
        if unit.endswith("-heal.service") or unit == "hercule-scraper-exporter.service":
            continue
        if not unit.endswith(".service"):
            continue
        name = unit[: -len(".service")]
        active = False
        try:
            check = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            active = check.stdout.strip() == "active"
        except (OSError, subprocess.TimeoutExpired):
            active = False
        results.append((name, active))
    return results


def _build_metrics():
    from prometheus_client import Gauge

    return {
        "heartbeat_age": Gauge(
            "scraper_heartbeat_age_seconds",
            "Seconds since last worker heartbeat",
            ["preset"],
        ),
        "worker_up": Gauge(
            "scraper_worker_up",
            "1 if heartbeat age is under stale threshold",
            ["preset"],
        ),
        "status_info": Gauge(
            "scraper_status_info",
            "1 for the current worker status label",
            ["preset", "status"],
        ),
        "target_leads": Gauge(
            "scraper_target_leads",
            "Target lead count from scrape_state",
            ["preset"],
        ),
        "progress_leads": Gauge(
            "scraper_progress_leads",
            "Checkpoint progress toward target (no Instantly live API)",
            ["preset"],
        ),
        "progress_ratio": Gauge(
            "scraper_progress_ratio",
            "progress_leads / target_leads (capped at 1)",
            ["preset"],
        ),
        "leads_saved": Gauge(
            "scraper_leads_saved",
            "Leads saved to CSV checkpoint",
            ["preset"],
        ),
        "enriched_valid": Gauge(
            "scraper_leads_enriched_valid",
            "Enriched valid leads",
            ["preset"],
        ),
        "enriched_rejected": Gauge(
            "scraper_leads_enriched_rejected",
            "Enrichment rejects",
            ["preset"],
        ),
        "instantly_pushed": Gauge(
            "scraper_instantly_pushed",
            "Instantly pushed checkpoint count",
            ["preset"],
        ),
        "inflight": Gauge(
            "scraper_inflight_tasks",
            "Outscraper inflight task count",
            ["preset"],
        ),
        "batch_completed": Gauge(
            "scraper_batch_completed",
            "Completed batch count (last_completed_batch_index + 1)",
            ["preset"],
        ),
        "batches_total": Gauge(
            "scraper_batches_total",
            "Total batches in current pass",
            ["preset"],
        ),
        "query_pass": Gauge(
            "scraper_query_pass",
            "Current query pass index",
            ["preset"],
        ),
        "state_updated": Gauge(
            "scraper_state_last_updated_timestamp",
            "Unix timestamp of scrape_state last_updated",
            ["preset"],
        ),
        "systemd_active": Gauge(
            "scraper_systemd_active",
            "1 if systemd unit is active",
            ["service"],
        ),
    }


def publish_snapshots(metrics: dict, snapshots: list[PresetSnapshot]) -> None:
    for snap in snapshots:
        p = snap.preset
        if snap.heartbeat_age_s is not None:
            metrics["heartbeat_age"].labels(preset=p).set(snap.heartbeat_age_s)
        else:
            metrics["heartbeat_age"].labels(preset=p).set(-1)
        metrics["worker_up"].labels(preset=p).set(1 if snap.worker_up else 0)
        for label in STATUS_LABELS:
            metrics["status_info"].labels(preset=p, status=label).set(
                1 if snap.status == label else 0
            )
        metrics["target_leads"].labels(preset=p).set(snap.target_leads)
        metrics["progress_leads"].labels(preset=p).set(snap.progress_leads)
        metrics["progress_ratio"].labels(preset=p).set(snap.progress_ratio)
        metrics["leads_saved"].labels(preset=p).set(snap.leads_saved)
        metrics["enriched_valid"].labels(preset=p).set(snap.leads_enriched_valid)
        metrics["enriched_rejected"].labels(preset=p).set(snap.leads_enriched_rejected)
        metrics["instantly_pushed"].labels(preset=p).set(snap.instantly_pushed)
        metrics["inflight"].labels(preset=p).set(snap.inflight_tasks)
        metrics["batch_completed"].labels(preset=p).set(snap.batch_completed)
        metrics["batches_total"].labels(preset=p).set(snap.batches_total)
        metrics["query_pass"].labels(preset=p).set(snap.query_pass)
        if snap.state_last_updated_ts is not None:
            metrics["state_updated"].labels(preset=p).set(snap.state_last_updated_ts)
        else:
            metrics["state_updated"].labels(preset=p).set(0)

    for service, active in list_systemd_scraper_services():
        metrics["systemd_active"].labels(service=service).set(1 if active else 0)


def refresh_loop(
    output_base: Path,
    metrics: dict,
    *,
    refresh_s: float = DEFAULT_REFRESH_S,
    stale_s: float = HEARTBEAT_STALE_S,
) -> None:
    while True:
        try:
            snapshots = collect_fleet(output_base, stale_s=stale_s)
            publish_snapshots(metrics, snapshots)
        except Exception as exc:  # noqa: BLE001 — keep exporter alive
            print(f"[exporter] refresh error: {exc}", file=sys.stderr)
        time.sleep(refresh_s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hercule scraper Prometheus exporter")
    parser.add_argument("--port", type=int, default=int(os.getenv("SCRAPER_EXPORTER_PORT", DEFAULT_PORT)))
    parser.add_argument(
        "--data-root",
        default=os.getenv("HERCULE_DATA_ROOT", "").strip() or None,
        help="HERCULE_DATA_ROOT override",
    )
    parser.add_argument("--refresh", type=float, default=DEFAULT_REFRESH_S)
    parser.add_argument("--stale-seconds", type=float, default=HEARTBEAT_STALE_S)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect once and print JSON (no HTTP server)",
    )
    args = parser.parse_args(argv)

    output_base = resolve_output_base(args.data_root)
    if args.once:
        snaps = collect_fleet(output_base, stale_s=args.stale_seconds)
        print(json.dumps([s.__dict__ for s in snaps], indent=2, default=str))
        return 0

    from prometheus_client import start_http_server

    metrics = _build_metrics()
    start_http_server(args.port)
    print(
        f"[exporter] listening on :{args.port} output_base={output_base} refresh={args.refresh}s",
        flush=True,
    )
    refresh_loop(
        output_base,
        metrics,
        refresh_s=args.refresh,
        stale_s=args.stale_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
