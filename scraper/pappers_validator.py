"""Backward-compatible shim — use company_registry package."""

from company_registry import (
    PappersCompany,
    PappersSirenValidator,
    PappersVerdict,
    REJECT_EMPLOYEE_COUNT,
    REJECT_NAF,
    REJECT_PAPPERS_NOT_FOUND,
    REJECT_PAPPERS_UNAVAILABLE,
    REJECT_UNKNOWN_EFFECTIF,
    build_validator,
    extract_siret_siren,
    pappers_settings,
    validate_leads,
)

# Legacy alias for holding reject
REJECT_HOLDING = "REJECT_HOLDING"

__all__ = [
    "PappersCompany",
    "PappersSirenValidator",
    "PappersVerdict",
    "REJECT_EMPLOYEE_COUNT",
    "REJECT_HOLDING",
    "REJECT_NAF",
    "REJECT_PAPPERS_NOT_FOUND",
    "REJECT_PAPPERS_UNAVAILABLE",
    "REJECT_UNKNOWN_EFFECTIF",
    "build_validator",
    "extract_siret_siren",
    "pappers_settings",
    "validate_leads",
]
