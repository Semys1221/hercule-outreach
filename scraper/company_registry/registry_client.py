"""HTTP client for recherche-entreprises API and Annuaire fallback."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from company_registry.classifier import tranche_min
from company_registry.config import USER_AGENT
from company_registry.matcher import pick_best_result
from company_registry.models import CompanyRecord, RegistrySource
from company_registry.siret_extract import digits, extract_siret_siren

SEARCH_API = "https://recherche-entreprises.api.gouv.fr/search"
ANNUAIRE_SEARCH = "https://annuaire-entreprises.data.gouv.fr/rechercher"
ANNUAIRE_ENTREPRISE = "https://annuaire-entreprises.data.gouv.fr/entreprise"

_EFFECTIF_RANGE_RE = re.compile(r"(\d+)\s*(?:à|au|and|-|–)\s*(\d+)", re.I)
_EFFECTIF_MIN_RE = re.compile(r"(\d+)\s*\+", re.I)
_EFFECTIF_EXACT_RE = re.compile(r"(\d+)\s+salari", re.I)


def _parse_effectif_label(label: str) -> int | None:
    text = (label or "").strip().lower()
    if not text:
        return None
    if "non employ" in text or text in {"nn", "sans salarié", "0 salarié", "0 salaries"}:
        return 0
    range_match = _EFFECTIF_RANGE_RE.search(text)
    if range_match:
        return int(range_match.group(1))
    plus_match = _EFFECTIF_MIN_RE.search(text)
    if plus_match:
        return int(plus_match.group(1))
    exact = _EFFECTIF_EXACT_RE.search(text)
    if exact:
        return int(exact.group(1))
    return None


def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def parse_search_result(item: dict[str, Any], *, match_score: float = 0.0) -> CompanyRecord:
    siege = item.get("siege") if isinstance(item.get("siege"), dict) else {}
    tranche = str(
        item.get("tranche_effectif_salarie")
        or siege.get("tranche_effectif_salarie")
        or item.get("tranche_effectif")
        or ""
    ).strip()
    date_creation = str(item.get("date_creation") or "")
    siret = digits(str(siege.get("siret") or item.get("siret") or ""))
    siren = digits(str(item.get("siren") or ""))
    if not siren and len(siret) == 14:
        siren = siret[:9]
    nature = str(item.get("nature_juridique") or item.get("forme_juridique") or "").strip()
    return CompanyRecord(
        siren=siren,
        siret=siret,
        tranche_effectif=tranche,
        effectif_min=tranche_min(tranche),
        effectif_label=tranche,
        chiffre_affaires=str(item.get("chiffre_affaires") or ""),
        annee_creation=date_creation[:4] if len(date_creation) >= 4 else "",
        code_naf=str(item.get("activite_principale") or siege.get("activite_principale") or "").strip(),
        forme_juridique=nature,
        forme_juridique_code=digits(nature) or nature,
        denomination=str(
            item.get("nom_complet")
            or item.get("nom_raison_sociale")
            or item.get("denomination")
            or ""
        ).strip(),
        commune=str(siege.get("libelle_commune") or item.get("libelle_commune") or "").strip(),
        source=RegistrySource.API,
        match_score=match_score,
    )


def parse_annuaire_search(html: str) -> tuple[str, str]:
    if not html:
        return "", ""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        entreprise = re.search(r"/entreprise/(\d{9})", href)
        if entreprise:
            return entreprise.group(1), ""
        etablissement = re.search(r"/etablissement/(\d{14})", href)
        if etablissement:
            siret = etablissement.group(1)
            return siret[:9], siret
    found_siret, found_siren = extract_siret_siren(_html_to_text(html))
    return found_siren or (found_siret[:9] if len(found_siret) == 14 else ""), found_siret


def parse_annuaire_fiche(html: str, *, siren: str = "", siret: str = "") -> CompanyRecord | None:
    if not html:
        return None
    text = _html_to_text(html)
    found_siret, found_siren = extract_siret_siren(text)
    siren = siren or found_siren
    siret = siret if len(siret) == 14 else found_siret
    if not siren and not siret:
        return None

    effectif_label = ""
    effectif_match = re.search(
        r"(?:tranche d['’]effectif|effectif)[^0-9a-z]{0,40}([0-9].{0,40}salari\w*)",
        text,
        re.I,
    )
    if effectif_match:
        effectif_label = effectif_match.group(1)
    naf_match = re.search(r"(?:naf|ape)\s*[:\s]*([0-9]{2}\.[0-9]{2}[a-z]?)", text, re.I)
    forme_match = re.search(
        r"(?:forme juridique|nature juridique)\s*[:\s]*([A-Za-zÉÈÀÙÂÊÎÔÛéèàùâêîôû0-9 \-]{2,40})",
        text,
        re.I,
    )
    year_match = re.search(r"(?:date de création|créée? le)\s*[:\s]*(\d{2}/\d{2}/(\d{4})|\d{4})", text, re.I)
    year = ""
    if year_match:
        year = year_match.group(2) or year_match.group(1)[:4]

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for node in soup.find_all(string=re.compile(r"effectif", re.I)):
        parent = node.parent
        chunk = parent.get_text(" ", strip=True) if parent else str(node)
        if _parse_effectif_label(chunk) is not None or tranche_min(chunk):
            effectif_label = effectif_label or chunk
            break

    effectif_min_val = _parse_effectif_label(effectif_label) or tranche_min(effectif_label)
    return CompanyRecord(
        siren=siren or (siret[:9] if len(siret) == 14 else ""),
        siret=siret,
        tranche_effectif="",
        effectif_min=effectif_min_val,
        effectif_label=effectif_label,
        annee_creation=year,
        code_naf=naf_match.group(1) if naf_match else "",
        forme_juridique=(forme_match.group(1).strip() if forme_match else ""),
        forme_juridique_code=digits(forme_match.group(1) if forme_match else "") or "",
        source=RegistrySource.ANNUAIRE,
    )


class RegistryClient:
    def __init__(self, timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s

    async def get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
    ) -> tuple[dict[str, Any] | None, bool]:
        """Return (payload, unavailable). unavailable=True on network/5xx errors."""
        for attempt in range(3):
            try:
                response = await client.get(url, params=params)
            except httpx.HTTPError:
                if attempt == 2:
                    return None, True
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code == 429:
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code == 404:
                return None, False
            if response.status_code >= 500:
                if attempt == 2:
                    return None, True
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code >= 400:
                return None, False
            try:
                payload = response.json()
            except ValueError:
                return None, False
            return (payload if isinstance(payload, dict) else None), False
        return None, True

    async def get_html(self, client: httpx.AsyncClient, url: str) -> tuple[str, bool]:
        for attempt in range(3):
            try:
                response = await client.get(url)
            except httpx.HTTPError:
                if attempt == 2:
                    return "", True
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code == 429:
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code >= 500:
                if attempt == 2:
                    return "", True
                await asyncio.sleep(0.5 * (2 ** attempt))
                continue
            if response.status_code >= 400:
                return "", False
            return response.text or "", False
        return "", True

    async def search_api(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        company: str,
        city: str,
        website: str = "",
    ) -> tuple[CompanyRecord | None, bool]:
        params = {"q": query, "per_page": "5"}
        data, unavailable = await self.get_json(client, SEARCH_API, params)
        if unavailable:
            return None, True
        if not data and city and query != city:
            data, unavailable = await self.get_json(
                client, SEARCH_API, {"q": f"{query} {city}", "per_page": "5"}
            )
            if unavailable:
                return None, True
        if not data:
            return None, False
        results = data.get("results") or []
        if not isinstance(results, list) or not results:
            return None, False
        chosen, match_score = pick_best_result(
            [item for item in results if isinstance(item, dict)],
            company=company or query,
            city=city,
            website=website,
        )
        if not chosen:
            return None, False
        return parse_search_result(chosen, match_score=match_score), False

    async def annuaire_lookup(
        self,
        client: httpx.AsyncClient,
        *,
        company: str,
        city: str,
        siren: str,
        siret: str,
    ) -> tuple[CompanyRecord | None, bool]:
        if len(siren) == 9:
            html, unavailable = await self.get_html(client, f"{ANNUAIRE_ENTREPRISE}/{siren}")
            if unavailable:
                return None, True
            parsed = parse_annuaire_fiche(html or "", siren=siren)
            if parsed:
                return parsed, False
        terme = " ".join(part for part in (siret or company, city) if part).strip()
        if not terme:
            return None, False
        search_html, unavailable = await self.get_html(
            client, f"{ANNUAIRE_SEARCH}?terme={quote(terme)}"
        )
        if unavailable:
            return None, True
        found_siren, found_siret = parse_annuaire_search(search_html or "")
        use_siren = found_siren or (found_siret[:9] if len(found_siret) == 14 else "")
        if len(use_siren) != 9:
            return None, False
        html, unavailable = await self.get_html(client, f"{ANNUAIRE_ENTREPRISE}/{use_siren}")
        if unavailable:
            return None, True
        return parse_annuaire_fiche(html or "", siren=use_siren, siret=found_siret), False
