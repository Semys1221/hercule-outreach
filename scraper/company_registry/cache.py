"""Persistent SIREN/SIRET cache."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from company_registry.models import CompanyRecord, GateVerdict


class RegistryCache:
    def __init__(self, path: str = "") -> None:
        self.path = path
        self._memory: dict[str, dict[str, Any]] = {}
        if path and os.path.isfile(path):
            self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError, TypeError):
            return
        if isinstance(payload, dict):
            self._memory = payload

    def flush(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._memory, f, ensure_ascii=False, indent=0)

    @staticmethod
    def cache_key(company: str, city: str, siret: str = "", siren: str = "") -> str:
        ident = (siret or siren or "").strip()
        if ident:
            return f"id:{ident}"
        return f"name:{(company or '').strip().lower()}|{(city or '').strip().lower()}"

    def get(self, key: str) -> GateVerdict | None:
        raw = self._memory.get(key)
        if not raw:
            return None
        return self._deserialize(raw)

    def remember(self, key: str, verdict: GateVerdict, record: CompanyRecord | None) -> None:
        self._memory[key] = self._serialize(verdict)
        if record and record.siren:
            self._memory[f"id:{record.siren}"] = self._serialize(verdict)
        if record and record.siret:
            self._memory[f"id:{record.siret}"] = self._serialize(verdict)

    @staticmethod
    def _serialize(verdict: GateVerdict) -> dict[str, Any]:
        return {
            "accepted": verdict.accepted,
            "reason": verdict.reason,
            "lead_score": verdict.lead_score,
            "taille_entreprise": verdict.taille_entreprise,
            "company": {
                "siren": verdict.company.siren,
                "siret": verdict.company.siret,
                "tranche_effectif": verdict.company.tranche_effectif,
                "effectif_min": verdict.company.effectif_min,
                "effectif_label": verdict.company.effectif_label,
                "chiffre_affaires": verdict.company.chiffre_affaires,
                "annee_creation": verdict.company.annee_creation,
                "code_naf": verdict.company.code_naf,
                "forme_juridique": verdict.company.forme_juridique,
                "forme_juridique_code": verdict.company.forme_juridique_code,
                "denomination": verdict.company.denomination,
                "commune": verdict.company.commune,
                "source": verdict.company.source,
            },
        }

    @staticmethod
    def _deserialize(raw: dict[str, Any]) -> GateVerdict:
        company_raw = raw.get("company") if isinstance(raw.get("company"), dict) else {}
        company = CompanyRecord(
            siren=str(company_raw.get("siren") or ""),
            siret=str(company_raw.get("siret") or ""),
            tranche_effectif=str(company_raw.get("tranche_effectif") or ""),
            effectif_min=company_raw.get("effectif_min"),
            effectif_label=str(company_raw.get("effectif_label") or ""),
            chiffre_affaires=str(company_raw.get("chiffre_affaires") or ""),
            annee_creation=str(company_raw.get("annee_creation") or ""),
            code_naf=str(company_raw.get("code_naf") or ""),
            forme_juridique=str(company_raw.get("forme_juridique") or ""),
            forme_juridique_code=str(company_raw.get("forme_juridique_code") or ""),
            denomination=str(company_raw.get("denomination") or ""),
            commune=str(company_raw.get("commune") or ""),
            source=str(company_raw.get("source") or ""),
        )
        return GateVerdict(
            accepted=bool(raw.get("accepted")),
            reason=str(raw.get("reason") or ""),
            company=company,
            lead_score=int(raw.get("lead_score") or 0),
            taille_entreprise=str(raw.get("taille_entreprise") or ""),
        )
