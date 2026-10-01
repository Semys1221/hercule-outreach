"""Resolve per-lead CTA links from Supabase `public.leads` and substitute prompt variables."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from supabase_repo import get_client

TargetType = Literal["buyer", "seller"]

FALLBACK_BUYER = "https://www.hercule.dev/reservation"
FALLBACK_SELLER = "https://www.hercule.dev/reservation"

_OUTREACH_CATEGORIES = ("comptable", "cif", "comptable_delivery")


class PromptLinks(TypedDict):
    primary: str
    agence_link: str
    entreprise_link: str
    comptable_link: str
    cif_link: str
    jum_link: str


def fallback_cta_link(target_type: TargetType) -> str:
    return FALLBACK_BUYER if target_type == "buyer" else FALLBACK_SELLER


def _canonical_link(row: dict[str, Any]) -> str:
    link = str(row.get("reservation_link") or "").strip()
    if link:
        return link
    for key in (
        "reservation_comptable_link",
        "reservation_cif_link",
        "reservation_jum_link",
        "reservation_entreprise_link",
        "reservation_agence_link",
        "reservation_carte_t_link",
        "conference_link",
    ):
        legacy = str(row.get(key) or "").strip()
        if legacy:
            return legacy
    return ""


def _find_lead_by_email(email: str) -> tuple[str | None, dict[str, Any] | None]:
    normalized = email.strip().lower()
    client = get_client()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = (
                client.table("leads")
                .select("*")
                .eq("email", normalized)
                .limit(5)
                .execute()
            )
            rows = resp.data or []
            if rows:
                row = rows[0]
                return str(row.get("category") or ""), row
            return None, None
        except Exception as err:
            last_error = err
            if attempt < 2:
                import time

                time.sleep(0.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    return None, None


def resolve_prompt_links(lead_email: str, target_type: TargetType) -> PromptLinks:
    category, row = _find_lead_by_email(lead_email)
    fallback = fallback_cta_link(target_type)
    canonical = _canonical_link(row) if row else ""
    link = canonical or fallback

    return {
        "primary": link,
        "agence_link": link,
        "entreprise_link": link,
        "comptable_link": link,
        "cif_link": link,
        "jum_link": link,
    }


def resolve_lead_cta_link(lead_email: str, target_type: TargetType) -> str:
    return resolve_prompt_links(lead_email, target_type)["primary"]


def apply_prompt_link_variables(
    prompt: str,
    cta_link: str,
    target_type: TargetType,
    links: PromptLinks | None = None,
) -> str:
    reservation = cta_link.strip() or (links["primary"] if links else fallback_cta_link(target_type))
    result = prompt
    for key in (
        "reservation_link",
        "reservation_agence_link",
        "reservation_entreprise_link",
        "reservation_comptable_link",
        "reservation_cif_link",
        "reservation_jum_link",
        "reservation_carte_t_link",
        "conference_link",
    ):
        result = result.replace(f"{{{{{key}}}}}", reservation)
        result = result.replace(f"{{{key}}}", reservation)
    return result
