"""Post-push / pre-push link provisioning via Hercule Next.js API."""

from __future__ import annotations

import os
from typing import Any, Callable

import httpx
import requests

BATCH_SIZE = 100


def backend_url() -> str:
    configured = os.getenv("CRM_BACKEND_URL", "").strip().rstrip("/")
    if configured:
        return configured
    app_url = os.getenv("NEXT_PUBLIC_APP_URL", "").strip().rstrip("/")
    if app_url and app_url.startswith("https://") and "localhost" not in app_url:
        return app_url
    return "https://www.hercule.dev"


def cron_secret() -> str:
    # Prefer LINK_TRACKING_WEBHOOK_SECRET first — matches
    # app/api/link-tracking/provision-leads/route.ts verifyProvisionLeadsSecret.
    return (
        os.getenv("LINK_TRACKING_WEBHOOK_SECRET", "").strip()
        or os.getenv("CRON_SECRET", "").strip()
        or os.getenv("INSTANTLY_BYPASS_WEBHOOK_SECRET", "").strip()
    )


def _normalize_emails(emails: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in emails:
        email = str(raw or "").strip().lower()
        if "@" not in email or email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


def _empty_stats() -> dict[str, Any]:
    return {
        "created": 0,
        "updated": 0,
        "patched": 0,
        "skipped": 0,
        "failed": 0,
        "attached": 0,
        "removed_from_list": 0,
        "batches": 0,
        "custom_variables_by_email": {},
    }


def _normalize_niche(raw: str) -> str:
    niche = str(raw or "").strip().lower()
    if niche == "jum":
        return "comptable_delivery"
    return niche


def provision_leads_batches(
    emails: list[str],
    *,
    list_id: str,
    campaign_id: str,
    niche: str | None = None,
    segment: str | None = None,
    reservation_page: str | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Provision slug + tracking links in batches (sync).

    Returns aggregated stats plus custom_variables_by_email for campaign push merge.
    Skips gracefully when CRON_SECRET is missing.
    """
    secret = cron_secret()
    if not secret:
        if log_cb:
            log_cb(
                "Link provision skipped — CRON_SECRET / LINK_TRACKING_WEBHOOK_SECRET missing"
            )
        return {**_empty_stats(), "skipped_reason": "missing_secret"}

    normalized = _normalize_emails(emails)
    if not normalized:
        return _empty_stats()

    url = f"{backend_url()}/api/link-tracking/provision-leads"
    headers = {"Authorization": f"Bearer {secret}"}
    stats = _empty_stats()
    custom_variables_by_email: dict[str, dict[str, str]] = {}

    for start in range(0, len(normalized), BATCH_SIZE):
        batch = normalized[start : start + BATCH_SIZE]
        payload: dict[str, Any] = {
            "emails": batch,
            "listId": list_id.strip(),
            "campaignId": campaign_id.strip(),
        }
        if niche:
            payload["niche"] = _normalize_niche(niche)
        if segment:
            payload["segment"] = segment.strip()
        if reservation_page:
            payload["reservationPage"] = reservation_page.strip()

        if log_cb:
            log_cb(
                f"Provisioning tracking URLs for {len(batch)} lead(s) "
                f"(batch {stats['batches'] + 1})..."
            )

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
        except requests.RequestException as exc:
            stats["failed"] += len(batch)
            if log_cb:
                log_cb(f"Link provision error: {exc}")
            continue

        stats["batches"] += 1

        if response.status_code == 401:
            if log_cb:
                log_cb("Link provision failed — unauthorized (check CRON_SECRET)")
            return {**stats, "custom_variables_by_email": custom_variables_by_email}

        if response.status_code >= 400:
            stats["failed"] += len(batch)
            if log_cb:
                log_cb(
                    f"Link provision failed — HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
            continue

        data = response.json()
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            if log_cb:
                log_cb("Link provision OK (no result payload)")
            continue

        for key in ("created", "updated", "patched", "skipped", "failed"):
            stats[key] += int(result.get(key) or 0)
        attach = result.get("attach")
        if isinstance(attach, dict):
            stats["attached"] += int(attach.get("moved") or 0)
        stats["removed_from_list"] += int(result.get("removedFromList") or 0)

        batch_vars = result.get("customVariablesByEmail")
        if isinstance(batch_vars, dict):
            for email, variables in batch_vars.items():
                if isinstance(email, str) and isinstance(variables, dict):
                    custom_variables_by_email[email.strip().lower()] = {
                        str(k): str(v) for k, v in variables.items()
                    }

    stats["custom_variables_by_email"] = custom_variables_by_email

    if log_cb:
        log_cb(
            "Link provision complete — "
            f"created={stats['created']}, updated={stats['updated']}, "
            f"patched={stats['patched']}, skipped={stats['skipped']}, "
            f"failed={stats['failed']}, "
            f"attached_to_campaign={stats['attached']}, "
            f"removed_from_list={stats['removed_from_list']}, "
            f"urls_ready={len(custom_variables_by_email)}"
        )

    return stats


async def provision_leads_after_push(
    emails: list[str],
    *,
    config: dict[str, Any],
    log_cb: Callable[[str], None],
) -> None:
    """Provision slug + tracking links for leads just pushed to Instantly (scraper)."""
    secret = cron_secret()
    if not secret:
        log_cb("Link provision skipped — CRON_SECRET / LINK_TRACKING_WEBHOOK_SECRET missing")
        return

    normalized = _normalize_emails(emails)
    if not normalized:
        return

    category = str(config.get("LINK_PROVISION_CATEGORY") or "cif").strip() or "cif"
    segment = str(config.get("LINK_PROVISION_SEGMENT") or "").strip() or None
    reservation_page = (
        str(config.get("LINK_PROVISION_RESERVATION_PAGE") or "").strip() or None
    )
    list_id = str(config.get("INSTANTLY_LIST_ID") or "").strip()
    campaign_id = str(config.get("INSTANTLY_CAMPAIGN_ID") or "").strip()

    if list_id and campaign_id:
        provision_leads_batches(
            normalized,
            list_id=list_id,
            campaign_id=campaign_id,
            niche=category,
            segment=segment,
            reservation_page=reservation_page,
            log_cb=log_cb,
        )
        return

    payload: dict[str, Any] = {
        "emails": normalized[:BATCH_SIZE],
        "niche": _normalize_niche(category),
    }
    if segment:
        payload["segment"] = segment
    if reservation_page:
        payload["reservationPage"] = reservation_page
    if list_id:
        payload["listId"] = list_id
    if campaign_id:
        payload["campaignId"] = campaign_id

    url = f"{backend_url()}/api/link-tracking/provision-leads"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {secret}"},
            )
        if response.status_code == 401:
            log_cb("Link provision failed — unauthorized (check CRON_SECRET on VPS)")
            return
        if response.status_code >= 400:
            log_cb(
                f"Link provision failed — HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return

        data = response.json()
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict):
            log_cb(
                "Link provision OK — "
                f"created={result.get('created', 0)}, "
                f"updated={result.get('updated', 0)}, "
                f"patched={result.get('patched', 0)}, "
                f"skipped={result.get('skipped', 0)}, "
                f"failed={result.get('failed', 0)}"
            )
        else:
            log_cb("Link provision OK")
    except Exception as exc:
        log_cb(f"Link provision error (scrape continues): {exc}")
