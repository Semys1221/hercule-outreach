"""Fuzzy matching for company name + city against API results."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from rapidfuzz import fuzz

from company_registry.models import CompanyRecord
from company_registry.siret_extract import digits


def normalize_name(name: str) -> str:
    text = (name or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _result_city(item: dict[str, Any]) -> str:
    siege = item.get("siege") if isinstance(item.get("siege"), dict) else {}
    return str(
        siege.get("libelle_commune")
        or item.get("libelle_commune")
        or siege.get("commune")
        or ""
    ).strip()


def _result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("nom_complet")
        or item.get("nom_raison_sociale")
        or item.get("denomination")
        or item.get("name")
        or ""
    ).strip()


def _domain_from_item(item: dict[str, Any]) -> str:
    siege = item.get("siege") if isinstance(item.get("siege"), dict) else {}
    for raw in (siege.get("site_internet"), item.get("site_internet"), item.get("website")):
        if not raw:
            continue
        host = urlparse(str(raw).strip()).netloc.lower().removeprefix("www.")
        if host:
            return host
    return ""


def score_api_result(
    item: dict[str, Any],
    *,
    company: str,
    city: str,
    website: str = "",
) -> float:
    name = _result_name(item)
    result_city = _result_city(item)
    name_score = fuzz.token_sort_ratio(normalize_name(company), normalize_name(name))
    city_score = 0.0
    city_l = city.strip().lower()
    if city_l and result_city:
        if city_l in result_city.lower() or result_city.lower() in city_l:
            city_score = 100.0
        else:
            city_score = float(fuzz.partial_ratio(city_l, result_city.lower()))
    domain_score = 0.0
    lead_domain = urlparse(f"https://{website}" if website and "://" not in website else website).netloc
    lead_domain = lead_domain.lower().removeprefix("www.")
    result_domain = _domain_from_item(item)
    if lead_domain and result_domain and lead_domain == result_domain:
        domain_score = 100.0
    return name_score * 0.55 + city_score * 0.30 + domain_score * 0.15


def pick_best_result(
    results: list[dict[str, Any]],
    *,
    company: str,
    city: str,
    website: str = "",
    min_score: float = 40.0,
) -> tuple[dict[str, Any] | None, float]:
    if not results:
        return None, 0.0
    scored = [
        (item, score_api_result(item, company=company, city=city, website=website))
        for item in results
        if isinstance(item, dict)
    ]
    if not scored:
        return None, 0.0
    scored.sort(key=lambda pair: pair[1], reverse=True)
    best_item, best_score = scored[0]
    if best_score < min_score and city.strip():
        return None, best_score
    return best_item, best_score


def score_name_city_match(
    record: CompanyRecord,
    *,
    company: str,
    city: str,
) -> float:
    name_score = fuzz.token_sort_ratio(
        normalize_name(company),
        normalize_name(record.denomination or company),
    )
    city_score = 0.0
    city_l = city.strip().lower()
    commune = (record.commune or "").strip().lower()
    if city_l and commune:
        if city_l in commune or commune in city_l:
            city_score = 100.0
        else:
            city_score = float(fuzz.partial_ratio(city_l, commune))
    return name_score * 0.7 + city_score * 0.3
