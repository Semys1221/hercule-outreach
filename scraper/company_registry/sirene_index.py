"""Local SIRENE SQLite index lookup."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing

from rapidfuzz import fuzz

from company_registry.classifier import tranche_min
from company_registry.matcher import normalize_name
from company_registry.models import CompanyRecord, RegistrySource
from company_registry.siret_extract import digits


class SireneIndex:
    def __init__(self, path: str) -> None:
        self.path = path
        self._available = os.path.isfile(path)

    @property
    def available(self) -> bool:
        return self._available

    def lookup_siret(self, siret: str) -> CompanyRecord | None:
        if not self._available or len(siret) != 14:
            return None
        return self._fetch_one("SELECT * FROM etablissements WHERE siret = ?", (siret,))

    def lookup_siren(self, siren: str) -> CompanyRecord | None:
        if not self._available or len(siren) != 9:
            return None
        return self._fetch_one(
            "SELECT * FROM etablissements WHERE siren = ? ORDER BY siret LIMIT 1",
            (siren,),
        )

    def lookup_name_city(self, company: str, city: str, limit: int = 5) -> CompanyRecord | None:
        if not self._available or not company.strip():
            return None
        norm = normalize_name(company)
        city_l = city.strip().lower()
        like = f"%{norm[:40]}%"
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            if city_l:
                rows = conn.execute(
                    """
                    SELECT * FROM etablissements
                    WHERE denomination_norm LIKE ? AND LOWER(commune) LIKE ?
                    LIMIT ?
                    """,
                    (like, f"%{city_l}%", limit * 3),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM etablissements WHERE denomination_norm LIKE ? LIMIT ?",
                    (like, limit * 3),
                ).fetchall()
        if not rows:
            return None
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            name_score = fuzz.token_sort_ratio(norm, row["denomination_norm"] or "")
            commune = (row["commune"] or "").lower()
            city_score = 100.0 if city_l and city_l in commune else (
                float(fuzz.partial_ratio(city_l, commune)) if city_l else 50.0
            )
            scored.append((name_score * 0.7 + city_score * 0.3, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = scored[0]
        if best_score < 55:
            return None
        return self._row_to_record(best_row, match_score=best_score)

    def _fetch_one(self, sql: str, params: tuple) -> CompanyRecord | None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: sqlite3.Row, match_score: float = 100.0) -> CompanyRecord:
        tranche = str(row["tranche_effectif"] or "")
        forme_code = str(row["forme_juridique_code"] or "")
        return CompanyRecord(
            siren=str(row["siren"] or ""),
            siret=str(row["siret"] or ""),
            tranche_effectif=tranche,
            effectif_min=tranche_min(tranche),
            effectif_label=tranche,
            code_naf=str(row["naf"] or ""),
            forme_juridique_code=forme_code,
            forme_juridique=forme_code,
            denomination=str(row["denomination"] or ""),
            commune=str(row["commune"] or ""),
            source=RegistrySource.SIRENE,
            match_score=match_score,
        )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etablissements (
            siret TEXT PRIMARY KEY,
            siren TEXT NOT NULL,
            denomination TEXT,
            denomination_norm TEXT,
            naf TEXT,
            tranche_effectif TEXT,
            forme_juridique_code TEXT,
            commune TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_etablissements_siren ON etablissements(siren)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_etablissements_denom ON etablissements(denomination_norm)"
    )
    conn.commit()


def normalize_denomination(name: str) -> str:
    return normalize_name(name)
