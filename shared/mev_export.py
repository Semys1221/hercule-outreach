"""MyEmailVerifier-ready single-column email CSV export."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable, Sequence, TextIO

import pandas as pd

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
MEV_HEADER = "email"
DEFAULT_EMAIL_COLUMNS: tuple[str, ...] = (
    "email",
    "Email",
    "E-mail",
    "contact",
    "Contact",
)


def normalize_email(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def is_valid_email(value: str) -> bool:
    normalized = normalize_email(value)
    return bool(normalized) and "@" in normalized and bool(EMAIL_REGEX.match(normalized))


def extract_emails(values: Iterable[object], *, dedupe: bool = True) -> list[str]:
    seen: set[str] = set()
    emails: list[str] = []
    for value in values:
        normalized = normalize_email(value)
        if not is_valid_email(normalized):
            continue
        if dedupe and normalized in seen:
            continue
        seen.add(normalized)
        emails.append(normalized)
    return emails


def _find_email_column(df: pd.DataFrame, column_candidates: Sequence[str]) -> str | None:
    lower_map = {col.lower(): col for col in df.columns}
    for candidate in column_candidates:
        match = lower_map.get(candidate.lower())
        if match:
            return match

    for col in df.columns:
        series = df[col].dropna().astype(str).str.strip()
        if series.empty:
            continue
        valid_count = series.apply(lambda value: is_valid_email(value)).sum()
        if valid_count / len(series) > 0.5:
            return col
    return None


def extract_emails_from_dataframe(
    df: pd.DataFrame,
    column_candidates: Sequence[str] = DEFAULT_EMAIL_COLUMNS,
) -> list[str]:
    if df.empty:
        return []
    column = _find_email_column(df, column_candidates)
    if not column:
        return []
    return extract_emails(df[column].tolist())


def audit_emails(emails: Iterable[object]) -> dict[str, int]:
    total = 0
    valid = 0
    invalid = 0
    for value in emails:
        total += 1
        if is_valid_email(str(value)):
            valid += 1
        else:
            invalid += 1
    return {"total": total, "valid": valid, "invalid": invalid}


def write_mev_csv(emails: Sequence[str], path: str | Path | TextIO) -> int:
    cleaned = extract_emails(emails)
    if isinstance(path, (str, Path)):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("w", newline="", encoding="utf-8")
        close_handle = True
    else:
        handle = path
        close_handle = False

    try:
        writer = csv.writer(handle)
        writer.writerow([MEV_HEADER])
        for email in cleaned:
            writer.writerow([email])
    finally:
        if close_handle:
            handle.close()
    return len(cleaned)


def mev_csv_bytes(emails: Sequence[str]) -> bytes:
    buffer = io.StringIO()
    write_mev_csv(emails, buffer)
    return buffer.getvalue().encode("utf-8")


def validate_mev_upload_emails(emails: Sequence[str]) -> list[str]:
    cleaned = extract_emails(emails)
    if not cleaned:
        raise ValueError(
            "No valid email addresses for MEV upload. "
            "Expected a single-column CSV with header 'email'."
        )
    return cleaned


def sync_mev_csv_from_leads_csv(
    leads_csv_path: str | Path,
    mev_csv_path: str | Path | None = None,
    *,
    email_column: str = "Email",
) -> int:
    leads_path = Path(leads_csv_path)
    if not leads_path.is_file():
        return 0

    target = Path(mev_csv_path) if mev_csv_path else leads_path.parent / "mev_emails.csv"
    df = pd.read_csv(leads_path)
    if df.empty:
        write_mev_csv([], target)
        return 0

    column = _find_email_column(df, (email_column, *DEFAULT_EMAIL_COLUMNS))
    if not column:
        write_mev_csv([], target)
        return 0

    count = write_mev_csv(df[column].tolist(), target)
    return count
