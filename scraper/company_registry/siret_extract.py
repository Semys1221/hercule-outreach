"""SIRET/SIREN extraction from text and legal pages."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx

from company_registry.config import USER_AGENT

_SIREN_RE = re.compile(r"\b(\d{9})\b")
_SIRET_RE = re.compile(r"\b(\d{14})\b")
_SIRET_LABELED_RE = re.compile(
    r"siret\s*[:\s-]*([0-9][0-9\s]{12,20}[0-9])",
    re.I,
)
_SIREN_LABELED_RE = re.compile(
    r"siren\s*[:\s-]*([0-9][0-9\s]{7,12}[0-9])",
    re.I,
)
_LEGAL_PATHS = ("/mentions-legales", "/mentions-legales/", "/legal", "/mentions_legales")


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def extract_siret_siren(text: str) -> tuple[str, str]:
    raw = text or ""
    labeled_siret = _SIRET_LABELED_RE.search(raw)
    if labeled_siret:
        siret = digits(labeled_siret.group(1))
        if len(siret) == 14:
            return siret, siret[:9]
    labeled_siren = _SIREN_LABELED_RE.search(raw)
    siren = digits(labeled_siren.group(1)) if labeled_siren else ""
    if len(siren) == 9:
        return "", siren
    siret_match = _SIRET_RE.search(raw)
    if siret_match:
        return siret_match.group(1), siret_match.group(1)[:9]
    siren_match = _SIREN_RE.search(raw)
    if siren_match:
        return "", siren_match.group(1)
    return "", ""


def extract_from_outscraper(business: dict) -> tuple[str, str]:
    """Map SIRET/SIREN from Outscraper raw fields when present."""
    candidates: list[str] = []
    for key in ("siret", "siren", "company_number", "registration_number"):
        val = digits(str(business.get(key) or ""))
        if val:
            candidates.append(val)
    insights = business.get("company_insights")
    if isinstance(insights, dict):
        for key in ("siret", "siren", "registration_number"):
            val = digits(str(insights.get(key) or ""))
            if val:
                candidates.append(val)
    siret = ""
    siren = ""
    for val in candidates:
        if len(val) == 14:
            siret = val
            siren = val[:9]
            break
        if len(val) == 9:
            siren = val
    return siret, siren


def normalize_site(raw: str) -> str:
    url = (raw or "").strip()
    if not url or url.lower() == "nan":
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_identifiers(lead: dict[str, str], site_text: str = "") -> tuple[str, str, bool]:
    """Return (siret, siren, siret_from_site)."""
    siret = digits(lead.get("Siret") or lead.get("siret") or "")
    siren = digits(lead.get("Siren") or lead.get("siren") or "")
    siret_from_site = False
    text = site_text or lead.get("_website_text") or lead.get("_html_text") or ""
    if len(siret) != 14:
        extracted_siret, extracted_siren = extract_siret_siren(text)
        if len(extracted_siret) == 14 or len(extracted_siren) == 9:
            siret_from_site = True
        siret = siret if len(siret) == 14 else extracted_siret
        siren = siren if len(siren) == 9 else extracted_siren
    if len(siret) == 14:
        siren = siren or siret[:9]
    elif len(siret) == 9:
        siren = siren or siret
        siret = ""
    return siret, siren, siret_from_site


async def fetch_mentions_legales(client: httpx.AsyncClient, website: str) -> str:
    base = normalize_site(website)
    if not base:
        return ""

    async def _fetch(path: str) -> str:
        url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return ""
        if response.status_code >= 400:
            return ""
        return response.text or ""

    results = await asyncio.gather(*[_fetch(path) for path in _LEGAL_PATHS])
    for html in results:
        if html:
            text_siret, text_siren = extract_siret_siren(html)
            if text_siret or text_siren:
                return html
    return ""
