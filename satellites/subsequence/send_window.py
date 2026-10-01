"""Paris weekday send window for manual Instantly bypass sends."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from config import send_window_end_hour, send_window_start_hour, send_window_tz

_PARIS = ZoneInfo(send_window_tz())

_WEEKDAY_NAMES_FR = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)

_MONTH_NAMES_FR = (
    "jan.",
    "fév.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_weekday_paris(dt: datetime | None = None) -> bool:
    paris = _ensure_utc(dt or datetime.now(timezone.utc)).astimezone(_PARIS)
    return paris.weekday() < 5


def is_within_send_window(dt: datetime | None = None) -> bool:
    paris = _ensure_utc(dt or datetime.now(timezone.utc)).astimezone(_PARIS)
    if paris.weekday() >= 5:
        return False
    start = time(send_window_start_hour(), 0)
    end = time(send_window_end_hour(), 0)
    return start <= paris.time() < end


def _paris_at_hour(paris_date: datetime, hour: int) -> datetime:
    local = datetime(
        paris_date.year,
        paris_date.month,
        paris_date.day,
        hour,
        0,
        0,
        tzinfo=_PARIS,
    )
    return local.astimezone(timezone.utc)


def next_send_slot(dt: datetime | None = None) -> datetime:
    paris = _ensure_utc(dt or datetime.now(timezone.utc)).astimezone(_PARIS)
    start_h = send_window_start_hour()
    end_h = send_window_end_hour()

    if paris.weekday() < 5 and paris.time() < time(start_h, 0):
        return _paris_at_hour(paris, start_h)

    if is_within_send_window(paris.astimezone(timezone.utc)):
        return _ensure_utc(dt or datetime.now(timezone.utc))

    candidate = paris
    if paris.weekday() < 5 and paris.time() >= time(end_h, 0):
        candidate = paris + timedelta(days=1)
    elif paris.weekday() >= 5:
        if paris.weekday() == 5:
            candidate = paris + timedelta(days=2)
        else:
            candidate = paris + timedelta(days=1)

    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)

    return _paris_at_hour(candidate, start_h)


def format_paris_slot(dt_utc: datetime) -> str:
    paris = _ensure_utc(dt_utc).astimezone(_PARIS)
    weekday = _WEEKDAY_NAMES_FR[paris.weekday()]
    month = _MONTH_NAMES_FR[paris.month - 1]
    return (
        f"{weekday} {paris.day} {month} {paris.year} "
        f"à {paris.hour:02d}:{paris.minute:02d} (Paris)"
    )
