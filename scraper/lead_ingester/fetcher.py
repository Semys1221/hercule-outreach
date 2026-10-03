"""Async website HTML fetcher — no signal logic."""

from __future__ import annotations

import asyncio
from urllib.parse import unquote

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}


def normalize_fetch_url(raw: str) -> str:
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


async def fetch_html(
    url: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    timeout: float = 8.0,
) -> tuple[str | None, str | None]:
    """
    Returns (html_content, error_code).
    error_code is None on success, else one of:
      "fetch_timeout" | "fetch_blocked" | "fetch_error:<status>" | "invalid_url"
    """
    normalized = normalize_fetch_url(url)
    if not normalized or not (
        normalized.startswith("http://") or normalized.startswith("https://")
    ):
        return None, "invalid_url"

    async with sem:
        try:
            response = await client.get(
                normalized,
                follow_redirects=True,
                timeout=timeout,
            )
            if response.status_code in (403, 429):
                return None, "fetch_blocked"
            if response.status_code >= 400:
                return None, f"fetch_error:{response.status_code}"
            return response.text, None
        except httpx.TimeoutException:
            return None, "fetch_timeout"
        except Exception:
            return None, "fetch_error:unknown"
