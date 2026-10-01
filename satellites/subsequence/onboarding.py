"""Campaign onboarding: status, webhook match, initialize."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from config import is_valid_webhook_target_url, webhook_url_error
from supabase_repo import (
    get_config,
    list_templates,
    save_config,
    seed_empty_templates,
)

INTERESTED_TEMPLATE_KEYS = (
    "interested_email1",
    "interested_email2",
    "interested_email3",
)

OnboardingStatus = Literal[
    "not_initialized",
    "copy_incomplete",
    "webhook_incomplete",
    "ready",
]


def normalize_webhook_url(url: str) -> str:
    return url.strip().rstrip("/")


def is_webhook_active(hook: dict[str, Any] | None) -> bool:
    if not hook:
        return False
    status = hook.get("status")
    return status is None or status == 1


def find_campaign_webhook(
    webhooks: list[dict[str, Any]],
    *,
    campaign_id: str,
    target_url: str,
    require_active: bool = True,
) -> dict[str, Any] | None:
    target = normalize_webhook_url(target_url)
    for hook in webhooks:
        if str(hook.get("event_type") or "") != "lead_interested":
            continue
        url = normalize_webhook_url(str(hook.get("target_hook_url") or ""))
        if url != target:
            continue
        campaign = hook.get("campaign") or hook.get("campaign_id")
        if not campaign or str(campaign) == campaign_id:
            if require_active and not is_webhook_active(hook):
                continue
            return hook
    return None


def explain_webhook_miss(
    webhooks: list[dict[str, Any]],
    *,
    campaign_id: str,
    target_url: str,
) -> str | None:
    if find_campaign_webhook(
        webhooks, campaign_id=campaign_id, target_url=target_url
    ):
        return None

    target = normalize_webhook_url(target_url)
    interested = [
        hook
        for hook in webhooks
        if str(hook.get("event_type") or "") == "lead_interested"
    ]
    if not interested:
        return "Aucun webhook Instantly de type `lead_interested` enregistré."

    same_url = [
        hook
        for hook in interested
        if normalize_webhook_url(str(hook.get("target_hook_url") or "")) == target
    ]
    if not same_url:
        other_urls = sorted(
            {
                normalize_webhook_url(str(hook.get("target_hook_url") or ""))
                for hook in interested
                if hook.get("target_hook_url")
            }
        )
        urls = ", ".join(other_urls) if other_urls else "(aucune URL)"
        return (
            f"Aucun webhook `lead_interested` sur `{target}`. "
            f"Webhooks existants : {urls}."
        )

    for hook in same_url:
        hook_campaign = hook.get("campaign") or hook.get("campaign_id")
        if hook_campaign and str(hook_campaign) == campaign_id:
            status = hook.get("status")
            if status is not None and status != 1:
                hook_id = hook.get("id") or "?"
                error_at = str(hook.get("timestamp_error") or "").strip()
                since = f" depuis {error_at}" if error_at else ""
                return (
                    f"Webhook trouvé (`{hook_id}`) mais status={status} "
                    f"(inactif{since}). Instantly l'a coupé après des échecs de livraison."
                )

    scoped_campaigns = sorted(
        {
            str(hook.get("campaign") or hook.get("campaign_id") or "global")
            for hook in same_url
        }
    )
    return (
        f"Webhook `lead_interested` sur la bonne URL mais scopé à d'autres campagnes : "
        f"{', '.join(scoped_campaigns)}."
    )


def copy_is_complete(templates: list[dict[str, Any]]) -> bool:
    by_key = {str(row.get("template_key") or ""): row for row in templates}
    for key in INTERESTED_TEMPLATE_KEYS:
        body = str((by_key.get(key) or {}).get("body_html") or "")
        if not body.strip():
            return False
    return True


def e1_copy_is_ready(templates: list[dict[str, Any]]) -> bool:
    for row in templates:
        if row.get("template_key") == "interested_email1":
            return bool(str(row.get("body_html") or "").strip())
    return False


def derive_onboarding_status(
    *,
    has_config: bool,
    has_webhook: bool,
    copy_complete: bool,
) -> OnboardingStatus:
    if not has_config:
        return "not_initialized"
    if not copy_complete:
        return "copy_incomplete"
    if not has_webhook:
        return "webhook_incomplete"
    return "ready"


def initialize_campaign(
    instantly_client: Any,
    *,
    campaign_id: str,
    campaign_name: str,
    target_url: str,
    secret: str,
) -> dict[str, Any]:
    if not is_valid_webhook_target_url(target_url):
        raise ValueError(
            webhook_url_error()
            or "URL webhook invalide — utilisez la prod `https://www.hercule.dev`."
        )

    existing = get_config(campaign_id)
    now = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "webhook_auto_send_enabled": True,
        "pipeline_auto_advance_enabled": True,
        "e1_webhook_delay_ms": 5 * 60 * 1000,
        "initialized_at": (existing or {}).get("initialized_at") or now,
    }
    save_config(row)
    seed_empty_templates(campaign_id)

    webhooks = instantly_client.list_webhooks()
    match = find_campaign_webhook(
        webhooks,
        campaign_id=campaign_id,
        target_url=target_url,
        require_active=False,
    )
    auth_headers = {"Authorization": f"Bearer {secret}"} if secret else None
    if match:
        webhook_id = str(match.get("id") or "")
        if webhook_id and auth_headers:
            instantly_client.patch_webhook(webhook_id, headers=auth_headers)
        if webhook_id and not is_webhook_active(match):
            instantly_client.resume_webhook(webhook_id)
    else:
        if not secret:
            raise ValueError(
                "Set INSTANTLY_BYPASS_WEBHOOK_SECRET (or CRON_SECRET) before initializing."
            )
        created = instantly_client.create_webhook(
            target_hook_url=target_url,
            event_type="lead_interested",
            name=f"Hercule Interested Bypass — {campaign_name}"[:80],
            campaign=campaign_id,
            headers=auth_headers,
        )
        webhook_id = str(created.get("id") or "")
    if webhook_id:
        save_config({"campaign_id": campaign_id, "webhook_id": webhook_id})
    config = get_config(campaign_id)
    if not config:
        raise RuntimeError("Failed to persist campaign config")
    return config
