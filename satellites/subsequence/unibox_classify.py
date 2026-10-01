"""Unibox email classification — template fingerprints and CRM step derivation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from shared.instantly_client import InstantlyClient

PipelineStep = Literal[
    "step_0", "step_1", "step_2", "step_3", "step_4", "replies_to_handle"
]
Flow = Literal[
    "interested_email1",
    "interested_email2",
    "interested_email3",
    "no_show_email1",
    "no_show_email2",
]

INTERESTED_FLOWS: list[Flow] = [
    "interested_email1",
    "interested_email2",
    "interested_email3",
]
NO_SHOW_FLOWS: list[Flow] = ["no_show_email1", "no_show_email2"]
ALL_HERCULE_FLOWS: list[Flow] = [*INTERESTED_FLOWS, *NO_SHOW_FLOWS]

FLOW_FINGERPRINTS: dict[Flow, list[str]] = {
    "interested_email1": [
        "voici les precisions",
        "notre accompagnement ajuste",
        "negocions vos prix fournisseurs",
        "voici plus de precisions",
        "pour faire simple",
        "cabinets partenaires",
        "au minimum 2 associes",
        "plus de 3 associes",
        "proposer mon cabinet",
        "mon cabinet est compatible",
        "entreprises de btp",
        "dentistes et veterinaires",
        "approche a 360",
        "echanges entre cabinets et entreprise",
        "ignorez precisement ou il perd",
        "30 minutes",
        "principales sources de perte",
        "recuperer de la marge",
        "leviers rapide a corriger",
        "par la suite vous accompagner",
        "etude prend environ 20 minutes",
        "avancer les frais vous-meme",
        "payer vos fournisseurs",
        "possibilites adaptees",
    ],
    "interested_email2": [
        "je reviens vers vous sur mon message",
        "etude prend environ 20 minutes",
        "avancer les frais vous-meme",
        "bonne activite tout en laissant",
        "achats trop eleves",
        "couts de personnel",
        "restaurant peut bien fonctionner",
        "perdant une partie de sa marge",
        "contrat annuel en attente",
        "mensuellement",
        "echanges entre cabinets et entreprise",
        "confirmer que votre reservation calendly",
    ],
    "interested_email3": [
        "dernier message de mon cote",
        "etude dure environ 20 minutes",
        "avancer vous-meme les frais",
        "beaucoup travailler pour un benefice",
        "marge disparait",
        "cloturer nos echanges",
        "bonne continuation",
        "retirer de notre liste",
    ],
    "no_show_email1": [
        "confirmer si votre reservation calendly",
        "demandez l audit",
        "demandez l'audit",
    ],
    "no_show_email2": [
        "n'ayant recu aucune confirmation",
        "retirer votre agence",
    ],
}

FLOW_SHORT_TAGS: dict[Flow, str] = {
    "interested_email1": "E1",
    "interested_email2": "E2",
    "interested_email3": "E3",
    "no_show_email1": "NS1",
    "no_show_email2": "NS2",
}

STEP_RANK: dict[PipelineStep, int] = {
    "step_0": 0,
    "step_1": 1,
    "step_2": 2,
    "step_3": 3,
    "step_4": 4,
    "replies_to_handle": 5,
}

NO_SHOW_STATUS = -4

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_email_text(raw: str) -> str:
    """Lowercase, strip HTML, remove accents for fingerprint matching."""
    text = _HTML_TAG_RE.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return _strip_accents(text)


def is_hercule_email(text: str) -> bool:
    normalized = normalize_email_text(text)
    return (
        "beatrice meyer" in normalized
        or "hercule.dev" in normalized
        or "jum-advisory.com" in normalized
        or "rentabilite-restaurant" in normalized
    )


def match_flows(text: str, *, allowed_flows: list[Flow]) -> set[Flow]:
    normalized = normalize_email_text(text)
    if not is_hercule_email(normalized):
        return set()
    matched: set[Flow] = set()
    for flow in allowed_flows:
        for phrase in FLOW_FINGERPRINTS[flow]:
            if phrase in normalized:
                matched.add(flow)
                break
    return matched


def derive_step_from_flows(flows: set[str], *, is_no_show: bool) -> PipelineStep:
    """Derive CRM step. When is_no_show is used, still counts interested flows (mixed sends)."""
    _ = is_no_show  # status tag may not match actual email template sent
    if "interested_email3" in flows or "no_show_email2" in flows:
        return "step_3"
    if "interested_email2" in flows:
        return "step_2"
    if "interested_email1" in flows or "no_show_email1" in flows:
        return "step_1"
    return "step_0"


def derive_step_unified(flows: set[str]) -> PipelineStep:
    return derive_step_from_flows(flows, is_no_show=False)


def merge_steps(
    proposed: PipelineStep,
    current: PipelineStep | None,
    *,
    overwrite: bool,
) -> PipelineStep:
    if current is None:
        return proposed
    if overwrite:
        return proposed
    if STEP_RANK[proposed] >= STEP_RANK[current]:  # type: ignore[index]
        return proposed
    return current  # type: ignore[return-value]


def extract_email_text(item: dict[str, Any]) -> tuple[str, bool]:
    """Return (text, has_body). has_body=False means subject-only (low confidence)."""
    body = item.get("body")
    if isinstance(body, dict):
        for key in ("html", "text", "plain"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value, True
    for key in ("body_html", "html", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value, True
    subject = str(item.get("subject") or "")
    return subject, False


def fetch_email_detail(client: InstantlyClient, email_id: str) -> dict[str, Any] | None:
    try:
        data = client._fetch(f"/emails/{email_id.strip()}", method="GET")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def email_timestamp(item: dict[str, Any]) -> str:
    return str(item.get("timestamp_email") or item.get("timestamp_created") or "")


def flows_from_existing(existing: list[str], *, is_no_show: bool) -> set[str]:
    allowed = set(NO_SHOW_FLOWS if is_no_show else INTERESTED_FLOWS)
    return {flow for flow in existing if flow in allowed}


def is_no_show_status(status: int | None) -> bool:
    return status == NO_SHOW_STATUS


def classify_sent_items(
    sent_items: list[dict[str, Any]],
    *,
    is_no_show: bool,
    client: InstantlyClient | None = None,
) -> tuple[set[Flow], dict[Flow, str], bool]:
    """Classify sent Unibox email dicts. Returns (flows, timestamps, low_confidence)."""
    allowed: list[Flow] = list(NO_SHOW_FLOWS if is_no_show else INTERESTED_FLOWS)
    detected: set[Flow] = set()
    timestamps: dict[Flow, str] = {}
    low_confidence = False

    for item in sent_items:
        text, has_body = extract_email_text(item)
        if not has_body and item.get("id") and client is not None:
            detail = fetch_email_detail(client, str(item["id"]))
            if detail:
                text, has_body = extract_email_text(detail)
                item = {**item, **detail}

        if not text.strip():
            continue

        matched = match_flows(text, allowed_flows=allowed)
        if not matched:
            continue

        if not has_body:
            low_confidence = True

        ts = email_timestamp(item)
        for flow in matched:
            detected.add(flow)
            prev = timestamps.get(flow, "")
            if ts and (not prev or ts > prev):
                timestamps[flow] = ts

    return detected, timestamps, low_confidence


def classify_lead_emails(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
    is_no_show: bool,
) -> tuple[set[Flow], dict[Flow, str], bool]:
    """Classify sent Unibox emails for one lead."""
    sent_items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="sent",
        limit=50,
    )
    return classify_sent_items(sent_items, is_no_show=is_no_show, client=client)


def flows_from_existing_unified(existing: list[str]) -> set[str]:
    allowed = set(ALL_HERCULE_FLOWS)
    return {flow for flow in existing if flow in allowed}


def classify_lead_emails_unified(
    client: InstantlyClient,
    *,
    lead_email: str,
    campaign_id: str,
) -> tuple[set[Flow], dict[Flow, str], bool]:
    """Classify sent Unibox emails using all interested + no-show flows."""
    sent_items = client.list_emails(
        search=lead_email,
        campaign_id=campaign_id,
        email_type="sent",
        limit=50,
    )
    detected: set[Flow] = set()
    timestamps: dict[Flow, str] = {}
    low_confidence = False

    for item in sent_items:
        text, has_body = extract_email_text(item)
        if not has_body and item.get("id"):
            detail = fetch_email_detail(client, str(item["id"]))
            if detail:
                text, has_body = extract_email_text(detail)
                item = {**item, **detail}

        if not text.strip():
            continue

        matched = match_flows(text, allowed_flows=list(ALL_HERCULE_FLOWS))
        if not matched:
            continue

        if not has_body:
            low_confidence = True

        ts = email_timestamp(item)
        for flow in matched:
            detected.add(flow)
            prev = timestamps.get(flow, "")
            if ts and (not prev or ts > prev):
                timestamps[flow] = ts

    return detected, timestamps, low_confidence


def flow_tag_for_text(text: str, *, is_no_show: bool) -> str | None:
    allowed: list[Flow] = list(NO_SHOW_FLOWS if is_no_show else INTERESTED_FLOWS)
    matched = match_flows(text, allowed_flows=allowed)
    if not matched:
        return None
    ordered = NO_SHOW_FLOWS if is_no_show else INTERESTED_FLOWS
    for flow in reversed(ordered):
        if flow in matched:
            return FLOW_SHORT_TAGS[flow]
    return None
