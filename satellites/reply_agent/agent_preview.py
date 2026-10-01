"""xAI Grok reply preview for Try agent (no send)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

import requests

from config import grok_api_key
from lead_links import apply_prompt_link_variables, resolve_prompt_links
from lead_tags import TAG_LABELS
from conference_cohort_context import (
    CONFERENCE_BRIEFING_WHEN,
    CONFERENCE_COHORT_SEQUENCE,
    CONFERENCE_CIF_DEMAND_CONTEXT,
    CONFERENCE_DEC_DEMAND_CONTEXT,
)
from legal_content import (
    build_knowledge_pack_cached,
    is_assurance_niche_preset,
    is_cif_niche_preset,
    is_comptable_niche_preset,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

GROK_API_URL = "https://api.x.ai/v1/chat/completions"
PRIMARY_MODEL = "grok-4-1-fast"
FALLBACK_MODEL = "grok-build-0.1"
MAX_OUTPUT_TOKENS = 200
DUE_DILIGENCE_MAX_OUTPUT_TOKENS = 1400
INBOUND_TEXT_MAX_CHARS = 2000
DEFAULT_GROK_TEMPERATURE = 0.5


def truncate_inbound_text(text: str, max_chars: int = INBOUND_TEXT_MAX_CHARS) -> str:
    trimmed = (text or "").strip()
    if not trimmed:
        return "(empty body)"
    if len(trimmed) <= max_chars:
        return trimmed
    return f"{trimmed[: max_chars - 1]}…"


def grok_temperature() -> float:
    raw = os.getenv("GROK_TEMPERATURE", "").strip()
    if not raw:
        return DEFAULT_GROK_TEMPERATURE
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_GROK_TEMPERATURE
    return max(0.0, min(1.0, value))


def build_conference_objection_rules(niche_preset_id: str | None = None) -> str | None:
    when = CONFERENCE_BRIEFING_WHEN
    if is_comptable_niche_preset(niche_preset_id or ""):
        return f"""{CONFERENCE_COHORT_SEQUENCE}
- {CONFERENCE_DEC_DEMAND_CONTEXT}

Première réponse (intérêt, question, demande RDV / « appelez-moi ») :
- Réponse directe et chaleureuse — PAS d'AER, PAS de 2 500 €, PAS d'option 1:1.
- Pousser l'appel de présentation **{when}** + lien CTA briefing collectif.

Objection conférence EXPLICITE (comptable — reservation-conference.html) — 2e réponse uniquement :
- Déclencheurs : refus clair du format collectif APRÈS invitation au briefing — « pas de visio collective », « je ne fais pas les appels en conférence », « pas intéressé par un appel à plusieurs », etc. — PAS « appelez-moi » seul ni une réponse positive.
- Maximum 4 phrases courtes dans reply_text pour cette objection (hors signature et lien CTA).
- Acknowledge : valider la réaction sans s'excuser (ex. « Je comprends que le format conférence ne soit pas votre habitude. »).
- Explain : un accompagnement Hercule sur-mesure démarre à 2 500 € ; pour proposer une tarification accessible aux cabinets qui souhaitent une solution clé en main pour développer rapidement leur clientèle BNC/BIC/TNS, nous présentons cette offre en appel conférence. Exception pricing : 2 500 € autorisé uniquement pour cette objection.
- Redirect : lien CTA briefing collectif fourni + « Si vous souhaitez réserver un appel en 1:1 avec le dirigeant pour discuter d'une solution sur-mesure, répondez à ce mail. »
- should_reply true — ce n'est PAS une raison d'abstenir ; recovery_confidence ≥ 75 si tag Lead.
- Pas de lien Calendly 1:1 ni d'appel téléphonique ad hoc en alternative."""
    if is_cif_niche_preset(niche_preset_id or ""):
        return f"""{CONFERENCE_COHORT_SEQUENCE}
- {CONFERENCE_CIF_DEMAND_CONTEXT}

Première réponse (intérêt, question, demande RDV / « appelez-moi ») :
- Réponse directe et chaleureuse — PAS d'AER, PAS de 2 500 €, PAS d'option 1:1.
- Pousser l'appel de présentation **{when}** + lien CTA briefing collectif.

Objection conférence EXPLICITE (CIF — reservation-conference.html) — 2e réponse uniquement :
- Déclencheurs : refus clair du format collectif APRÈS invitation au briefing — « pas de visio collective », « je ne fais pas les appels en conférence », « pas intéressé par un appel à plusieurs », etc. — PAS « appelez-moi » seul ni une réponse positive.
- Maximum 4 phrases courtes dans reply_text pour cette objection (hors signature et lien CTA).
- Acknowledge : valider la réaction sans s'excuser (ex. « Je comprends que le format conférence ne soit pas votre habitude. »).
- Explain : un accompagnement Hercule sur-mesure démarre à 2 500 € ; pour proposer une tarification accessible aux cabinets qui souhaitent une solution clé en main pour développer rapidement leur clientèle professionnelle (chirurgiens-dentistes / CIF), nous présentons cette offre en appel conférence. Exception pricing : 2 500 € autorisé uniquement pour cette objection.
- Redirect : lien CTA briefing collectif fourni + « Si vous souhaitez réserver un appel en 1:1 avec le dirigeant pour discuter d'une solution sur-mesure, répondez à ce mail. »
- should_reply true — ce n'est PAS une raison d'abstenir ; recovery_confidence ≥ 75 si tag Lead.
- Pas de lien Calendly 1:1 ni d'appel téléphonique ad hoc en alternative."""
    if is_assurance_niche_preset(niche_preset_id or ""):
        return f"""Première réponse (intérêt, question, demande RDV / « appelez-moi ») :
- Réponse directe et chaleureuse — PAS d'AER, PAS de 2 500 €, PAS d'option 1:1.
- Pousser l'appel de présentation **{when}** + lien CTA briefing collectif.

Objection conférence EXPLICITE (IAS — reservation-conference.html) — 2e réponse uniquement :
- Déclencheurs : refus clair du format collectif APRÈS invitation au briefing — « pas de visio collective », « je ne fais pas les appels en conférence », « pas intéressé par un appel à plusieurs », etc. — PAS « appelez-moi » seul ni une réponse positive.
- Maximum 4 phrases courtes dans reply_text pour cette objection (hors signature et lien CTA).
- Acknowledge : valider la réaction sans s'excuser (ex. « Je comprends que le format conférence ne soit pas votre habitude. »).
- Explain : un accompagnement Hercule sur-mesure démarre à 2 500 € ; pour proposer une tarification accessible aux cabinets qui souhaitent une solution clé en main pour développer rapidement leur clientèle TNS / libéraux, nous présentons cette offre en appel conférence. Exception pricing : 2 500 € autorisé uniquement pour cette objection.
- Redirect : lien CTA briefing collectif fourni + « Si vous souhaitez réserver un appel en 1:1 avec le dirigeant pour discuter d'une solution sur-mesure, répondez à ce mail. »
- should_reply true — ce n'est PAS une raison d'abstenir ; recovery_confidence ≥ 75 si tag Lead.
- Pas de lien Calendly 1:1 ni d'appel téléphonique ad hoc en alternative."""
    return None


def build_prospect_quality_objection_rules() -> str:
    return f"""Objection qualité prospects / Pappers / Sirene (R2 — double verrou qualification) :
- should_reply true — ne PAS s'abstenir ; recovery_confidence ≥ 85 si tag Lead.
- NE PAS utiliser AER (sauf paragraphe tarif si demande HT sans RDV dans le même mail — AER tarif léger uniquement sur ce point).
- Rédige 4 à 5 paragraphes courts, sans listes à puces ni numérotées.
- Structure : (1) accusé réception des questions (qualification des dirigeants + tarif si demandé) ; (2) R2 — Pappers/Sirene servent uniquement à repérer des structures ; aucun dirigeant transmis sur un signal seul ; chaque profil passe par un appel téléphonique de qualification, un contrat signé, puis un retour par mail confirmant actifs et besoin — appel + confirmation écrite éliminent le bruit, vous ne recevez que des personnes déjà intéressées ; (3) si tarif HT sans RDV demandé — ne pas chiffrer, conditions au briefing collectif du {CONFERENCE_BRIEFING_WHEN}, renvoi discret hercule.dev/cvg/comptable sans montants ; (4) CTA briefing collectif, lien seul sur sa ligne.
- Interdit : reframe perception (leads, Google Ads, Meta, cold email, « coût supplémentaire »), reconfiguration de statut, machine à cash, tableau lead-gen vs Hercule.
- Ne pas confondre qualification dirigeant (appel téléphonique) et bande passante cabinet (visios qualifiantes)."""


def build_partner_due_diligence_rules() -> str:
    return f"""Email questionnaire / due diligence partenaire (prospect intéressé qui demande des précisions) :
- should_reply true — ne PAS s'abstenir ; recovery_confidence ≥ 85 si tag Lead.
- NE PAS utiliser AER. Cette consigne remplace la limite de phrases.
- Rédige 4 à 8 paragraphes thématiques courts, sans listes à puces ni numérotées.
- Structure, dans cet ordre : (1) accusé réception de l'intérêt et des questions ; (2) périmètre de la mission et besoins des dirigeants ; (3) cadre réglementaire et responsabilités — le cabinet porte le conseil, Hercule ne sélectionne ni ne commercialise de produits ; (4) qualification des prospects et organisation des mises en relation (exclusivité, visio dirigeant et cabinet, Calendly/Zoom) ; (5) modèle économique — 0 % de commission, dirigeant ne paie rien, renvoyer vers le site tarifs SANS chiffrer ; (6) CTA briefing collectif, lien seul sur sa ligne. Les documents détaillés (présentation, CGV, convention) sont présentés au briefing du {CONFERENCE_BRIEFING_WHEN} — ne pas promettre un envoi de convention type par email.
- Ne pas inventer de volume de cabinets, de durée au minute près, ni de produits imposés."""


def build_international_rules(niche_preset_id: str | None = None) -> str | None:
    if is_comptable_niche_preset(niche_preset_id or ""):
        return """International BE/CH/CA (DEC — prioritaire sur briefing France si lead BE/CH/CA détecté) :
- Détection : email .be/.ch/.ca, mention Belgique/Suisse/Canada, question scope France/hors France.
- Étape 1 (pas d'acceptation tarifs explicite) : réponse directe — modèle France par défaut ; BE/CH/CA = échange 1:1 dirigeant + infrastructure sur mesure.
- Profils DEC : restaurants +3 salariés en chaos opérationnel (tenue comptable / social-paie).
- Tarifs autorisés en email : 1 499 USD/mois (Hercule) · 400 USD/mois min par profil · 10 profils/mois.
- Redirect étape 1 : « Si vous souhaitez échanger et acceptez ces tarifications, répondez à ce mail — vous recevrez un lien de planification unique. »
- PAS de briefing 13 oct, PAS de lien CTA conférence, PAS de lien Calendly inventé à l'étape 1.
- Gate : « oui » / « avec plaisir » / « je souhaite échanger » sans acceptation tarifs → rappeler montants USD et demander acceptation explicite.
- Étape 2 (acceptation tarifs explicite + tarifs déjà exposés dans le fil) : si Contexte Calendly fournit booking_url → l'inclure seul sur sa ligne."""
    if is_cif_niche_preset(niche_preset_id or "") or is_assurance_niche_preset(
        niche_preset_id or ""
    ):
        return """International BE/CH/CA (IAS + CIF — prioritaire sur briefing France si lead BE/CH/CA détecté) :
- Détection : email .be/.ch/.ca, mention Belgique/Suisse/Canada, question scope France/hors France.
- Étape 1 (pas d'acceptation tarifs explicite) : réponse directe — modèle France par défaut ; BE/CH/CA = échange 1:1 dirigeant + infrastructure sur mesure.
- Profils IAS (courtiers_prevoyance) : TNS/libéraux — passifs sociaux / prévoyance Madelin (COA, pas mandataire).
- Profils CIF (conseillers_gestion_patrimoine) : dentistes et vétérinaires 2+ salariés — trésorerie, pression fiscale, placement avoirs pro/privé.
- Tarifs autorisés en email : 1 499 USD/mois · 400 USD/mois min par profil · 10 profils/mois.
- Redirect étape 1 : « Si vous souhaitez échanger et acceptez ces tarifications, répondez à ce mail — vous recevrez un lien de planification unique. »
- PAS de briefing 13 oct, PAS de lien CTA conférence, PAS de lien Calendly inventé à l'étape 1.
- Gate : échange souhaité sans acceptation tarifs → rappeler montants USD et demander acceptation explicite.
- Étape 2 (acceptation tarifs explicite + tarifs déjà exposés dans le fil) : si Contexte Calendly fournit booking_url → l'inclure seul sur sa ligne."""
    return None


def build_global_rules(
    *,
    max_sentences: int = 3,
    niche_preset_id: str | None = None,
    partner_due_diligence: bool = False,
    prospect_quality_objection: bool = False,
) -> str:
    n = max(1, min(10, max_sentences))
    if partner_due_diligence:
        length_rule = build_partner_due_diligence_rules()
    elif prospect_quality_objection:
        length_rule = build_prospect_quality_objection_rules()
    elif n == 1:
        length_rule = (
            "Maximum 1 phrase courte dans reply_text (hors signature et lien CTA)."
        )
    else:
        length_rule = (
            f"Maximum {n} phrases courtes dans reply_text (hors signature et lien CTA)."
        )
    if is_cif_niche_preset(niche_preset_id or ""):
        pricing_url = "https://hercule.dev/cvg/conseil-financier"
    elif is_assurance_niche_preset(niche_preset_id or ""):
        pricing_url = "https://hercule.dev/cvg/courtier-assurance"
    elif is_comptable_niche_preset(niche_preset_id or ""):
        pricing_url = "https://hercule.dev/cvg/comptable"
    else:
        pricing_url = "https://hercule.dev/cvg"
    conference_rules = build_conference_objection_rules(niche_preset_id)
    international_rules = build_international_rules(niche_preset_id)
    conference_section = f"\n{conference_rules}\n" if conference_rules else ""
    international_section = f"\n{international_rules}\n" if international_rules else ""
    pricing_security_rule = (
        "- N'invente jamais de prix, délais, garanties ou fonctionnalités — sauf 2 500 € sur-mesure pour objection conférence (autorisé) et 1 499 USD / 400 USD pour flux international BE/CH/CA (autorisé)."
        if conference_rules or international_rules
        else "- N'invente jamais de prix, délais, garanties ou fonctionnalités."
    )
    return f"""Tu es Béatrice Meyer, responsable qualification chez Hercule (hercule.dev).

Réponds uniquement en JSON avec les clés : should_reply (boolean), reply_text (string|null), reason (string), recovery_confidence (number 0–100, obligatoire si tag Lead).

Règles quand should_reply est true :
- Texte brut uniquement dans reply_text (pas de HTML, pas de markdown).
- Rédige reply_text en français, vouvoiement, ton professionnel et direct — comme un email humain, pas une FAQ.
- {length_rule}
- Structure AER dans reply_text UNIQUEMENT pour les objections (tarif, refus format conférence explicite, bande passante, éligibilité) : (1) Acknowledge — valider l'objection sans céder ; (2) Explain — agiter la douleur / coût de l'inaction ou expliquer le positionnement ; (3) Redirect — lien CTA briefing collectif. Pour réponses positives, neutres ou demandes de RDV → réponse directe et chaleureuse sans AER ; pousser le briefing du {CONFERENCE_BRIEFING_WHEN}.
- Ne recopie pas mot à mot le pack de connaissances ; reformule avec tes mots.
- Sépare le corps, le lien CTA briefing et la clôture par une ligne vide (\\n\\n).
- Mets le lien CTA briefing seul sur sa propre ligne, en URL brute (sera affiché « Réserver » à l'envoi).
- Pour renvoyer vers le site (hors CTA briefing), intègre hercule.dev dans la phrase (ex. « …n'hésitez pas à vous rendre sur notre site internet hercule.dev ») — pas sur une ligne séparée ; utilise {pricing_url} si question tarifs.
- Termine par « Cordialement, », puis « Béatrice Meyer », puis « Hercule, Courtage contrat BNC/BIC », chaque élément sur sa propre ligne — sans URL https:// séparée en signature.
{conference_section}{international_section}
Ton — évite ces formulations :
- « Merci pour votre message » (sauf si le lead partage une info personnelle ou émotionnelle)
- « Je comprends votre préoccupation »
- « Je reste à votre disposition »
- « Je note votre question sur notre identité » (ou toute méta-formulation du type « je note votre question »)
- « réserver cette semaine » ou « réserver un créneau maintenant » (urgence forcée)
- listes à puces ou numérotées dans reply_text

Identité (questions « qui êtes-vous ») :
- Framing : Hercule est un groupement d'entrepreneurs dirigé par Evan Sinclair — réponse directe en une phrase.
- Ne pas mener par la raison sociale EI (Nanguy Evan Gbeho, entrepreneur individuel) sauf si le prospect demande explicitement l'immatriculation ou le RCS.

Contexte fil (historique de conversation) :
- Lis tout l'historique fourni avant de décider should_reply.
- Si l'inbound contient plusieurs questions ou objections, réponds à TOUTES dans reply_text (ne pas en omettre une).
- Si le prospect remercie ou confirme sans nouvelle question APRÈS qu'un rendez-vous Calendly est pris → should_reply false (ne pas renvoyer un rappel conférence).
- Si le prospect remercie pour la proposition sans confirmer ni refuser (« Merci pour cette proposition », « Merci pour votre offre », etc.) et qu'aucun RDV n'est enregistré → should_reply true : relance douce en demandant s'il souhaite prendre rendez-vous pour l'appel de présentation du {CONFERENCE_BRIEFING_WHEN} + lien CTA briefing.
- Si le prospect dit ne pas avoir saisi / ne pas comprendre (« je n'ai pas saisi », « je n'ai pas compris ») → should_reply true : clarifier en AER qui est Hercule (groupement d'entrepreneurs, Evan Sinclair) et le lien avec son métier — même si le cabinet est hors France.
- Un accusé de réception court qui clôt l'échange (« top merci », « parfait merci ») après réservation ou lien déjà traité ne mérite pas de nouvelle relance — sauf remerciement pour la proposition sans RDV (voir ci-dessus).

Recovery (tag Lead) :
- Toujours renseigner recovery_confidence (0–100) : probabilité que la relance soit rattrapable.
- « Non merci, pas notre cible » / refus définitif → should_reply false, recovery_confidence 10–25.
- « Non mais… » / objection format ou téléphone → should_reply true si rattrapable, recovery_confidence ≥ 75.
- « Je n'ai pas saisi » / incompréhension → should_reply true, recovery_confidence ≥ 80.
- Opt-out explicite (« non merci », « c'est mort », « stop », « ne plus me contacter ») → should_reply false, recovery_confidence 0 — ne pas confondre avec « non mais » ou un simple merci après réservation.
- Tag Interested : recovery_confidence optionnel (ignoré).

Signature :
- Avant « Cordialement, », inclure sur sa propre ligne : Répondez non si vous ne souhaitez plus de messages. (sans italique ni markdown)

Sécurité :
- Si la réponse n'est PAS clairement couverte par le pack de connaissances, mets should_reply à false et explique dans reason (en français). Exceptions : email de due diligence partenaire ou objection qualité prospects (R2) couvert par le pack — should_reply true.
{pricing_security_rule}
- Utilise uniquement le lien CTA fourni — n'invente jamais d'URL."""


def assemble_system_prompt(
    config: dict[str, Any],
    prompt_snapshot: str,
    *,
    max_sentences: int = 3,
    custom_directive: str | None = None,
    booking_context: str | None = None,
    partner_due_diligence: bool = False,
    prospect_quality_objection: bool = False,
) -> str:
    niche_preset_id = str(config.get("niche_preset_id") or "")
    parts = [
        build_global_rules(
            max_sentences=max_sentences,
            niche_preset_id=niche_preset_id,
            partner_due_diligence=partner_due_diligence,
            prospect_quality_objection=prospect_quality_objection,
        ),
        "",
        "## Pack de connaissances",
        build_knowledge_pack(config),
        "",
        "## Prompt campagne",
        prompt_snapshot,
    ]
    directive = (custom_directive or "").strip()
    if directive:
        parts.extend(["", "## Directive custom (opérateur)", directive])
    calendly_context = (booking_context or "").strip()
    if calendly_context:
        parts.extend(["", "## Contexte Calendly (ne pas inventer)", calendly_context])
    return "\n".join(parts)


def build_knowledge_pack(config: dict[str, Any]) -> str:
    niche = config.get("niche_metadata") or {}
    niche_angle = niche.get("angle") if isinstance(niche.get("angle"), str) else config.get("niche_preset_id", "")
    niche_effectif = niche.get("effectif_cible") if isinstance(niche.get("effectif_cible"), str) else ""
    target_type = str(config.get("target_type") or "buyer")
    return build_knowledge_pack_cached(
        str(config.get("niche_preset_id") or ""),
        target_type,
        str(niche_angle or ""),
        str(niche_effectif or ""),
    )


def _resolve_model(env_name: str, default: str) -> str:
    value = os.getenv(env_name, "").strip()
    return value or default


def _parse_grok_json(content: str) -> dict[str, Any]:
    trimmed = content.strip()
    match = re.search(r"\{[\s\S]*\}", trimmed)
    raw = match.group(0) if match else trimmed
    parsed = json.loads(raw)
    should_reply = bool(parsed.get("should_reply"))
    reply_text = parsed.get("reply_text")
    if isinstance(reply_text, str) and reply_text.strip():
        reply_text = reply_text.strip()
    else:
        reply_text = None
    reason = str(parsed.get("reason") or "Aucune raison fournie").strip()
    recovery_confidence: int | None = None
    raw_confidence = parsed.get("recovery_confidence")
    if isinstance(raw_confidence, (int, float)) and float(raw_confidence) == raw_confidence:
        recovery_confidence = max(0, min(100, int(round(float(raw_confidence)))))
    elif isinstance(raw_confidence, str) and raw_confidence.strip():
        try:
            parsed_confidence = float(raw_confidence.strip())
            recovery_confidence = max(0, min(100, int(round(parsed_confidence))))
        except ValueError:
            recovery_confidence = None
    return {
        "should_reply": should_reply and bool(reply_text),
        "reply_text": reply_text if should_reply and reply_text else None,
        "reason": reason,
        "recovery_confidence": recovery_confidence,
    }


def _parse_cost_usd_ticks(data: dict[str, Any]) -> int | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    raw = usage.get("cost_in_usd_ticks")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _parse_rate_limit_wait_seconds(error_text: str) -> float | None:
    match = re.search(r"try again in ([\d.]+)s", error_text, re.I)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc)
    return "429" in text or "rate limit" in text.lower()


def _call_grok_model(
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> tuple[dict[str, Any], str, int | None]:
    temp = grok_temperature()
    # #region agent log
    try:
        requests.post(
            "http://127.0.0.1:7849/ingest/172cb84e-a8e1-4d83-b273-2b61310f5e7d",
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "cfd30a",
            },
            json={
                "sessionId": "cfd30a",
                "runId": "post-fix",
                "hypothesisId": "tone-v2",
                "location": "agent_preview.py:_call_grok_model",
                "message": "grok call params",
                "data": {
                    "model": model,
                    "temperature": temp,
                    "tone_rules_v2": "Maximum" in system_prompt
                    and "urgence artificielle" in system_prompt,
                },
                "timestamp": int(time.time() * 1000),
            },
            timeout=2,
        )
    except Exception:
        pass
    # #endregion
    response = requests.post(
        GROK_API_URL,
        headers={
            "Authorization": f"Bearer {grok_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": temp,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(
            f"Grok {model} failed ({response.status_code}): {response.text[:300]}"
        )
    data = response.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not str(content).strip():
        raise RuntimeError(f"Grok {model} returned empty content")
    return _parse_grok_json(str(content)), model, _parse_cost_usd_ticks(data)


def _generate_with_models(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> tuple[dict[str, Any], str, int | None]:
    primary = _resolve_model("GROK_PRIMARY_MODEL", PRIMARY_MODEL)
    fallback = _resolve_model("GROK_FALLBACK_MODEL", FALLBACK_MODEL)

    def _call_with_json_retries(model: str) -> tuple[dict[str, Any], str, int | None]:
        last_json_err: json.JSONDecodeError | None = None
        for _ in range(3):
            try:
                return _call_grok_model(
                    model,
                    system_prompt,
                    user_prompt,
                    max_tokens=max_tokens,
                )
            except json.JSONDecodeError as err:
                last_json_err = err
        if last_json_err is not None:
            raise last_json_err
        raise RuntimeError(f"Grok {model} failed without a JSON error")

    try:
        return _call_with_json_retries(primary)
    except Exception as primary_err:
        if not fallback or (
            not _is_rate_limit_error(primary_err)
            and not isinstance(primary_err, json.JSONDecodeError)
        ):
            raise
        try:
            return _call_with_json_retries(fallback)
        except Exception as fallback_err:
            raise RuntimeError(
                f"Primary ({primary}) failed: {primary_err}. "
                f"Fallback ({fallback}) failed: {fallback_err}"
            ) from fallback_err


def _target_type_from_config(config: dict[str, Any]) -> Literal["buyer", "seller"]:
    value = str(config.get("target_type") or "buyer").strip().lower()
    return "seller" if value == "seller" else "buyer"


def _max_sentences_from_config(config: dict[str, Any], override: int | None = None) -> int:
    if override is not None:
        return max(1, min(10, override))
    raw = config.get("max_sentences", 2)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 2
    return max(1, min(10, value))


def generate_reply_preview(
    config: dict[str, Any],
    inbound_text: str,
    lead_email: str,
    *,
    prompt_override: str | None = None,
    max_sentences: int | None = None,
    custom_directive: str | None = None,
    interest_label: str | None = None,
    lead_name: str | None = None,
    thread_context: str | None = None,
) -> dict[str, Any]:
    prompt_snapshot = (
        prompt_override
        if prompt_override is not None
        else str(config.get("prompt_snapshot") or "")
    ).strip()
    if not prompt_snapshot:
        raise ValueError("Missing prompt_snapshot on campaign config")

    tag_label = (interest_label or TAG_LABELS["lead"]).strip()

    target_type = _target_type_from_config(config)
    prompt_links = resolve_prompt_links(lead_email, target_type)
    prompt_snapshot = apply_prompt_link_variables(
        prompt_snapshot,
        prompt_links["primary"],
        target_type,
        prompt_links,
    )
    sentence_count = _max_sentences_from_config(config, max_sentences)

    from calendly_booking import resolve_booking_context

    booking_context = resolve_booking_context(
        campaign_id=str(config.get("campaign_id") or ""),
        niche_preset_id=str(config.get("niche_preset_id") or ""),
        inbound_text=inbound_text,
        lead_email=lead_email,
        lead_name=(lead_name or lead_email).strip(),
        thread_context=thread_context,
    )

    from inbound_question import (
        inbound_looks_like_partner_due_diligence,
        inbound_looks_like_prospect_quality_objection,
    )

    partner_due_diligence = inbound_looks_like_partner_due_diligence(inbound_text)
    prospect_quality_objection = (
        not partner_due_diligence
        and inbound_looks_like_prospect_quality_objection(inbound_text)
    )
    extended_inbound = partner_due_diligence or prospect_quality_objection
    output_tokens = (
        DUE_DILIGENCE_MAX_OUTPUT_TOKENS if extended_inbound else MAX_OUTPUT_TOKENS
    )

    system_prompt = assemble_system_prompt(
        config,
        prompt_snapshot,
        max_sentences=sentence_count,
        custom_directive=custom_directive,
        booking_context=booking_context,
        partner_due_diligence=partner_due_diligence,
        prospect_quality_objection=prospect_quality_objection,
    )
    user_prompt_parts = [
        f"Email du lead : {lead_email}",
        f"Tag Instantly du lead : {tag_label}",
        "",
        f"Lien CTA (utilise exactement cette URL dans reply_text) : {prompt_links['primary']}",
    ]
    if (thread_context or "").strip():
        user_prompt_parts.extend(
            [
                "",
                "Historique du fil (du plus ancien au plus récent) :",
                thread_context.strip(),
            ]
        )
    user_prompt_parts.extend(
        [
            "",
            "Réponse entrante à traiter (dernier message du prospect) :",
            truncate_inbound_text(
                inbound_text,
                max_chars=8000 if extended_inbound else INBOUND_TEXT_MAX_CHARS,
            ),
        ]
    )
    user_prompt = "\n".join(user_prompt_parts)

    knowledge_pack = build_knowledge_pack(config)
    legal_anchors = (
        "groupement d'entrepreneurs",
        "Evan Sinclair",
        "je note votre question",
    )
    pack_lower = knowledge_pack.lower()
    # #region agent log
    try:
        requests.post(
            "http://127.0.0.1:7849/ingest/172cb84e-a8e1-4d83-b273-2b61310f5e7d",
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "713bee",
            },
            json={
                "sessionId": "713bee",
                "runId": "pre-grok",
                "hypothesisId": "H1-H5",
                "location": "agent_preview.py:generate_reply_preview",
                "message": "knowledge pack legal anchor coverage",
                "data": {
                    "niche_preset_id": config.get("niche_preset_id"),
                    "target_type": config.get("target_type"),
                    "anchors_present": {
                        anchor: anchor.lower() in pack_lower for anchor in legal_anchors
                    },
                    "inbound_preview": truncate_inbound_text(inbound_text)[:120],
                },
                "timestamp": int(time.time() * 1000),
            },
            timeout=2,
        )
    except Exception:
        pass
    # #endregion

    try:
        decision, model, cost_ticks = _generate_with_models(
            system_prompt, user_prompt, max_tokens=output_tokens
        )
    except Exception as exc:
        if not _is_rate_limit_error(exc):
            raise
        wait_s = _parse_rate_limit_wait_seconds(str(exc))
        if wait_s is None:
            raise
        time.sleep(min(wait_s + 1.0, 90.0))
        decision, model, cost_ticks = _generate_with_models(
            system_prompt, user_prompt, max_tokens=output_tokens
        )

    reply_text = decision.get("reply_text") or ""
    reply_lower = reply_text.lower()
    # #region agent log
    try:
        requests.post(
            "http://127.0.0.1:7849/ingest/172cb84e-a8e1-4d83-b273-2b61310f5e7d",
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "713bee",
            },
            json={
                "sessionId": "713bee",
                "runId": "post-grok",
                "hypothesisId": "H1-H5",
                "location": "agent_preview.py:generate_reply_preview",
                "message": "grok decision for inbound reply",
                "data": {
                    "niche_preset_id": config.get("niche_preset_id"),
                    "should_reply": decision.get("should_reply"),
                    "reason": decision.get("reason"),
                    "has2500": "2 500" in reply_text,
                    "has1to1": "1:1" in reply_text,
                    "has_mercredi_23": "mercredi 23" in reply_lower,
                    "has_conference_script": "appel conférence" in reply_lower,
                    "reply_has_groupement": "groupement" in reply_lower,
                    "reply_has_evan_sinclair": "evan sinclair" in reply_lower,
                    "reply_has_bad_meta": "je note votre question" in reply_lower,
                    "reply_has_bad_ei_lead": (
                        reply_lower.startswith("hercule est l'activité")
                        or "nanguy evan gbeho" in reply_lower[:120]
                    ),
                    "reply_preview": reply_text[:180],
                },
                "timestamp": int(time.time() * 1000),
            },
            timeout=2,
        )
    except Exception:
        pass
    # #endregion

    return {**decision, "model": model, "cost_usd_ticks": cost_ticks}
