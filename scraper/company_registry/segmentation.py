"""Derived segmentation fields for fiscal/compta outreach angles."""

from __future__ import annotations

import re
from typing import Any

from company_registry.classifier import classify_company, parse_ca_euros
from company_registry.models import CompanyRecord, CompanySize
from company_registry.scorer import company_age_years, is_entreprise_individuelle, is_holding

_COMPTA_KEYWORDS = (
    "expert-comptable",
    "expert comptable",
    "cabinet comptable",
    "expertise comptable",
    "commissaire aux comptes",
)

_OUTIL_COMPTA_KEYWORDS = (
    "dougs",
    "pennylane",
    "indy",
    "fiducial",
    "in extenso",
    "sage comptabilité",
    "quickbooks",
)

_TRAVEL_NAF_PREFIXES = ("46", "62", "70", "49", "79", "52")


def _site_text(row: dict[str, str]) -> str:
    return str(row.get("_website_text") or row.get("_html_text") or "").lower()


def detect_compta_on_site(site_text: str) -> tuple[str, str]:
    """Return (deja_expert_comptable, outil_compta_detecte) as oui/non."""
    text = (site_text or "").lower()
    if not text:
        return "non", "non"
    deja = "oui" if any(kw in text for kw in _COMPTA_KEYWORDS) else "non"
    outil = "oui" if any(kw in text for kw in _OUTIL_COMPTA_KEYWORDS) else "non"
    return deja, outil


def _naf_normalized(code: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (code or "").lower())


def _is_travel_naf(code_naf: str) -> bool:
    naf = _naf_normalized(code_naf)
    return any(naf.startswith(prefix) for prefix in _TRAVEL_NAF_PREFIXES)


def estimate_economie_estimee(
    *,
    effectif_min: int | None,
    chiffre_affaires: str = "",
) -> str:
    ca = parse_ca_euros(chiffre_affaires)
    base = 1200
    if effectif_min is not None:
        base += effectif_min * 220
    if ca is not None:
        base += int(ca * 0.0015)
    if base < 800:
        base = 800
    if base > 12000:
        base = 12000
    rounded = int(round(base / 100.0)) * 100
    return str(rounded)


def compute_angle_flags(
    record: CompanyRecord,
    *,
    site_text: str = "",
    nb_etablissements: int = 0,
) -> dict[str, str]:
    deja_ec, outil_compta = detect_compta_on_site(site_text)
    eff = record.effectif_min
    ca = parse_ca_euros(record.chiffre_affaires)
    age = company_age_years(record)
    taille = classify_company(
        effectif_min=record.effectif_min,
        chiffre_affaires=record.chiffre_affaires,
    )

    ei = bool(record.est_entrepreneur_individuel) or is_entreprise_individuelle(record)
    forme = (record.forme_juridique or "").lower()
    angle_ir = (
        "oui"
        if ei
        or "entrepreneur individuel" in forme
        or "eurl" in forme
        or record.forme_juridique_code in {"5498", "5499"}
        else "non"
    )

    etabs = max(nb_etablissements, record.nb_etablissements)
    angle_frais_km = (
        "oui" if _is_travel_naf(record.code_naf) or etabs >= 2 else "non"
    )

    angle_charges = (
        "oui"
        if deja_ec == "non"
        and not is_holding(record)
        and eff is not None
        and 3 <= eff <= 50
        and (ca is None or 300_000 <= ca <= 10_000_000)
        and (age is None or age >= 2)
        else "non"
    )

    angle_cotisations = (
        "oui"
        if deja_ec == "non"
        and not is_holding(record)
        and eff is not None
        and 1 <= eff <= 49
        and taille in {CompanySize.TPE, CompanySize.PME, CompanySize.UNKNOWN}
        else "non"
    )

    return {
        "AngleIr": angle_ir,
        "AngleCharges": angle_charges,
        "AngleFraisKm": angle_frais_km,
        "AngleCotisations": angle_cotisations,
        "EconomieEstimee": estimate_economie_estimee(
            effectif_min=record.effectif_min,
            chiffre_affaires=record.chiffre_affaires,
        ),
        "DejaExpertComptable": deja_ec,
        "OutilComptaDetecte": outil_compta,
    }


def enrich_lead_segmentation(
    record: CompanyRecord,
    row: dict[str, Any],
) -> dict[str, str]:
    """Merge registry + row context into Instantly/CSV segmentation fields."""
    site_text = _site_text(row)
    flags = compute_angle_flags(
        record,
        site_text=site_text,
        nb_etablissements=record.nb_etablissements,
    )
    extra = {
        "DirigeantPrenom": record.dirigeant_prenom,
        "DirigeantNom": record.dirigeant_nom,
        "DirigeantQualite": record.dirigeant_qualite,
        "ResultatNet": record.resultat_net,
        "EstEntrepreneurIndividuel": "oui" if record.est_entrepreneur_individuel else "non",
        "CategorieEntreprise": record.categorie_entreprise,
        "NbEtablissements": str(record.nb_etablissements) if record.nb_etablissements else "",
        "Phone": str(row.get("Phone") or "").strip(),
        "Rating": str(row.get("Rating") or "").strip(),
        "ReviewsCount": str(row.get("ReviewsCount") or "").strip(),
    }
    return {**extra, **flags}
