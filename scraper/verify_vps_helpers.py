"""Pure helpers for VPS scrape worker verification (heartbeat, counts, speed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CheckStatus = Literal["PASS", "WARN", "FAIL", "SKIP"]

HEARTBEAT_STALE_S = 180.0
HEARTBEAT_UI_STALLED_S = 900.0
DEFAULT_MIN_LIVE_PER_HOUR = 100.0
COUNT_TOLERANCE = 5


@dataclass
class PresetSpec:
    preset_id: str
    service_name: str


DEFAULT_PRESET_SPECS: tuple[PresetSpec, ...] = (
    PresetSpec("cabinets_expertise_comptable_fresh_geo", "hercule-scraper-comptable-fresh-geo"),
)


@dataclass
class PresetSnapshot:
    preset_id: str
    service_name: str
    systemd_active: bool
    heartbeat: dict[str, Any] | None
    heartbeat_age_s: float | None
    heartbeat_status: str
    state: dict[str, Any] | None
    leads_saved: int
    instantly_pushed: int
    remote_csv: int | None
    progress: int
    instantly_skipped_duplicate: int


@dataclass
class SpeedSample:
    elapsed_s: float
    live_start: int | None
    live_end: int | None
    live_per_hour: float | None
    preset_deltas: dict[str, dict[str, float | int | None]]


def classify_worker_health(
    *,
    systemd_active: bool,
    heartbeat_age_s: float | None,
    heartbeat_status: str,
    progress_delta: int = 0,
) -> CheckStatus:
    """Classify worker health for heartbeat checks."""
    status = (heartbeat_status or "").strip().lower()
    if not systemd_active:
        if status == "complete":
            return "PASS"
        return "WARN"
    if heartbeat_age_s is None:
        return "FAIL"
    if heartbeat_age_s >= HEARTBEAT_UI_STALLED_S:
        return "FAIL"
    if status == "blocked" and progress_delta <= 0:
        return "FAIL"
    if heartbeat_age_s >= HEARTBEAT_STALE_S:
        return "FAIL"
    if status == "blocked":
        return "WARN"
    return "PASS"


def counts_consistent(
    *,
    leads_saved: int,
    remote_csv: int | None,
    instantly_pushed: int,
    instantly_live: int | None,
    target_mode: str = "",
) -> CheckStatus:
    """Check scrape_state vs CSV and checkpoint vs live list."""
    if remote_csv is not None and remote_csv < max(leads_saved - COUNT_TOLERANCE, 0):
        return "FAIL"
    if instantly_live is not None and instantly_pushed > instantly_live + COUNT_TOLERANCE:
        # Run checkpoint can exceed live when list is shared + skip-if-in-list, or after list wipe.
        if target_mode == "instantly_pushed_run":
            return "WARN"
        return "FAIL"
    return "PASS"


def compute_rate_per_hour(delta: int | float, elapsed_s: float) -> float | None:
    if elapsed_s <= 0:
        return None
    return float(delta) / (elapsed_s / 3600.0)


def classify_speed(
    live_per_hour: float | None,
    *,
    min_live_per_hour: float = DEFAULT_MIN_LIVE_PER_HOUR,
    sample_minutes: float,
    any_systemd_active: bool,
    outscraper_healthy: bool,
) -> CheckStatus:
    if sample_minutes <= 0:
        return "SKIP"
    if not any_systemd_active:
        return "SKIP"
    if not outscraper_healthy:
        return "FAIL"
    if live_per_hour is None:
        return "FAIL"
    if live_per_hour >= min_live_per_hour:
        return "PASS"
    if live_per_hour > 0:
        return "WARN"
    return "FAIL"


def outscraper_probe_status(http_status: int | None, error: str = "") -> CheckStatus:
    if http_status == 402:
        return "FAIL"
    if http_status is None:
        return "WARN" if error else "FAIL"
    if 200 <= http_status < 300:
        return "PASS"
    if http_status in (401, 403):
        return "FAIL"
    return "WARN"


def aggregate_exit_code(checks: dict[str, CheckStatus]) -> int:
    if any(status == "FAIL" for status in checks.values()):
        return 1
    return 0
