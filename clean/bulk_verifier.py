"""MyEmailVerifier bulk upload API: upload → poll → download."""

from __future__ import annotations

import io
import os
import random
import sys
import time
from typing import Callable, Optional

import pandas as pd
import requests

from core_logic import get_api_key
from paths import data_dir

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.mev_export import validate_mev_upload_emails  # noqa: E402

RUN_MODE_DRY = "dry_run"

_BASE_URL = "https://client.myemailverifier.com"
_UPLOAD_URL = f"{_BASE_URL}/verifier/upload_file"
_HTTP_TIMEOUT = (10, 120)
_MAX_RETRIES = 4
_BACKOFF_BASE = 2.0
_POLL_INTERVAL = 30
_MAX_CHUNK_SIZE = 100_000

BulkProgressCallback = Callable[[str, float], None]


def normalize_status(raw: object) -> str:
    """Map MEV bulk/single labels to pipeline-friendly status strings."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Missing Status"

    key = str(raw).strip()
    if not key:
        return "Missing Status"

    collapsed = key.lower().replace("-", "").replace("_", "").replace(" ", "")
    mapping = {
        "valid": "Valid",
        "invalid": "Invalid",
        "catchall": "Catch All",
        "unknown": "Unknown",
        "greylisted": "Unknown",
        "duplicate": "Duplicate",
        "spamtrap": "Invalid",
        "disposable": "Invalid",
        "toxicdomains": "Invalid",
    }
    return mapping.get(collapsed, key)


def _normalize_email(email: object) -> str:
    if email is None or (isinstance(email, float) and pd.isna(email)):
        return ""
    return str(email).strip().lower()


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    lower_map = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        match = lower_map.get(candidate.lower())
        if match:
            return match
    return None


class BulkEmailVerifierClient:
    """HTTP client for MyEmailVerifier bulk file verification."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=_HTTP_TIMEOUT,
                    **kwargs,
                )

                if response.status_code == 429:
                    retry_after = _BACKOFF_BASE * attempt
                    try:
                        payload = response.json()
                        retry_after = int(payload.get("retryAfter", retry_after))
                    except ValueError:
                        pass
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    time.sleep(_BACKOFF_BASE ** attempt)
                    continue

                return response

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
                time.sleep(_BACKOFF_BASE ** attempt)

        if last_error:
            raise ConnectionError(f"Request failed after retries: {last_error}") from last_error
        raise ConnectionError("Request failed after retries")

    def get_credits(self) -> int:
        url = f"{_BASE_URL}/verifier/getcredits/{self.api_key}"
        response = self._request_with_retry("GET", url)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Invalid credits response: {exc}") from exc

        credits_raw = data.get("Credits") or data.get("credits") or "0"
        try:
            return int(str(credits_raw).strip())
        except ValueError as exc:
            raise ValueError(f"Unexpected credits value: {credits_raw}") from exc

    def upload_file(self, csv_path: str) -> int:
        with open(csv_path, "rb") as handle:
            response = self._request_with_retry(
                "POST",
                _UPLOAD_URL,
                files={"filename": (os.path.basename(csv_path), handle, "text/csv")},
                data={"api_key": self.api_key},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Invalid upload response: {response.text[:500]}") from exc

        if not data.get("status"):
            message = data.get("msg") or data.get("message") or "Upload failed"
            raise RuntimeError(message)

        file_id = data.get("file_id")
        if file_id is None:
            raise RuntimeError("Upload succeeded but no file_id returned")

        return int(file_id)

    def poll_until_complete(
        self,
        file_id: int,
        on_progress: Optional[BulkProgressCallback] = None,
    ) -> dict:
        url = f"{_BASE_URL}/verifier/file_info/{self.api_key}/{file_id}"
        poll_count = 0
        last_percent: int | None = None

        while True:
            poll_count += 1
            response = self._request_with_retry("GET", url)
            try:
                data = response.json()
            except ValueError as exc:
                raise ValueError(f"Invalid file_info response: {exc}") from exc

            if not data.get("status"):
                message = data.get("message") or "File info request failed"
                raise RuntimeError(message)

            file_info = data.get("file") or {}
            status_label = str(file_info.get("status_label") or "").lower()

            if on_progress:
                message, fraction = _format_bulk_progress(file_info)
                on_progress(message, fraction)

            progress_percent = int(file_info.get("progress_percent") or 0)
            if poll_count == 1 or progress_percent != last_percent or poll_count % 4 == 0:
                # #region agent log
                try:
                    from agent_debug_log import agent_debug_log

                    agent_debug_log(
                        "bulk_verifier.py:poll_until_complete",
                        "mev_poll",
                        {
                            "file_id": file_id,
                            "poll_count": poll_count,
                            "status_label": status_label,
                            "progress_percent": progress_percent,
                            "percent_phase1": int(file_info.get("percent_phase1") or 0),
                        },
                        "B",
                    )
                except Exception:
                    pass
                # #endregion
                last_percent = progress_percent

            if status_label == "completed":
                if not file_info.get("downloadable"):
                    raise RuntimeError("Bulk job completed but results are not downloadable yet")
                return file_info

            time.sleep(_POLL_INTERVAL)

    def download_results(self, download_url: str) -> pd.DataFrame:
        response = self._request_with_retry("GET", download_url)
        response.raise_for_status()
        return pd.read_csv(io.StringIO(response.text))

    def parse_results_df(self, df: pd.DataFrame) -> dict[str, str]:
        email_col = _find_column(df, ("Address", "Email", "email", "E-mail"))
        status_col = _find_column(
            df,
            ("Status", "Result", "Verification Status", "verification_status"),
        )

        if not email_col or not status_col:
            raise ValueError(
                f"Could not find email/status columns in bulk result CSV: {list(df.columns)}"
            )

        status_map: dict[str, str] = {}
        for _, row in df.iterrows():
            email = _normalize_email(row[email_col])
            if not email:
                continue
            status_map[email] = normalize_status(row[status_col])

        return status_map


def _format_bulk_progress(file_info: dict) -> tuple[str, float]:
    phase = file_info.get("phase") or "Processing"
    progress_percent = int(file_info.get("progress_percent") or 0)
    percent_phase1 = int(file_info.get("percent_phase1") or 0)
    percent_phase2 = int(file_info.get("percent_phase2") or 0)
    processed = int(file_info.get("processed_res") or 0)
    total = int(file_info.get("total_emails") or file_info.get("total") or 0)
    valid = int(file_info.get("valid") or 0)

    if percent_phase1 < 100:
        fraction = percent_phase1 / 100 * 0.15
        label = f"MEV bulk: {phase} — phase 1 {percent_phase1}%"
    elif percent_phase2 < 100:
        fraction = 0.15 + (percent_phase2 / 100) * 0.15
        label = f"MEV bulk: {phase} — phase 2 {percent_phase2}%"
    else:
        fraction = 0.30 + (progress_percent / 100) * 0.70
        if total:
            label = (
                f"MEV bulk: {phase} — {progress_percent}% "
                f"({valid}/{total} valid, {processed}/{total} processed)"
            )
        else:
            label = f"MEV bulk: {phase} — {progress_percent}%"

    return label, min(max(fraction, 0.0), 1.0)


def _write_upload_csv(emails: list[str], prefix: str, chunk_index: int) -> str:
    os.makedirs(data_dir(), exist_ok=True)
    path = os.path.join(data_dir(), f"{prefix}_mev_upload_{chunk_index}.csv")
    cleaned = validate_mev_upload_emails(emails)
    upload_df = pd.DataFrame({"email": cleaned})
    upload_df.to_csv(path, index=False)
    return path


def _simulate_dry_run(emails: list[str]) -> dict[str, str]:
    status_map: dict[str, str] = {}
    for email in emails:
        normalized = _normalize_email(email)
        if not normalized:
            continue
        time.sleep(0.01)
        status_map[normalized] = random.choice(
            ["Valid", "Valid", "Invalid", "Catch All", "Unknown"]
        )
    return status_map


def fetch_mev_credits() -> int | None:
    """Return current MyEmailVerifier credit balance, or None if unavailable."""
    api_key = get_api_key()
    if not api_key:
        return None
    try:
        return BulkEmailVerifierClient(api_key).get_credits()
    except (ValueError, ConnectionError, requests.exceptions.RequestException):
        return None


def verify_emails_bulk(
    emails: list[str],
    *,
    run_mode: str,
    on_progress: Optional[BulkProgressCallback] = None,
    artifact_prefix: Optional[str] = None,
    existing_status_map: Optional[dict[str, str]] = None,
    on_status_map_updated: Optional[Callable[[dict[str, str]], None]] = None,
) -> dict[str, str]:
    """
    Verify emails via MEV bulk API.
    Returns lowercase email -> normalized Verification_Status.
    Skips emails already present in existing_status_map (resume support).
    """
    valid_emails = [
        str(email).strip()
        for email in emails
        if email is not None
        and str(email).strip()
        and str(email).strip().lower() != "nan"
    ]

    merged: dict[str, str] = {
        _normalize_email(email): normalize_status(status)
        for email, status in (existing_status_map or {}).items()
        if _normalize_email(email)
    }

    pending_emails = [
        email for email in valid_emails if _normalize_email(email) not in merged
    ]

    if run_mode == RUN_MODE_DRY:
        if on_progress:
            on_progress("Dry run: simulating bulk verification...", 0.5)
        simulated = _simulate_dry_run(pending_emails)
        merged.update(simulated)
        if on_status_map_updated:
            on_status_map_updated(merged)
        if on_progress:
            on_progress(
                f"Dry run complete — {len(merged)} email(s) simulated "
                f"({len(simulated)} new, {len(merged) - len(simulated)} resumed).",
                1.0,
            )
        return merged

    if not pending_emails:
        if on_progress:
            on_progress(
                f"All {len(merged)} email(s) already verified — skipping MEV upload.",
                1.0,
            )
        return merged

    api_key = get_api_key()
    if not api_key:
        raise ValueError("MYEMAILVERIFIER_API_KEY is not set")

    client = BulkEmailVerifierClient(api_key)
    prefix = artifact_prefix or "bulk"
    chunks = [
        pending_emails[index : index + _MAX_CHUNK_SIZE]
        for index in range(0, len(pending_emails), _MAX_CHUNK_SIZE)
    ]

    if on_progress:
        resumed = len(merged)
        if resumed:
            on_progress(
                f"Resuming — {resumed} already verified, "
                f"{len(pending_emails)} remaining...",
                0.02,
            )
        else:
            on_progress("Checking MyEmailVerifier credits...", 0.02)

    credits = client.get_credits()
    if credits < len(pending_emails):
        raise RuntimeError(
            f"Insufficient MEV credits: need {len(pending_emails)} more, have {credits}"
        )

    upload_paths: list[str] = []

    try:
        for chunk_index, chunk in enumerate(chunks):
            chunk_label = f"chunk {chunk_index + 1}/{len(chunks)}" if len(chunks) > 1 else "list"
            if on_progress:
                on_progress(f"Uploading {len(chunk)} email(s) ({chunk_label})...", 0.05)

            upload_path = _write_upload_csv(chunk, prefix, chunk_index)
            upload_paths.append(upload_path)
            file_id = client.upload_file(upload_path)

            if on_progress:
                on_progress(f"MEV bulk job queued (file_id={file_id})...", 0.08)

            def chunk_progress(message: str, fraction: float) -> None:
                if not on_progress:
                    return
                chunk_base = chunk_index / len(chunks)
                chunk_span = 1.0 / len(chunks)
                on_progress(message, chunk_base + fraction * chunk_span)

            file_info = client.poll_until_complete(file_id, on_progress=chunk_progress)

            download_url = file_info.get("download_all_csv") or file_info.get("file_path")
            if not download_url:
                raise RuntimeError("Bulk job completed but no download URL was returned")

            if on_progress:
                on_progress("Downloading bulk verification results...", 0.92)

            results_df = client.download_results(download_url)
            merged.update(client.parse_results_df(results_df))

            if on_status_map_updated:
                on_status_map_updated(dict(merged))

        if on_progress:
            on_progress(
                f"MEV bulk complete — {len(merged)} result(s) "
                f"({len(pending_emails)} newly verified).",
                1.0,
            )

        return merged

    finally:
        for path in upload_paths:
            try:
                os.remove(path)
            except OSError:
                pass
