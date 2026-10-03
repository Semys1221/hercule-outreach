"""Hybrid lead scoring for company gate."""

from __future__ import annotations

import re
from datetime import datetime

from company_registry.classifier import classify_company
from company_registry.config import (
    EI_FORME_CODES,
    HOLDING_FORME_CODES,
    HOLDING_NAF_PREFIXES,
)
from company_registry.matcher import score_name_city_match
from company_registry.models import CompanyRecord


def is_entreprise_individuelle(record: CompanyRecord) -> bool:
    if record.forme_juridique_code in EI_FORME_CODES:
        return True
    return bool(re.search(r"\b(entrepreneur\s+individuel|eirl|ei)\b", record.forme_juridique, re.I))


def is_holding(record: CompanyRecord) -> bool:
    code = digits_only(record.forme_juridique_code)
    if code in HOLDING_FORME_CODES:
        return True
    naf = (record.code_naf or "").replace(" ", "").upper()
    return any(naf.startswith(prefix.replace(".", "")) or naf.startswith(prefix) for prefix in HOLDING_NAF_PREFIXES)


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def naf_matches(record: CompanyRecord, prefixes: list[str]) -> bool:
    if not prefixes or not record.code_naf:
        return bool(not prefixes)
    normalized = record.code_naf.lower().replace(" ", "")
    return any(normalized.startswith(prefix.replace(" ", "").lower()) for prefix in prefixes)


def company_age_years(record: CompanyRecord, now_year: int | None = None) -> int | None:
    year_raw = (record.annee_creation or "").strip()
    if not year_raw or len(year_raw) < 4:
        return None
    try:
        year = int(year_raw[:4])
    except ValueError:
        return None
    current = now_year or datetime.now().year
    return max(current - year, 0)


def compute_lead_score(
    record: CompanyRecord,
    *,
    company: str,
    city: str,
    min_employees: int,
    naf_prefixes: list[str],
) -> int:
    score = 0
    if record.effectif_min is not None and record.effectif_min >= min_employees:
        score += 40
    if naf_matches(record, naf_prefixes):
        score += 20
    age = company_age_years(record)
    if age is not None and age > 3:
        score += 10
    if not is_entreprise_individuelle(record) and not is_holding(record):
        score += 15
    match_score = score_name_city_match(record, company=company, city=city)
    if match_score >= 70:
        score += 15
    elif match_score >= 50:
        score += 8
    if record.siret_from_site:
        score += 10
    return min(score, 100)


def should_accept_unknown_effectif(score: int, min_score: int) -> bool:
    return score >= min_score
