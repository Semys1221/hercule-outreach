"""Company registry — SIRET/effectif gate for lead enrichment."""

from company_registry.cache import RegistryCache
from company_registry.classifier import classify_company, tranche_min
from company_registry.config import CompanyGateConfig, pappers_settings
from company_registry.gate import (
    CompanyGate,
    PappersSirenValidator,
    REJECT_EMPLOYEE_COUNT,
    REJECT_HOLDING,
    REJECT_NAF,
    REJECT_PAPPERS_NOT_FOUND,
    REJECT_PAPPERS_UNAVAILABLE,
    REJECT_UNKNOWN_EFFECTIF,
    build_validator,
)
from company_registry.models import (
    CompanyRecord,
    CompanySize,
    GateVerdict,
    LegacyCompany,
    LegacyVerdict,
)
from company_registry.siret_extract import extract_from_outscraper, extract_siret_siren
from company_registry.sirene_build import build_index, check_index
from company_registry.validate import validate_leads

# Backward-compatible type aliases
PappersCompany = LegacyCompany
PappersVerdict = LegacyVerdict

__all__ = [
    "CompanyGate",
    "CompanyGateConfig",
    "CompanyRecord",
    "CompanySize",
    "GateVerdict",
    "LegacyCompany",
    "LegacyVerdict",
    "PappersCompany",
    "PappersSirenValidator",
    "PappersVerdict",
    "RegistryCache",
    "REJECT_EMPLOYEE_COUNT",
    "REJECT_HOLDING",
    "REJECT_NAF",
    "REJECT_PAPPERS_NOT_FOUND",
    "REJECT_PAPPERS_UNAVAILABLE",
    "REJECT_UNKNOWN_EFFECTIF",
    "build_index",
    "build_validator",
    "check_index",
    "classify_company",
    "extract_from_outscraper",
    "extract_siret_siren",
    "pappers_settings",
    "tranche_min",
    "validate_leads",
]
