"""Campaign onboarding: webhooks + prod activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from config import is_valid_webhook_target_url, webhook_url_error
from presets import preset_label, resolve_preset_for_campaign

# Instantly API v2 registration values (not always equal to payload event_type).
REPLY_WEBHOOK_EVENT = "reply_received"
OOO_WEBHOOK_EVENT = "lead_out_of_office"

OnboardingStatus = Literal[
    "not_initialized",
    "webhook_incomplete",
    "niche_mismatch",
    "waiting_for_replies",
    "paused",
]


@dataclass(frozen=True)
class CampaignReadiness:
    ready: bool
    reason: str | None = None


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
    event_type: str,
    require_active: bool = True,
) -> dict[str, Any] | None:
    target = normalize_webhook_url(target_url)
    for hook in webhooks:
        if str(hook.get("event_type") or "") != event_type:
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


STATUS_LABELS: dict[OnboardingStatus, str] = {
    "not_initialized": "Non initialisé — configurez la niche, validez le prompt, puis initiez le webhook.",
    "webhook_incomplete": "Webhooks enregistrés — cliquez **Envoyer en prod** pour activer l'Inbox.",
    "niche_mismatch": "Niche incorrecte — la config enregistrée ne correspond pas à cette campagne. Réactivez avec la bonne niche.",
    "waiting_for_replies": "Inbox active — en attente de réponses.",
    "paused": "Campagne en pause.",
}


def validate_campaign_readiness(
    config: dict[str, Any],
    campaign_id: str,
) -> CampaignReadiness:
    status = str(config.get("status") or "not_initialized")
    if status not in ("waiting_for_replies", "paused"):
        return CampaignReadiness(False, "not_active")

    if not config.get("initialized_at"):
        return CampaignReadiness(False, "missing_initialized_at")

    if not str(config.get("prompt_snapshot") or "").strip():
        return CampaignReadiness(False, "missing_prompt_snapshot")

    webhook_id = str(config.get("webhook_id") or "")
    ooo_webhook_id = str(config.get("ooo_webhook_id") or "")
    if not webhook_id or not ooo_webhook_id:
        return CampaignReadiness(False, "missing_webhooks")

    niche_preset_id = str(config.get("niche_preset_id") or "")
    target_type = str(config.get("target_type") or "")
    prompt_key = str(config.get("prompt_key") or "")
    expected_key = f"{niche_preset_id}_{target_type}"
    if prompt_key != expected_key:
        return CampaignReadiness(False, "prompt_key_mismatch")

    expected_preset = resolve_preset_for_campaign(campaign_id)
    if expected_preset and niche_preset_id != expected_preset:
        return CampaignReadiness(False, "niche_mismatch")

    return CampaignReadiness(True)


def merge_webhook_config(
    existing: dict[str, Any] | None,
    new_fields: dict[str, Any],
) -> dict[str, Any]:
    """Preserve activation status when re-registering webhooks."""
    row = dict(new_fields)
    if not existing:
        row.setdefault("status", "not_initialized")
        row.setdefault("prompt_snapshot", "")
        return row

    existing_status = str(existing.get("status") or "not_initialized")
    if existing_status in ("waiting_for_replies", "paused"):
        row["status"] = existing_status
        if existing.get("initialized_at"):
            row["initialized_at"] = existing["initialized_at"]
        if existing.get("prompt_snapshot"):
            row["prompt_snapshot"] = existing["prompt_snapshot"]
    else:
        row.setdefault("status", "not_initialized")
        row.setdefault("prompt_snapshot", existing.get("prompt_snapshot") or "")

    return row


def derive_onboarding_status(
    config: dict[str, Any] | None,
    campaign_id: str,
) -> OnboardingStatus:
    if not config:
        return "not_initialized"

    readiness = validate_campaign_readiness(config, campaign_id)
    if readiness.ready:
        return str(config.get("status") or "waiting_for_replies")  # type: ignore[return-value]

    if readiness.reason == "niche_mismatch":
        return "niche_mismatch"

    webhook_id = str(config.get("webhook_id") or "")
    ooo_webhook_id = str(config.get("ooo_webhook_id") or "")
    if webhook_id and ooo_webhook_id:
        return "webhook_incomplete"

    return "not_initialized"


def assert_campaign_ready_for_activation(
    *,
    campaign_id: str,
    niche_preset_id: str,
    target_type: str,
    prompt_snapshot: str,
    webhook_id: str,
    ooo_webhook_id: str,
) -> None:
    if not prompt_snapshot.strip():
        raise ValueError("Le prompt est vide — validez le prompt avant l'activation.")
    if not webhook_id or not ooo_webhook_id:
        raise ValueError("Les webhooks ne sont pas enregistrés.")

    expected_preset = resolve_preset_for_campaign(campaign_id)
    if expected_preset and niche_preset_id != expected_preset:
        raise ValueError(
            f"Cette campagne est liée à « {preset_label(expected_preset)} », "
            f"pas « {preset_label(niche_preset_id)} »."
        )


def ensure_webhook(
    instantly_client: Any,
    *,
    campaign_id: str,
    campaign_name: str,
    target_url: str,
    secret: str,
    event_type: str,
    name_prefix: str,
) -> str:
    if not is_valid_webhook_target_url(target_url):
        raise ValueError(
            webhook_url_error()
            or "URL webhook invalide — utilisez la prod `https://www.hercule.dev`."
        )

    webhooks = instantly_client.list_webhooks()
    match = find_campaign_webhook(
        webhooks,
        campaign_id=campaign_id,
        target_url=target_url,
        event_type=event_type,
        require_active=False,
    )
    auth_headers = {"Authorization": f"Bearer {secret}"} if secret else None
    webhook_id = ""
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
            event_type=event_type,
            name=f"{name_prefix} — {campaign_name}"[:80],
            campaign=campaign_id,
            headers=auth_headers,
        )
        webhook_id = str(created.get("id") or "")
    if not webhook_id:
        raise RuntimeError(f"Failed to register {event_type} webhook")
    return webhook_id


def initiate_webhooks(
    instantly_client: Any,
    *,
    campaign_id: str,
    campaign_name: str,
    target_url: str,
    secret: str,
) -> tuple[str, str]:
    reply_id = ensure_webhook(
        instantly_client,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        target_url=target_url,
        secret=secret,
        event_type=REPLY_WEBHOOK_EVENT,
        name_prefix="Hercule AI Reply",
    )
    ooo_id = ensure_webhook(
        instantly_client,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        target_url=target_url,
        secret=secret,
        event_type=OOO_WEBHOOK_EVENT,
        name_prefix="Hercule AI OOO",
    )
    return reply_id, ooo_id


def activate_campaign(
    *,
    campaign_id: str,
    campaign_name: str,
    niche_preset_id: str,
    niche_metadata: dict[str, Any],
    target_type: str,
    prompt_key: str,
    prompt_snapshot: str,
    webhook_id: str,
    ooo_webhook_id: str,
) -> dict[str, Any]:
    assert_campaign_ready_for_activation(
        campaign_id=campaign_id,
        niche_preset_id=niche_preset_id,
        target_type=target_type,
        prompt_snapshot=prompt_snapshot,
        webhook_id=webhook_id,
        ooo_webhook_id=ooo_webhook_id,
    )
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "niche_preset_id": niche_preset_id,
        "niche_metadata": niche_metadata,
        "target_type": target_type,
        "prompt_key": prompt_key,
        "prompt_snapshot": prompt_snapshot,
        "webhook_id": webhook_id,
        "ooo_webhook_id": ooo_webhook_id,
        "status": "waiting_for_replies",
        "initialized_at": now,
    }
    return row
