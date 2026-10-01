"""HTTP + BeautifulSoup website keyword verification for the Streamlit Scraper pipeline."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable
from urllib.parse import unquote

import httpx
import pandas as pd
from bs4 import BeautifulSoup

_BROADER_INCLUDED = [
    "marketing digital",
    "webmarketing",
    "publicité en ligne",
    "publicité digitale",
    "stratégie digitale",
    "performance digitale",
    "agence digitale",
    "référencement",
    "référencement naturel",
    "campagnes publicitaires",
    "social media",
    "community management",
    "content marketing",
    "digital marketing",
    "meta ads",
    "linkedin ads",
    "tiktok ads",
    "sem",
    "smo",
    "display",
]

_PERFORMANCE_INCLUDED = [
    "growth hacking",
    "growth marketing",
    "génération de leads",
    "lead gen",
    "lead generation",
    "acquisition client",
    "a/b testing",
    "cro",
    "conversion rate optimization",
    "optimisation de la conversion",
    "outbound",
    "inbound marketing",
    "marketing automation",
    "scraping",
    "cold email",
    "cold calling",
    "paid traffic",
    "trafic payant",
    "organic traffic",
    "trafic organique",
    "seo",
    "sea",
    "google ads",
    "social ads",
    "facebook ads",
]

DEFAULT_HARD_EXCLUDED = [
    "imprimerie",
    "print",
    "flyer",
    "flyers",
    "brochure",
    "carte de visite",
    "bâche",
    "packaging",
    "goodies",
    "objets publicitaires",
]

DEFAULT_SOFT_EXCLUDED = [
    "design graphique",
    "graphisme",
    "création de logo",
    "identité visuelle",
    "branding",
    "relations publiques",
    "relation presse",
]

DEFAULT_KEYWORDS = {
    "included_keywords": _PERFORMANCE_INCLUDED + _BROADER_INCLUDED,
    "hard_excluded_keywords": DEFAULT_HARD_EXCLUDED,
    "soft_excluded_keywords": DEFAULT_SOFT_EXCLUDED,
    "excluded_keywords": DEFAULT_HARD_EXCLUDED + DEFAULT_SOFT_EXCLUDED,
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PAGE_GOTO_TIMEOUT_MS = 15000
MIN_THROUGHPUT_LEADS_PER_SEC = 0.25


def _normalize_fetch_url(raw: str) -> str:
    url = unquote(str(raw).strip())
    if not url or url.lower() == "nan":
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    lower = url.lower()
    if "/%3f" in lower:
        url = url[: lower.index("/%3f")]
    elif "/?" in url:
        url = url.split("/?", 1)[0]
    if "?" in url.split("//", 1)[-1]:
        url = url.split("?", 1)[0]
    return url.rstrip("/")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True).lower()


def _find_keywords(text_content: str, keywords: list[str]) -> list[str]:
    return [
        kw
        for kw in keywords
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_content)
    ]


def _check_keywords(
    text_content: str,
    included: list[str],
    hard_excluded: list[str],
    soft_excluded: list[str],
) -> tuple[str, str, str, str]:
    found_included = _find_keywords(text_content, included)
    found_hard = _find_keywords(text_content, hard_excluded)
    found_soft = _find_keywords(text_content, soft_excluded)

    if not found_included:
        status = "Non Valide"
    elif found_hard:
        status = "Non Valide"
    else:
        status = "Valide"

    return (
        status,
        ", ".join(found_included),
        ", ".join(found_hard),
        ", ".join(found_soft),
    )


def _enrich_reject_reason(
    *,
    status: str,
    included_found: str,
    hard_found: str,
    soft_found: str,
    error_detail: str = "",
) -> str:
    if included_found == "Erreur/Timeout":
        return f"http_error: {error_detail or 'request failed'}"
    if not included_found:
        return "no_included"
    if hard_found:
        return f"hard_excluded: {hard_found}"
    if soft_found and status == "Non Valide":
        return f"soft_excluded: {soft_found}"
    return status


def _apply_service_from_html(
    record: dict[str, str],
    html_text: str,
    service_config: dict[str, Any] | None,
) -> None:
    if not service_config or not service_config.get("SERVICE_RULES"):
        return
    from category_filter import detect_service_match

    combined = f"{html_text} {record.get('Mots_Inclus_Trouvés', '')}".strip().lower()
    if not combined:
        return
    match = detect_service_match(combined, service_config)
    if match:
        record["Service"] = match


async def fetch_and_check(
    url: str,
    included: list[str],
    hard_excluded: list[str],
    soft_excluded: list[str],
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    goto_timeout_ms: int = PAGE_GOTO_TIMEOUT_MS,
) -> tuple[str, str, str, str, str]:
    url = _normalize_fetch_url(url)
    if not url:
        return "Non Valide", "URL invalide", "", "", ""

    async with semaphore:
        try:
            timeout = httpx.Timeout(goto_timeout_ms / 1000.0)
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()
            text_content = _html_to_text(resp.text)
            status, inc, hard, soft = _check_keywords(
                text_content, included, hard_excluded, soft_excluded
            )
            return status, inc, hard, soft, text_content
        except Exception as e:
            return "Non Valide", "Erreur/Timeout", "", str(e).split("\n")[0], ""


async def _fetch_and_qualify(
    row: dict[str, str],
    url: str,
    included: list[str],
    hard_excluded: list[str],
    soft_excluded: list[str],
    client: httpx.AsyncClient,
    website_sema: asyncio.Semaphore,
    goto_timeout_ms: int,
    siret_validator: Any | None,
    siret_sema: asyncio.Semaphore | None,
) -> dict[str, str]:
    status, inc, hard, soft, html_text = await fetch_and_check(
        url, included, hard_excluded, soft_excluded, client, website_sema, goto_timeout_ms
    )
    record = {
        **row,
        "Statut_Lead": status,
        "Mots_Inclus_Trouvés": inc,
        "Hard_Exclus_Trouvés": hard,
        "Soft_Exclus_Trouvés": soft,
        "Mots_Exclus_Trouvés": ", ".join(filter(None, [hard, soft])),
        "_website_text": html_text,
    }
    if status != "Valide" or siret_validator is None:
        return record
    assert siret_sema is not None
    async with siret_sema:
        verdict = await siret_validator.validate_lead(record, client)
    record.update(verdict.as_lead_fields())
    if not verdict.accepted:
        record["Statut_Lead"] = "Non Valide"
        record["Enrich_Reason"] = verdict.reason
    return record


async def run_website_scraping(
    df: pd.DataFrame,
    url_column: str,
    included: list[str],
    hard_excluded: list[str],
    soft_excluded: list[str],
    max_concurrent: int,
    goto_timeout_ms: int = PAGE_GOTO_TIMEOUT_MS,
) -> pd.DataFrame:
    urls = df[url_column].tolist()
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        tasks = [
            fetch_and_check(
                url, included, hard_excluded, soft_excluded, client, semaphore, goto_timeout_ms
            )
            for url in urls
        ]
        results = await asyncio.gather(*tasks)

    statuses, inc_founds, hard_founds, soft_founds, html_texts = zip(*results)
    out = df.copy()
    out["Statut_Lead"] = statuses
    out["Mots_Inclus_Trouvés"] = inc_founds
    out["Hard_Exclus_Trouvés"] = hard_founds
    out["Soft_Exclus_Trouvés"] = soft_founds
    out["Mots_Exclus_Trouvés"] = [
        ", ".join(filter(None, [h, s])) for h, s in zip(hard_founds, soft_founds)
    ]
    out["_html_text"] = html_texts
    return out


def _resolve_exclusion_lists(
    *,
    hard_excluded: list[str] | None,
    soft_excluded: list[str] | None,
    excluded: list[str] | None,
) -> tuple[list[str], list[str]]:
    hard = list(hard_excluded or DEFAULT_KEYWORDS["hard_excluded_keywords"])
    soft = (
        list(soft_excluded)
        if soft_excluded is not None
        else list(DEFAULT_KEYWORDS["soft_excluded_keywords"])
    )
    if excluded and hard_excluded is None and soft_excluded is None:
        hard = list(excluded)
        soft = []
    return hard, soft


async def enrich_leads(
    rows: list[dict[str, str]],
    *,
    url_column: str = "Website",
    included: list[str] | None = None,
    hard_excluded: list[str] | None = None,
    soft_excluded: list[str] | None = None,
    excluded: list[str] | None = None,
    max_concurrent: int = 10,
    goto_timeout_ms: int = PAGE_GOTO_TIMEOUT_MS,
    service_config: dict[str, Any] | None = None,
    siret_config: dict[str, Any] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Verify lead websites; return (valid_rows, rejected_rows) with enrich audit fields."""
    if not rows:
        return [], []

    included = included or DEFAULT_KEYWORDS["included_keywords"]
    hard, soft = _resolve_exclusion_lists(
        hard_excluded=hard_excluded,
        soft_excluded=soft_excluded,
        excluded=excluded,
    )

    if log_cb:
        log_cb(f"Website enrich — checking {len(rows)} site(s) @ concurrency {max_concurrent}")

    if url_column not in rows[0]:
        rejected = [
            {
                **row,
                "Statut_Lead": "Non Valide",
                "Mots_Inclus_Trouvés": "",
                "Hard_Exclus_Trouvés": "",
                "Soft_Exclus_Trouvés": "",
                "Mots_Exclus_Trouvés": "",
                "Enrich_Reason": f"missing column {url_column}",
            }
            for row in rows
        ]
        return [], rejected

    siret_validator = None
    siret_sema = None
    siret_timeout = 5.0
    if siret_config and bool(siret_config.get("PAPPERS_ENABLED", False)):
        from company_registry import build_validator, pappers_settings
        from company_registry.validate import _cache_path_for_config

        settings = pappers_settings(siret_config)
        cache_path = _cache_path_for_config(siret_config)
        siret_validator = build_validator(siret_config, cache_path=cache_path)
        siret_sema = asyncio.Semaphore(settings["concurrency"])
        siret_timeout = settings["timeout_s"]
        if log_cb:
            log_cb(
                f"SIRET enrich overlapped — min effectif {settings['min_employees']}, "
                f"concurrency {settings['concurrency']}"
            )

    website_sema = asyncio.Semaphore(max_concurrent)
    timeout = httpx.Timeout(max(goto_timeout_ms / 1000.0, siret_timeout))
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        qualified = await asyncio.gather(
            *[
                _fetch_and_qualify(
                    row,
                    str(row.get(url_column) or ""),
                    included,
                    hard,
                    soft,
                    client,
                    website_sema,
                    goto_timeout_ms,
                    siret_validator,
                    siret_sema,
                )
                for row in rows
            ]
        )

    valid: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    siret_rejected = 0
    for record in qualified:
        html_text = record.pop("_website_text", "")
        status = record.get("Statut_Lead", "Non Valide")
        if status == "Valide":
            _apply_service_from_html(record, html_text, service_config)
            valid.append(record)
            continue
        if str(record.get("Enrich_Reason") or "").startswith("REJECT_"):
            siret_rejected += 1
            rejected.append(record)
            continue
        error_detail = record.get("Soft_Exclus_Trouvés", "")
        if record.get("Mots_Inclus_Trouvés") == "Erreur/Timeout":
            error_detail = error_detail or record.get("Mots_Exclus_Trouvés", "")
        record["Enrich_Reason"] = _enrich_reject_reason(
            status=status,
            included_found=record.get("Mots_Inclus_Trouvés", ""),
            hard_found=record.get("Hard_Exclus_Trouvés", ""),
            soft_found=record.get("Soft_Exclus_Trouvés", ""),
            error_detail=error_detail,
        )
        rejected.append(record)

    if siret_validator is not None:
        siret_validator.flush_cache()

    if log_cb and siret_rejected:
        log_cb(f"Enrich: {siret_rejected} lead(s) rejected by SIRET/registry gate.")

    return valid, rejected
