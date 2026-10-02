"""Build scrape run history rows from VPS/local disk artifacts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from scrape_metrics import heartbeat_age_seconds
from scrape_state import STATUS_COMPLETED, STATUS_INCOMPLETE, STATUS_RUNNING

_LOG_TS = re.compile(r"^\[([^\]]+)\]")
_RUN_START = re.compile(
    r"Worker loop start — preset=([^,]+), target=(\d+), mode=(\S+)"
)
_TARGET_REACHED = re.compile(r"Target reached — progress (\d+)/(\d+)")
_WORKER_BLOCKED = re.compile(r"Worker blocked — (.+)")


def _parse_log_ts(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw


def _status_label_fr(code: str) -> str:
    mapping = {
        "running": "En cours",
        "complete": "Terminé",
        "completed": "Terminé",
        "incomplete": "Incomplet",
        "blocked": "Bloqué",
        "stalled": "En pause (heartbeat)",
        "idle": "Inactif",
        "heal_start": "Relance (heal)",
        "heal_restart": "Redémarrage (heal)",
        "noop_at_target": "Objectif atteint",
        "noop_healthy": "OK (watchdog)",
    }
    return mapping.get(code, code or "—")


def parse_worker_runs_from_log(log_text: str) -> list[dict[str, Any]]:
    """Infer worker-loop sessions from scrape.log (newest first)."""
    if not log_text:
        return []

    open_run: dict[str, Any] | None = None
    completed: list[dict[str, Any]] = []

    def _flush(end_ts: str = "", end_status: str = "incomplete", note: str = "") -> None:
        nonlocal open_run
        if not open_run:
            return
        if end_ts:
            open_run["ended_at"] = end_ts
        open_run["status"] = end_status
        if note:
            open_run["note"] = note
        completed.append(open_run)
        open_run = None

    for line in log_text.splitlines():
        ts_match = _LOG_TS.match(line)
        ts_raw = ts_match.group(1) if ts_match else ""
        ts_iso = _parse_log_ts(ts_raw)

        start_match = _RUN_START.search(line)
        if start_match:
            _flush(end_ts=ts_iso, end_status="interrupted")
            open_run = {
                "source": "log",
                "preset": start_match.group(1).strip(),
                "target": int(start_match.group(2)),
                "target_mode": start_match.group(3).strip(),
                "started_at": ts_iso,
                "ended_at": "",
                "status": "running",
                "leads_saved": None,
                "instantly_pushed": None,
                "note": "",
            }
            continue

        if not open_run:
            continue

        target_match = _TARGET_REACHED.search(line)
        if target_match:
            open_run["progress"] = int(target_match.group(1))
            open_run["target"] = int(target_match.group(2))
            _flush(end_ts=ts_iso, end_status="completed", note="Objectif atteint")
            continue

        blocked_match = _WORKER_BLOCKED.search(line)
        if blocked_match:
            open_run["note"] = blocked_match.group(1).strip()[:120]

    if open_run:
        completed.append(open_run)

    completed.reverse()
    return completed


def _state_run_row(state: dict[str, Any], preset_id: str) -> dict[str, Any]:
    status = str(state.get("status") or STATUS_INCOMPLETE)
    return {
        "source": "checkpoint",
        "preset": str(state.get("preset") or preset_id),
        "target": int(state.get("target", 0) or 0),
        "target_mode": str(state.get("target_mode") or ""),
        "started_at": str(state.get("started_at") or ""),
        "ended_at": str(state.get("last_updated") or "") if status != STATUS_RUNNING else "",
        "status": status,
        "leads_saved": int(state.get("leads_saved", 0) or 0),
        "leads_enriched_valid": int(state.get("leads_enriched_valid", 0) or 0),
        "leads_enriched_rejected": int(state.get("leads_enriched_rejected", 0) or 0),
        "instantly_pushed": int(state.get("instantly_pushed", 0) or 0),
        "inflight": len(state.get("inflight_tasks") or []),
        "note": "",
    }


def _cron_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        action = str(event.get("action") or "")
        rows.append(
            {
                "source": "cron",
                "preset": "",
                "target": int(event.get("target", 0) or 0),
                "target_mode": "",
                "started_at": str(event.get("ts") or ""),
                "ended_at": "",
                "status": action,
                "leads_saved": None,
                "instantly_pushed": event.get("progress") or event.get("progress_before"),
                "note": (
                    f"live {event.get('live_before', '?')} → {event.get('live_after', '?')}"
                    if event.get("live_before") is not None
                    else ""
                ),
            }
        )
    rows.reverse()
    return rows


def merge_run_history(
    preset_id: str,
    *,
    state: dict[str, Any] | None,
    log_text: str,
    cron_events: list[dict],
    max_rows: int = 25,
) -> list[dict[str, Any]]:
    """Combine checkpoint, log-derived runs, and cron heal events (newest first)."""
    rows: list[dict[str, Any]] = []

    log_runs = [
        run for run in parse_worker_runs_from_log(log_text) if run.get("preset") == preset_id
    ]
    rows.extend(log_runs)

    if state and str(state.get("preset") or preset_id) == preset_id:
        state_row = _state_run_row(state, preset_id)
        state_start = str(state_row.get("started_at") or "")
        latest_log_start = max(
            (str(r.get("started_at") or "") for r in log_runs),
            default="",
        )
        if state_row.get("status") == STATUS_RUNNING or state_start >= latest_log_start:
            rows.append(state_row)

    rows.extend(_cron_rows(cron_events))

    def _sort_key(item: dict[str, Any]) -> str:
        return str(item.get("started_at") or item.get("ended_at") or "")

    rows.sort(key=_sort_key, reverse=True)
    return rows[:max_rows]


def detect_scrape_running(
    preset_id: str,
    *,
    state: dict[str, Any] | None,
    heartbeat: dict[str, Any] | None,
    vps: dict[str, Any] | None,
) -> tuple[bool, str, str]:
    """Return (is_running, status_code, french_label)."""
    age = heartbeat_age_seconds(heartbeat)
    hb_preset = str((heartbeat or {}).get("preset") or "").strip()
    hb_status = str((heartbeat or {}).get("status") or "").strip()
    vps_active = bool(vps and vps.get("active"))
    state_status = str((state or {}).get("status") or "")

    if vps_active:
        if hb_preset and hb_preset != preset_id:
            return False, "other_preset", f"Worker VPS actif (autre preset : {hb_preset})"
        if age is not None and age < 900:
            if hb_status in ("running", "blocked"):
                return True, hb_status, _status_label_fr(hb_status)
            if state_status == STATUS_RUNNING:
                return True, "running", _status_label_fr("running")
        if state_status == STATUS_RUNNING and age is not None and age < 900:
            return True, "running", _status_label_fr("running")
        if vps_active and age is None and state_status == STATUS_RUNNING:
            return True, "running", _status_label_fr("running")

    if not vps_active and state_status == STATUS_RUNNING:
        if age is not None and age < 900 and (not hb_preset or hb_preset == preset_id):
            if hb_status in ("running", "blocked", ""):
                return True, hb_status or "running", _status_label_fr(hb_status or "running")

    if age is not None and age >= 900 and state_status == STATUS_RUNNING:
        return False, "stalled", _status_label_fr("stalled")

    if state_status == STATUS_COMPLETED:
        return False, STATUS_COMPLETED, _status_label_fr(STATUS_COMPLETED)

    return False, "idle", _status_label_fr("idle")


def history_to_dataframe_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Flatten for st.dataframe display."""
    out: list[dict[str, str]] = []
    for row in rows:
        source = str(row.get("source") or "")
        status_code = str(row.get("status") or "")
        leads = row.get("leads_saved")
        pushed = row.get("instantly_pushed")
        enrich_ok = row.get("leads_enriched_valid")
        rejected = row.get("leads_enriched_rejected")
        inflight = row.get("inflight")
        parts: list[str] = []
        if leads is not None:
            parts.append(f"CSV {leads}")
        if enrich_ok is not None:
            parts.append(f"valid {enrich_ok}")
        if rejected is not None:
            parts.append(f"rej. {rejected}")
        if pushed is not None:
            parts.append(f"push {pushed}")
        if inflight:
            parts.append(f"in-flight {inflight}")

        out.append(
            {
                "Début": _short_ts(str(row.get("started_at") or "")),
                "Fin": _short_ts(str(row.get("ended_at") or "")),
                "Statut": _status_label_fr(status_code),
                "Preset": str(row.get("preset") or ("—" if source != "cron" else "watchdog")),
                "Objectif": _format_target(row),
                "Leads / progrès": ", ".join(parts) if parts else "—",
                "Détail": str(row.get("note") or "")[:160],
            }
        )
    return out


def _short_ts(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso[:19] if len(iso) > 19 else iso


def _format_target(row: dict[str, Any]) -> str:
    target = int(row.get("target") or 0)
    mode = str(row.get("target_mode") or "")
    if target <= 0:
        return "—"
    return f"{target:,} ({mode})" if mode else f"{target:,}"
