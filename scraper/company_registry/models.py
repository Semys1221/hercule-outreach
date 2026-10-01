"""Data models for company registry gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class RejectReason(StrEnum):
    EMPLOYEE_COUNT = "REJECT_EMPLOYEE_COUNT"
    NAF = "REJECT_NAF"
    NOT_FOUND = "REJECT_PAPPERS_NOT_FOUND"
    UNKNOWN_EFFECTIF = "REJECT_UNKNOWN_EFFECTIF"
    UNAVAILABLE = "REJECT_PAPPERS_UNAVAILABLE"
    HOLDING = "REJECT_HOLDING"


class AcceptReason(StrEnum):
    SCORE_UNKNOWN_EFFECTIF = "ACCEPT_SCORE_UNKNOWN_EFFECTIF"


class CompanySize(StrEnum):
    TPE = "TPE"
    PME = "PME"
    ETI = "ETI"
    GE = "GE"
    UNKNOWN = ""


class RegistrySource(StrEnum):
    CACHE = "cache"
    SIRENE = "sirene"
    API = "api"
    ANNUAIRE = "annuaire"
    LEAD = "lead"


@dataclass
class CompanyRecord:
    siren: str = ""
    siret: str = ""
    tranche_effectif: str = ""
    effectif_min: int | None = None
    effectif_label: str = ""
    chiffre_affaires: str = ""
    annee_creation: str = ""
    code_naf: str = ""
    forme_juridique: str = ""
    forme_juridique_code: str = ""
    denomination: str = ""
    commune: str = ""
    source: str = ""
    match_score: float = 0.0
    siret_from_site: bool = False

    def as_lead_fields(
        self,
        *,
        taille: str = "",
        lead_score: int = 0,
        fetched_at: str = "",
    ) -> dict[str, str]:
        return {
            "Siret": self.siret,
            "Siren": self.siren,
            "Effectif": self.effectif_label
            or (str(self.effectif_min) if self.effectif_min is not None else ""),
            "TrancheEffectif": self.tranche_effectif,
            "Naf": self.code_naf,
            "FormeJuridique": self.forme_juridique,
            "AnneeCreation": self.annee_creation,
            "ChiffreAffaires": self.chiffre_affaires,
            "TailleEntreprise": taille,
            "LeadScore": str(lead_score) if lead_score else "",
            "RegistrySource": self.source,
            "RegistryFetchedAt": fetched_at,
        }


@dataclass
class GateVerdict:
    accepted: bool
    reason: str = ""
    company: CompanyRecord = field(default_factory=CompanyRecord)
    lead_score: int = 0
    taille_entreprise: str = ""

    def as_legacy(self) -> "LegacyVerdict":
        return LegacyVerdict(
            accepted=self.accepted,
            reason=self.reason,
            company=LegacyCompany.from_record(self.company),
            lead_score=self.lead_score,
            taille_entreprise=self.taille_entreprise,
        )

    def as_lead_fields(self) -> dict[str, str]:
        return self.as_legacy().as_lead_fields()


@dataclass
class LegacyCompany:
    """Backward-compatible shape for pappers_validator shim."""

    siren: str = ""
    siret: str = ""
    tranche_effectif: str = ""
    effectif_min: int | None = None
    effectif_label: str = ""
    chiffre_affaires: str = ""
    annee_creation: str = ""
    code_naf: str = ""
    forme_juridique: str = ""
    forme_juridique_code: str = ""

    @classmethod
    def from_record(cls, record: CompanyRecord) -> LegacyCompany:
        return cls(
            siren=record.siren,
            siret=record.siret,
            tranche_effectif=record.tranche_effectif,
            effectif_min=record.effectif_min,
            effectif_label=record.effectif_label,
            chiffre_affaires=record.chiffre_affaires,
            annee_creation=record.annee_creation,
            code_naf=record.code_naf,
            forme_juridique=record.forme_juridique,
            forme_juridique_code=record.forme_juridique_code,
        )

    def as_lead_fields(self) -> dict[str, str]:
        return CompanyRecord(
            siren=self.siren,
            siret=self.siret,
            tranche_effectif=self.tranche_effectif,
            effectif_min=self.effectif_min,
            effectif_label=self.effectif_label,
            chiffre_affaires=self.chiffre_affaires,
            annee_creation=self.annee_creation,
            code_naf=self.code_naf,
            forme_juridique=self.forme_juridique,
            forme_juridique_code=self.forme_juridique_code,
        ).as_lead_fields()


@dataclass
class LegacyVerdict:
    accepted: bool
    reason: str = ""
    company: LegacyCompany = field(default_factory=LegacyCompany)
    lead_score: int = 0
    taille_entreprise: str = ""

    def as_lead_fields(self) -> dict[str, str]:
        from datetime import datetime, timezone

        fetched_at = datetime.now(timezone.utc).isoformat()
        return CompanyRecord(
            siren=self.company.siren,
            siret=self.company.siret,
            tranche_effectif=self.company.tranche_effectif,
            effectif_min=self.company.effectif_min,
            effectif_label=self.company.effectif_label,
            chiffre_affaires=self.company.chiffre_affaires,
            annee_creation=self.company.annee_creation,
            code_naf=self.company.code_naf,
            forme_juridique=self.company.forme_juridique,
            forme_juridique_code=self.company.forme_juridique_code,
        ).as_lead_fields(
            taille=self.taille_entreprise,
            lead_score=self.lead_score,
            fetched_at=fetched_at,
        )
