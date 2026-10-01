"""Free local email verification: syntax, junk domains, MX DNS."""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import dns.resolver
import pandas as pd

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

GARBAGE_DOMAINS = {
    "example.com",
    "test.com",
    "domain.com",
    "fake.com",
    "spam.com",
    "email.com",
}

_DNS_TIMEOUT = 2
_DEFAULT_DNS_WORKERS = 32

_thread_local = threading.local()


@dataclass
class QuickVerifyResult:
    clean_df: pd.DataFrame
    rejected_df: pd.DataFrame
    email_column: str
    format_errors: int
    garbage_domains: int
    dns_errors: int
    total_processed: int
    dropped_email_columns: list[str]


def is_email_column(series: pd.Series) -> bool:
    """True if at least 50% of non-empty rows match the email regex."""
    clean_series = series.dropna().astype(str).str.strip()
    if clean_series.empty:
        return False

    valid_count = clean_series.apply(lambda x: bool(EMAIL_REGEX.match(x))).sum()
    return (valid_count / len(clean_series)) > 0.5


def detect_email_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if is_email_column(df[col]):
            return col
    return None


def _get_resolver() -> dns.resolver.Resolver:
    resolver = getattr(_thread_local, "resolver", None)
    if resolver is None:
        resolver = dns.resolver.Resolver()
        resolver.timeout = _DNS_TIMEOUT
        resolver.lifetime = _DNS_TIMEOUT
        _thread_local.resolver = resolver
    return resolver


def _resolve_mx(domain: str) -> tuple[str, bool]:
    try:
        _get_resolver().resolve(domain, "MX")
        return domain, True
    except Exception:
        return domain, False


def check_mx_record(domain: str) -> bool:
    return _resolve_mx(domain)[1]


def _resolve_mx_batch(
    domains: set[str],
    *,
    max_workers: int = _DEFAULT_DNS_WORKERS,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, bool]:
    if not domains:
        return {}

    mx_cache: dict[str, bool] = {}
    total = len(domains)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_resolve_mx, domain): domain for domain in domains}
        for future in as_completed(futures):
            domain, ok = future.result()
            mx_cache[domain] = ok
            completed += 1
            if on_progress and (completed % 10 == 0 or completed == total):
                on_progress(completed, total)

    return mx_cache


def _normalize_email(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def quick_verify_dataframe(
    df: pd.DataFrame,
    email_column: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_dns_workers: int = _DEFAULT_DNS_WORKERS,
) -> QuickVerifyResult:
    """
    Filter rows by email format, junk domains, and MX records.
    Keeps a single email column when multiple are detected.
    """
    working = df.copy()
    email_cols = [col for col in working.columns if is_email_column(working[col])]

    if email_column and email_column in working.columns:
        primary_email_col = email_column
        dropped = [col for col in email_cols if col != email_column]
    elif email_cols:
        primary_email_col = email_cols[0]
        dropped = email_cols[1:]
    else:
        raise ValueError("No valid email column detected in this CSV.")

    if dropped:
        working = working.drop(columns=dropped)

    total_rows = len(working)
    pending_dns: list[tuple[pd.Series, str]] = []
    pre_rejected: list[pd.Series] = []
    c_format_err = 0
    c_garbage = 0

    for index, (_, row) in enumerate(working.iterrows()):
        email = _normalize_email(row[primary_email_col])

        if not EMAIL_REGEX.match(email):
            rejected = row.copy()
            rejected["Quick_Reject_Reason"] = "bad_format"
            pre_rejected.append(rejected)
            c_format_err += 1
        else:
            domain = email.split("@", 1)[1]
            if domain in GARBAGE_DOMAINS:
                rejected = row.copy()
                rejected["Quick_Reject_Reason"] = "garbage_domain"
                pre_rejected.append(rejected)
                c_garbage += 1
            else:
                pending_dns.append((row, domain))

        if on_progress and (index % 50 == 0 or index == total_rows - 1):
            on_progress(index + 1, total_rows)

    unique_domains = {domain for _, domain in pending_dns}
    mx_cache = _resolve_mx_batch(
        unique_domains,
        max_workers=max_dns_workers,
        on_progress=on_progress,
    )

    valid_rows: list[pd.Series] = []
    dns_rejected: list[pd.Series] = []
    c_dns_err = 0

    for row, domain in pending_dns:
        if mx_cache.get(domain, False):
            valid_rows.append(row)
        else:
            rejected = row.copy()
            rejected["Quick_Reject_Reason"] = "no_mx"
            dns_rejected.append(rejected)
            c_dns_err += 1

    rejected_rows = pre_rejected + dns_rejected
    clean_df = pd.DataFrame(valid_rows) if valid_rows else working.iloc[0:0].copy()
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else working.iloc[0:0].copy()

    return QuickVerifyResult(
        clean_df=clean_df,
        rejected_df=rejected_df,
        email_column=primary_email_col,
        format_errors=c_format_err,
        garbage_domains=c_garbage,
        dns_errors=c_dns_err,
        total_processed=total_rows,
        dropped_email_columns=dropped,
    )
