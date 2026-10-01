"""SQLite persistence for subsequence / reply prompt version history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from config import history_db_path

DOMAIN_SUBSEQUENCE = "subsequence"
DOMAIN_REPLY_PROMPT = "reply_prompt"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS editor_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    niche_key TEXT NOT NULL,
    item_key TEXT NOT NULL,
    campaign_id TEXT,
    subject TEXT,
    body_text TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_editor_version_lookup
    ON editor_version (domain, niche_key, item_key, created_at DESC);
"""


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@contextmanager
def connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path else history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        yield conn
    finally:
        conn.close()


def resolve_niche_key(campaign_id: str, preset_id: str | None) -> str:
    preset = (preset_id or "").strip()
    if preset:
        return preset
    cid = campaign_id.strip()
    return f"campaign:{cid}" if cid else "unknown"


def insert_version(
    *,
    domain: str,
    niche_key: str,
    item_key: str,
    body_text: str,
    campaign_id: str | None = None,
    subject: str | None = None,
    label: str | None = None,
    set_active: bool = True,
    db_path: str | None = None,
) -> int:
    created_at = _utc_now_iso()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO editor_version
                (domain, niche_key, item_key, campaign_id, subject, body_text, label, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                domain,
                niche_key,
                item_key,
                campaign_id,
                subject,
                body_text,
                (label or "").strip() or None,
                created_at,
            ),
        )
        version_id = int(cur.lastrowid)
        conn.commit()
        if set_active:
            set_active_version(version_id, db_path=db_path, _conn=conn)
        return version_id


def set_active_version(
    version_id: int,
    *,
    db_path: str | None = None,
    _conn: sqlite3.Connection | None = None,
) -> None:
    def _run(conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT domain, niche_key, item_key FROM editor_version WHERE id = ?",
            (version_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Version introuvable: {version_id}")
        conn.execute(
            """
            UPDATE editor_version SET is_active = 0
            WHERE domain = ? AND niche_key = ? AND item_key = ?
            """,
            (row["domain"], row["niche_key"], row["item_key"]),
        )
        conn.execute(
            "UPDATE editor_version SET is_active = 1 WHERE id = ?",
            (version_id,),
        )
        conn.commit()

    if _conn is not None:
        _run(_conn)
        return
    with connect(db_path) as conn:
        _run(conn)


def list_versions(
    *,
    domain: str,
    niche_key: str,
    item_key: str | None = None,
    limit: int = 100,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        if item_key:
            rows = conn.execute(
                """
                SELECT * FROM editor_version
                WHERE domain = ? AND niche_key = ? AND item_key = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (domain, niche_key, item_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM editor_version
                WHERE domain = ? AND niche_key = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (domain, niche_key, limit),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_version(version_id: int, *, db_path: str | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM editor_version WHERE id = ?",
            (version_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "domain": row["domain"],
        "niche_key": row["niche_key"],
        "item_key": row["item_key"],
        "campaign_id": row["campaign_id"],
        "subject": row["subject"],
        "body_text": row["body_text"],
        "label": row["label"],
        "created_at": row["created_at"],
        "is_active": bool(row["is_active"]),
    }


def ensure_seeded_from_current(
    *,
    domain: str,
    niche_key: str,
    item_key: str,
    body_text: str,
    campaign_id: str | None = None,
    subject: str | None = None,
    db_path: str | None = None,
) -> bool:
    """Insert initial import row if no history exists for this triplet. Returns True if seeded."""
    existing = list_versions(
        domain=domain,
        niche_key=niche_key,
        item_key=item_key,
        limit=1,
        db_path=db_path,
    )
    if existing:
        return False
    if not str(body_text or "").strip():
        return False
    insert_version(
        domain=domain,
        niche_key=niche_key,
        item_key=item_key,
        body_text=body_text,
        campaign_id=campaign_id,
        subject=subject,
        label="Import automatique",
        set_active=True,
        db_path=db_path,
    )
    return True


def promote_version(
    version_id: int,
    *,
    push_to_prod: Callable[[dict[str, Any]], None],
    db_path: str | None = None,
) -> dict[str, Any]:
    row = get_version(version_id, db_path=db_path)
    if not row:
        raise ValueError(f"Version introuvable: {version_id}")
    push_to_prod(row)
    set_active_version(version_id, db_path=db_path)
    return row
