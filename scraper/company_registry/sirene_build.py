"""Build local SIRENE SQLite index from INSEE open data."""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from typing import Callable

import requests

from company_registry.config import DEFAULT_SIRENE_PATH
from company_registry.sirene_index import ensure_schema, normalize_denomination

# Stable data.gouv resource URL (redirects to current monthly StockEtablissement zip)
STOCK_ETABLISSEMENT_RESOURCE_URL = (
    "https://www.data.gouv.fr/datasets/r/0651fb76-bcf3-4f6a-a38d-bc04fa708576"
)

_DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024
_DOWNLOAD_PROGRESS_BYTES = 100 * 1024 * 1024
_DOWNLOAD_MAX_ATTEMPTS = 3


def sirene_db_path(path: str | None = None) -> str:
    return path or DEFAULT_SIRENE_PATH


def check_index(path: str | None = None) -> dict:
    db_path = sirene_db_path(path)
    if not os.path.isfile(db_path):
        return {"exists": False, "path": db_path, "rows": 0, "age_days": None}
    mtime = datetime.fromtimestamp(os.path.getmtime(db_path), tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - mtime).days
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM etablissements").fetchone()
        count = int(row[0]) if row else 0
    return {"exists": True, "path": db_path, "rows": count, "age_days": age_days, "mtime": mtime.isoformat()}


def _resolve_download_url(source_url: str) -> str:
    """Follow redirects to the current static.data.gouv.fr file URL."""
    response = requests.head(source_url, allow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.url


def _download_file(
    url: str,
    dest_path: str,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    last_error: Exception | None = None
    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            with requests.get(url, stream=True, timeout=(30, 600)) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                last_logged = 0
                with open(dest_path, "wb") as out:
                    for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                        if not chunk:
                            continue
                        out.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - last_logged >= _DOWNLOAD_PROGRESS_BYTES:
                            if total:
                                _log(
                                    f"  downloaded {downloaded / (1024 * 1024):.0f} / "
                                    f"{total / (1024 * 1024):.0f} MB"
                                )
                            else:
                                _log(f"  downloaded {downloaded / (1024 * 1024):.0f} MB")
                            last_logged = downloaded
            return
        except (requests.ConnectionError, requests.Timeout, requests.ChunkedEncodingError) as exc:
            last_error = exc
            if os.path.isfile(dest_path):
                os.remove(dest_path)
            if attempt < _DOWNLOAD_MAX_ATTEMPTS:
                wait_s = 2 ** attempt
                _log(f"Download failed ({exc}); retrying in {wait_s}s (attempt {attempt}/{_DOWNLOAD_MAX_ATTEMPTS})...")
                time.sleep(wait_s)
    raise RuntimeError(f"SIRENE download failed after {_DOWNLOAD_MAX_ATTEMPTS} attempts: {last_error}")


def _row_to_record(row: dict[str, str]) -> tuple | None:
    """Map a StockEtablissement CSV row to an etablissements INSERT tuple."""
    siren = (row.get("siren") or "").strip()
    nic = (row.get("nic") or "").strip()
    siret = (row.get("siret") or "").strip() or f"{siren}{nic}"
    if len(siret) != 14 or not siret.isdigit():
        return None
    denom = (
        (row.get("denominationUsuelleEtablissement") or "").strip()
        or (row.get("enseigne1Etablissement") or "").strip()
    )
    return (
        siret,
        siren,
        denom,
        normalize_denomination(denom),
        (row.get("activitePrincipaleEtablissement") or "").strip(),
        (row.get("trancheEffectifsEtablissement") or "").strip(),
        "",
        (row.get("libelleCommuneEtablissement") or "").strip(),
    )


def build_index(
    *,
    dest_path: str | None = None,
    log_cb: Callable[[str], None] | None = None,
    max_rows: int | None = None,
    source_url: str | None = None,
) -> str:
    """Download StockEtablissement and import into SQLite."""
    dest = sirene_db_path(dest_path)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    def _log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    resource_url = source_url or STOCK_ETABLISSEMENT_RESOURCE_URL
    _log(f"Resolving SIRENE stock URL from {resource_url}...")
    download_url = _resolve_download_url(resource_url)
    _log(f"Downloading SIRENE stock from {download_url}...")

    tmp_dir = tempfile.mkdtemp(prefix="sirene_build_")
    try:
        zip_path = os.path.join(tmp_dir, "stock.zip")
        _download_file(download_url, zip_path, log_cb=_log)
        _log("Extracting archive...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)
        csv_name = next(
            (name for name in os.listdir(tmp_dir) if name.endswith(".csv")),
            None,
        )
        if not csv_name:
            raise RuntimeError("StockEtablissement CSV not found in archive")
        csv_path = os.path.join(tmp_dir, csv_name)

        tmp_db = dest + ".tmp"
        if os.path.isfile(tmp_db):
            os.remove(tmp_db)
        with closing(sqlite3.connect(tmp_db)) as conn:
            ensure_schema(conn)
            _log("Importing establishments...")
            imported = 0
            batch: list[tuple] = []
            with open(csv_path, encoding="utf-8", errors="replace", newline="") as csv_file:
                for row in csv.DictReader(csv_file):
                    record = _row_to_record(row)
                    if record is None:
                        continue
                    batch.append(record)
                    if max_rows and imported + len(batch) >= max_rows:
                        keep = max_rows - imported
                        if keep < len(batch):
                            batch = batch[:keep]
                        if batch:
                            conn.executemany(
                                """
                                INSERT OR REPLACE INTO etablissements
                                (siret, siren, denomination, denomination_norm, naf,
                                 tranche_effectif, forme_juridique_code, commune)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                batch,
                            )
                            conn.commit()
                            imported += len(batch)
                            batch.clear()
                        break
                    if len(batch) >= 5000:
                        conn.executemany(
                            """
                            INSERT OR REPLACE INTO etablissements
                            (siret, siren, denomination, denomination_norm, naf,
                             tranche_effectif, forme_juridique_code, commune)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            batch,
                        )
                        conn.commit()
                        imported += len(batch)
                        batch.clear()
                        if imported % 500_000 == 0:
                            _log(f"  {imported:,} rows imported...")
                if batch:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO etablissements
                        (siret, siren, denomination, denomination_norm, naf,
                         tranche_effectif, forme_juridique_code, commune)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    conn.commit()
                    imported += len(batch)
        _log(f"Import complete — {imported:,} rows. Moving to {dest}")
        shutil.move(tmp_db, dest)
        return dest
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
