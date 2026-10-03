"""TPE / PME / ETI / GE classifier."""

from __future__ import annotations

import re

from company_registry.config import TRANCHE_MAX, TRANCHE_MIN
from company_registry.models import CompanySize


def tranche_min(code: str) -> int | None:
    raw = (code or "").strip()
    if not raw:
        return None
    return TRANCHE_MIN.get(raw.upper()) or TRANCHE_MIN.get(raw)


def tranche_max(code: str) -> int | None:
    raw = (code or "").strip()
    if not raw:
        return None
    return TRANCHE_MAX.get(raw.upper()) or TRANCHE_MAX.get(raw)


def parse_ca_euros(raw: str) -> int | None:
    text = (raw or "").strip().lower().replace(" ", "")
    if not text:
        return None
    multiplier = 1
    if "md" in text or "milliard" in text:
        multiplier = 1_000_000_000
    elif "m" in text and "md" not in text:
        multiplier = 1_000_000
    elif "k" in text:
        multiplier = 1_000
    match = re.search(r"([\d.,]+)", text)
    if not match:
        return None
    num = match.group(1).replace(",", ".")
    try:
        return int(float(num) * multiplier)
    except ValueError:
        return None


def classify_company(
    *,
    effectif_min: int | None,
    chiffre_affaires: str = "",
) -> CompanySize:
    ca = parse_ca_euros(chiffre_affaires)
    employees = effectif_min

    if employees is not None:
        if employees >= 5000:
            return CompanySize.GE
        if employees >= 250:
            return CompanySize.ETI
        if employees >= 10:
            if ca is not None and ca >= 50_000_000:
                return CompanySize.ETI
            return CompanySize.PME
        if employees >= 1 or (ca is not None and ca >= 2_000_000):
            return CompanySize.TPE
        return CompanySize.TPE

    if ca is not None:
        if ca >= 50_000_000:
            return CompanySize.ETI
        if ca >= 2_000_000:
            return CompanySize.PME
        return CompanySize.TPE

    return CompanySize.UNKNOWN
