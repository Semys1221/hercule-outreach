"""Company gate — lookup orchestration and hard rules."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from company_registry.cache import RegistryCache
from company_registry.classifier import classify_company
from company_registry.config import CompanyGateConfig
from company_registry.models import (
    AcceptReason,
    CompanyRecord,
    GateVerdict,
    RejectReason,
    RegistrySource,
)
from company_registry.registry_client import RegistryClient
from company_registry.scorer import (
    compute_lead_score,
    is_holding,
    naf_matches,
    should_accept_unknown_effectif,
)
from company_registry.sirene_index import SireneIndex
from company_registry.siret_extract import (
    extract_siret_siren,
    fetch_mentions_legales,
    resolve_identifiers,
)

logger = logging.getLogger(__name__)

# Backward-compatible reject reason aliases
REJECT_EMPLOYEE_COUNT = RejectReason.EMPLOYEE_COUNT
REJECT_NAF = RejectReason.NAF
REJECT_PAPPERS_NOT_FOUND = RejectReason.NOT_FOUND
REJECT_UNKNOWN_EFFECTIF = RejectReason.UNKNOWN_EFFECTIF
REJECT_PAPPERS_UNAVAILABLE = RejectReason.UNAVAILABLE
REJECT_HOLDING = RejectReason.HOLDING


class CompanyGate:
    def __init__(self, config: CompanyGateConfig) -> None:
        self.config = config
        self._memory: RegistryCache = RegistryCache(config.cache_path)
        self._client = RegistryClient(timeout_s=config.timeout_s)
        sirene_path = config.resolve_sirene_path()
        self._sirene = SireneIndex(sirene_path) if config.sirene_index_enabled else SireneIndex("")
        if config.sirene_index_enabled and not self._sirene.available:
            logger.warning("SIRENE index not found at %s — HTTP fallback only", sirene_path)

    def flush_cache(self) -> None:
        self._memory.flush()

    def cache_key(self, company: str, city: str, siret: str = "", siren: str = "") -> str:
        return RegistryCache.cache_key(company, city, siret=siret, siren=siren)

    async def validate_lead(self, lead: dict[str, str], client: httpx.AsyncClient) -> GateVerdict:
        company = (lead.get("Company") or "").strip()
        city = (lead.get("City") or "").strip()
        website = (lead.get("Website") or "").strip()
        site_text = lead.get("_website_text") or lead.get("_html_text") or ""
        siret, siren, siret_from_site = resolve_identifiers(lead, site_text)

        key = self.cache_key(company, city, siret=siret, siren=siren)
        cached = self._memory.get(key)
        if cached is not None:
            return cached

        record, unavailable = await self._resolve_company(
            client,
            company=company,
            city=city,
            website=website,
            site_text=site_text,
            siret=siret,
            siren=siren,
            siret_from_site=siret_from_site,
            deep=self.config.deep_enrich,
        )
        if unavailable:
            verdict = self._reject(RejectReason.UNAVAILABLE, CompanyRecord())
        elif record is None:
            verdict = self._reject(RejectReason.NOT_FOUND, CompanyRecord())
        else:
            record.siret_from_site = siret_from_site or record.siret_from_site
            verdict = self._apply_rules(record, company=company, city=city)

        self._memory.remember(key, verdict, record if record else None)
        return verdict

    async def _resolve_company(
        self,
        client: httpx.AsyncClient,
        *,
        company: str,
        city: str,
        website: str,
        site_text: str,
        siret: str,
        siren: str,
        siret_from_site: bool,
        deep: bool,
    ) -> tuple[CompanyRecord | None, bool]:
        # 1. SIRENE index by identifier
        if self._sirene.available:
            if len(siret) == 14:
                hit = self._sirene.lookup_siret(siret)
                if hit:
                    hit.siret_from_site = siret_from_site
                    return hit, False
            if len(siren) == 9:
                hit = self._sirene.lookup_siren(siren)
                if hit:
                    hit.siret_from_site = siret_from_site
                    return hit, False

        # 2. API JSON
        query = siret or siren or " ".join(part for part in (company, city) if part).strip()
        if query:
            hit, unavailable = await self._client.search_api(
                client, query, company=company, city=city, website=website
            )
            if unavailable:
                return None, True
            if hit and (hit.effectif_min is not None or hit.siren or hit.siret):
                hit.siret_from_site = siret_from_site
                return hit, False

        # 3. Mentions légales → API (skipped in fast mode — too slow for scrape throughput)
        if not self.config.fast_mode and not siret and not siren:
            legal_html = await fetch_mentions_legales(client, website)
            extra_siret, extra_siren = extract_siret_siren(legal_html)
            siret = extra_siret
            siren = extra_siren or (extra_siret[:9] if len(extra_siret) == 14 else "")
            if siret or siren:
                if self._sirene.available:
                    hit = (
                        self._sirene.lookup_siret(siret)
                        if len(siret) == 14
                        else self._sirene.lookup_siren(siren)
                    )
                    if hit:
                        hit.siret_from_site = True
                        return hit, False
                hit, unavailable = await self._client.search_api(
                    client, siret or siren, company=company, city=city, website=website
                )
                if unavailable:
                    return None, True
                if hit:
                    hit.siret_from_site = True
                    return hit, False

        # 4. SIRENE by name+city (local index — fast when available)
        if self._sirene.available and company:
            hit = self._sirene.lookup_name_city(company, city)
            if hit:
                hit.siret_from_site = siret_from_site
                return hit, False

        # Fast mode: stop after index + single API pass (no Annuaire HTML crawl).
        if self.config.fast_mode:
            return None, False

        # 5. Annuaire HTML (deep enrich or last resort when identifiers known)
        if deep or siret or siren:
            hit, unavailable = await self._client.annuaire_lookup(
                client, company=company, city=city, siren=siren, siret=siret
            )
            if unavailable:
                return None, True
            if hit:
                hit.siret_from_site = siret_from_site
                return hit, False

        return None, False

    def _reject(self, reason: RejectReason, record: CompanyRecord) -> GateVerdict:
        if self.config.on_unknown == "accept" and reason in (
            RejectReason.UNKNOWN_EFFECTIF,
            RejectReason.NOT_FOUND,
            RejectReason.UNAVAILABLE,
        ):
            return GateVerdict(True, "", record)
        return GateVerdict(False, str(reason), record)

    def _apply_rules(self, record: CompanyRecord, *, company: str, city: str) -> GateVerdict:
        naf_prefixes = [str(p).strip().lower() for p in (self.config.naf_prefixes or []) if p]

        if self.config.reject_holdings and is_holding(record):
            return GateVerdict(False, str(RejectReason.HOLDING), record)

        if naf_prefixes and record.code_naf and not naf_matches(record, naf_prefixes):
            return GateVerdict(False, str(RejectReason.NAF), record)

        score = compute_lead_score(
            record,
            company=company,
            city=city,
            min_employees=self.config.min_employees,
            naf_prefixes=naf_prefixes,
        )
        taille = str(classify_company(
            effectif_min=record.effectif_min,
            chiffre_affaires=record.chiffre_affaires,
        ))

        if record.effectif_min is not None:
            if record.effectif_min < self.config.min_employees:
                return GateVerdict(
                    False, str(RejectReason.EMPLOYEE_COUNT), record, lead_score=score, taille_entreprise=taille
                )
            if (
                self.config.max_employees is not None
                and record.effectif_min > self.config.max_employees
            ):
                return GateVerdict(
                    False, str(RejectReason.EMPLOYEE_COUNT), record, lead_score=score, taille_entreprise=taille
                )
            return GateVerdict(True, "", record, lead_score=score, taille_entreprise=taille)

        # Unknown effectif — hybrid scoring
        if self.config.scoring_enabled and should_accept_unknown_effectif(score, self.config.min_score):
            return GateVerdict(
                True,
                str(AcceptReason.SCORE_UNKNOWN_EFFECTIF),
                record,
                lead_score=score,
                taille_entreprise=taille,
            )
        if self.config.on_unknown == "accept":
            return GateVerdict(True, "", record, lead_score=score, taille_entreprise=taille)
        return GateVerdict(
            False, str(RejectReason.UNKNOWN_EFFECTIF), record, lead_score=score, taille_entreprise=taille
        )


# Backward-compatible alias
PappersSirenValidator = CompanyGate


def build_validator(config: dict[str, Any], *, cache_path: str = "") -> CompanyGate:
    gate_config = CompanyGateConfig.from_dict(config, cache_path=cache_path)
    return CompanyGate(gate_config)
