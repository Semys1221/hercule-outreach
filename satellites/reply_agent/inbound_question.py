"""Scheduling intent helpers mirrored from lib/ai-reply-agent/inbound-question.ts."""

from __future__ import annotations

import re

PHONE_REQUEST_KEYWORDS = (
    "téléphone",
    "telephone",
    "appeler",
    "appel ",
    "formulaire",
    "numéro",
    "numero",
    "joignable",
    "rappeler",
)

SCHEDULING_ANSWER_KEYWORDS = (
    "disponib",
    "demain",
    "matin",
    "après-midi",
    "apres-midi",
    "aprem",
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)

INTERNATIONAL_EMAIL_TLD = re.compile(r"\.(be|ch|ca)$", re.IGNORECASE)

INTERNATIONAL_GEO_KEYWORDS = (
    "belgique",
    "belge",
    "bruxelles",
    "brussels",
    "suisse",
    "switzerland",
    "genève",
    "geneve",
    "canada",
    "montréal",
    "montreal",
    "hors france",
    "hors-france",
    "concerne aussi",
    "cela concerne",
    "pour la france",
    "en france non",
    "annonces pour la france",
    "répertorie des annonces",
    "repertorie des annonces",
)

INTERNATIONAL_GEO_QUESTION_KEYWORDS = (
    "france",
    "belgique",
    "belge",
    "suisse",
    "canada",
    "hors france",
    "concerne aussi",
    "cela concerne",
    "répertorie",
    "repertorie",
    "annonces",
)

PRICING_ACCEPTANCE_KEYWORDS = (
    "j'accepte les tarif",
    "j accepte les tarif",
    "accepte les tarif",
    "accepte ces tarif",
    "j'accepte la tarif",
    "j accepte la tarif",
    "ok pour 1 499",
    "ok pour 1499",
    "ok pour les tarif",
    "d'accord pour les tarif",
    "d accord pour les tarif",
    "d'accord pour 1 499",
    "d accord pour 1 499",
    "je confirme et accepte",
    "je confirme les tarif",
    "confirmes les tarif",
    "accepte le tarif de 1 499",
    "accepte le tarif de 1499",
)

IMPLICIT_FREE_KEYWORDS = (
    "gratuit",
    "free",
    "sans frais",
    "sans engagement",
    "c'était gratuit",
    "c etait gratuit",
    "je pensais que c'était gratuit",
    "je pensais que c etait gratuit",
)

ACKNOWLEDGMENT_KEYWORDS = (
    "merci",
    "thanks",
    "thank you",
    "parfait",
    "top",
    "super",
    "ok",
    "d'accord",
    "d accord",
    "bien reçu",
    "bien recu",
    "noté",
    "note",
)

POLITE_PROPOSAL_ACK_KEYWORDS = (
    "proposition",
    "offre",
    "sollicitation",
    "approche",
    "votre message",
    "cette proposition",
    "votre proposition",
)

POLITE_PROPOSAL_DECLINE_KEYWORDS = (
    "non merci",
    "pas intéressé",
    "pas interesse",
    "pas pour nous",
    "ne correspond pas",
    "sans suite",
    "stop",
    "ne plus me contacter",
)


def _inbound_probe(text: str) -> str:
    trimmed = (text or "").strip()
    if not trimmed or trimmed == "(empty body)":
        return ""
    without_quoted = trimmed.split("\n>")[0].strip()
    return without_quoted.lower()


def _email_domain(email: str | None) -> str:
    normalized = (email or "").strip().lower()
    at = normalized.rfind("@")
    if at < 0:
        return ""
    return normalized[at:]


def inbound_looks_like_international_lead(text: str, email: str | None = None) -> bool:
    if INTERNATIONAL_EMAIL_TLD.search(_email_domain(email)):
        return True
    probe = _inbound_probe(text)
    if not probe:
        return False
    return any(keyword in probe for keyword in INTERNATIONAL_GEO_KEYWORDS)


def inbound_looks_like_international_geo_question(
    text: str,
    email: str | None = None,
) -> bool:
    if not inbound_looks_like_international_lead(text, email):
        return False
    probe = _inbound_probe(text)
    if "?" in probe:
        return True
    return any(keyword in probe for keyword in INTERNATIONAL_GEO_QUESTION_KEYWORDS)


def thread_mentioned_international_pricing(thread_text: str) -> bool:
    probe = (thread_text or "").lower()
    if not probe.strip():
        return False
    has_pricing = (
        "1 499" in probe
        or "1499" in probe
        or "400 usd" in probe
        or "400/mois" in probe
        or "400 / mois" in probe
    )
    if not has_pricing:
        return False
    return any(
        marker in probe
        for marker in (
            "usd",
            "belgique",
            "suisse",
            "canada",
            "international",
            "infrastructure sur mesure",
            "échange 1:1",
            "echange 1:1",
            "acceptez ces tarifications",
        )
    )


def inbound_explicitly_accepts_international_pricing(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    if any(keyword in probe for keyword in IMPLICIT_FREE_KEYWORDS):
        return False
    if any(keyword in probe for keyword in PRICING_ACCEPTANCE_KEYWORDS):
        return True
    if re.search(r"accepte.*(?:1499|1\s*499|400)", probe):
        return True
    return "j'accepte" in probe and (
        "tarif" in probe or "1499" in probe or "1 499" in probe
    )


def can_issue_international_1to1_link(
    *,
    inbound_text: str,
    thread_context: str | None = None,
) -> bool:
    if not inbound_explicitly_accepts_international_pricing(inbound_text):
        return False
    return thread_mentioned_international_pricing(thread_context or "")


def inbound_looks_like_phone_request(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    return any(keyword in probe for keyword in PHONE_REQUEST_KEYWORDS)


FRENCH_PHONE_PATTERN = re.compile(
    r"\b(?:0[1-9]|\+33[\s.]?[1-9])(?:[\s.\-]?\d{2}){4}\b"
)


def inbound_provides_phone_number(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    return bool(FRENCH_PHONE_PATTERN.search(probe))


def inbound_looks_like_scheduling_answer(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    if re.search(r"\d{1,2}\s*h", probe):
        return True
    return any(keyword in probe for keyword in SCHEDULING_ANSWER_KEYWORDS)


PARTNER_DUE_DILIGENCE_MIN_HITS = 3

PARTNER_DUE_DILIGENCE_SIGNALS = (
    "cadre réglementaire",
    "cadre reglementaire",
    "orias",
    "conseiller en investissements",
    "convention",
    "mise en relation",
    "mises en relation",
    "modèle économique",
    "modele economique",
    "précisions",
    "precisions",
    "compatible avec mon activité",
    "compatible avec mon activite",
    "responsabilité",
    "responsabilite",
    "rc pro",
    "responsabilité civile",
    "responsabilite civile",
    "conditions financières",
    "conditions financieres",
    "exclusiv",
    "rétrocession",
    "retrocession",
    "produits financiers",
    "placement des avoirs",
    "pression fiscale",
    "lettre de mission",
)


def inbound_looks_like_partner_due_diligence(text: str) -> bool:
    """Prospect is interested but sends a structured partnership questionnaire."""
    probe = _inbound_probe(text)
    if not probe:
        return False
    hits = 0
    for signal in PARTNER_DUE_DILIGENCE_SIGNALS:
        if signal in probe:
            hits += 1
            if hits >= PARTNER_DUE_DILIGENCE_MIN_HITS:
                return True
    return False


PROSPECT_QUALITY_OBJECTION_MIN_HITS = 2

PROSPECT_QUALITY_OBJECTION_SIGNALS = (
    "pappers",
    "sirene",
    "signal",
    "qualifi",
    "confirm",
    "contacté",
    "contacte",
    "nouveau cabinet",
    "expertise comptable",
    "liste froide",
    "besoin est réel",
    "besoin reel",
    "identifiés via",
    "identifies via",
    "identifié via",
    "identifie via",
)


def inbound_looks_like_prospect_quality_objection(text: str) -> bool:
    """Cabinet questions whether transmitted prospects are truly qualified (vs Pappers-only)."""
    probe = _inbound_probe(text)
    if not probe:
        return False
    hits = 0
    for signal in PROSPECT_QUALITY_OBJECTION_SIGNALS:
        if signal in probe:
            hits += 1
            if hits >= PROSPECT_QUALITY_OBJECTION_MIN_HITS:
                return True
    return False


def inbound_looks_like_question(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed or trimmed == "(empty body)":
        return False
    probe = _inbound_probe(trimmed)
    if not probe:
        return False
    if "?" in probe:
        return True
    question_keywords = (
        "comment",
        "pourquoi",
        "explique",
        "expliquer",
        "tarif",
        "mensualité",
        "mensualite",
        "combien",
        "coûte",
        "coute",
        "fonctionne",
        "lien",
        "link",
        "accès",
        "acces",
        "invitation",
    )
    if any(keyword in probe for keyword in question_keywords):
        return True
    request_phrases = (
        "je veux",
        "j'ai besoin",
        "j ai besoin",
        "pas reçu",
        "pas recu",
        "envoyez",
        "envoyer",
    )
    return any(phrase in probe for phrase in request_phrases)


def inbound_is_polite_proposal_acknowledgment(text: str) -> bool:
    """Polite thank-you for the proposal without clear yes, no, or question."""
    probe = _inbound_probe(text)
    if not probe:
        return False

    if "?" in probe:
        return False

    if (
        inbound_looks_like_question(text)
        or inbound_shows_confusion(text)
        or inbound_looks_like_phone_request(text)
        or inbound_looks_like_scheduling_answer(text)
        or inbound_requests_verification(text)
        or inbound_claims_booking_done(text)
        or inbound_shows_interest(text)
    ):
        return False

    if any(keyword in probe for keyword in POLITE_PROPOSAL_DECLINE_KEYWORDS):
        return False

    if not any(keyword in probe for keyword in ACKNOWLEDGMENT_KEYWORDS):
        return False

    if not any(keyword in probe for keyword in POLITE_PROPOSAL_ACK_KEYWORDS):
        return False

    first_line = probe.split("\n")[0].strip()
    if len(first_line) > 120:
        return False

    return True


def inbound_shows_interest(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    interest_keywords = (
        "intéressé",
        "interesse",
        "d'accord",
        "d accord",
        "je suis ouvert",
        "mon cabinet est compatible",
        "peut être intéressé",
        "peut etre interesse",
        "cela peut m'intéresser",
        "cela peut m interesser",
        "avec plaisir",
        "volontiers",
        "pour échanger",
        "pour echanger",
        "échanger sur le sujet",
        "echanger sur le sujet",
        "effectivement",
    )
    return any(keyword in probe for keyword in interest_keywords)


def inbound_claims_booking_done(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    booking_claim_keywords = (
        "j'ai réservé",
        "j ai réservé",
        "j'ai book",
        "j ai book",
        "créneau réservé",
        "creneau reserve",
        "rdv pris",
        "rendez-vous pris",
        "rendez vous pris",
        "réservation effectuée",
        "reservation effectuee",
        "j'ai pris rendez",
        "j ai pris rendez",
        "calendly confirmé",
        "calendly confirme",
        "j'ai choisi un créneau",
        "j ai choisi un creneau",
    )
    return any(keyword in probe for keyword in booking_claim_keywords)


def inbound_shows_confusion(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    confusion_keywords = (
        "pas saisi",
        "pas saisie",
        "pas compris",
        "n'ai pas compris",
        "n ai pas compris",
        "ne comprends pas",
        "je ne comprends pas",
        "n'ai pas bien compris",
        "n ai pas bien compris",
        "mal compris",
        "pas clair",
        "c'est quoi",
        "c est quoi",
        "qu'est-ce",
        "qu est-ce",
    )
    return any(keyword in probe for keyword in confusion_keywords)


def inbound_requests_verification(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    verification_keywords = (
        "identifier",
        "identité",
        "identite",
        "vérif",
        "verif",
        "coordonnées professionnelles",
        "coordonnees professionnelles",
        "qui êtes-vous",
        "qui etes-vous",
        "quelle société",
        "quelle societe",
        "origine de cette sollicitation",
        "vous représenter",
        "vous representer",
        "pas de confiance",
        "ne vous fais pas confiance",
    )
    return any(keyword in probe for keyword in verification_keywords)


def inbound_is_pure_acknowledgment(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    if "?" in probe:
        return False
    if (
        inbound_looks_like_question(text)
        or inbound_shows_confusion(text)
        or inbound_looks_like_phone_request(text)
        or inbound_looks_like_scheduling_answer(text)
        or inbound_requests_verification(text)
    ):
        return False
    first_line = probe.split("\n")[0].strip()
    if len(first_line) > 80:
        return False
    ack_keywords = (
        "merci",
        "thanks",
        "parfait",
        "top",
        "super",
        "ok",
        "bien reçu",
        "bien recu",
        "noté",
        "note",
    )
    return any(keyword in probe for keyword in ack_keywords)


def inbound_is_pure_interest_signal(text: str) -> bool:
    if not inbound_shows_interest(text):
        return False
    if inbound_looks_like_question(text):
        return False
    if inbound_shows_confusion(text):
        return False
    if inbound_looks_like_phone_request(text):
        return False
    if inbound_provides_phone_number(text):
        return False
    if inbound_looks_like_scheduling_answer(text):
        return False
    if inbound_requests_verification(text):
        return False
    if inbound_claims_booking_done(text):
        return False
    return True


def inbound_complains_partial_answer(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    return (
        "partie de mes interrogations" in probe
        or "ne répondez qu'à" in probe
        or "ne repondez qu a" in probe
        or "pas répondu à" in probe
        or "pas repondu a" in probe
        or "n'avez répondu qu'à" in probe
        or "n avez repondu qu a" in probe
        or "ça ne répond pas à ma question" in probe
        or "ca ne repond pas a ma question" in probe
    )


def inbound_calendly_person_mismatch(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    return (
        ("calendly" in probe or "annule" in probe)
        and (
            "evan" in probe
            or "pas vous" in probe
            or "quelqu'un d'autre" in probe
            or "quelqu un d autre" in probe
        )
    )


def inbound_mentions_low_associate_count(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    import re

    return bool(
        re.search(r"pas\s+3\s+collaborateurs", probe)
        or "moins de 3" in probe
        or "pas 2 collaborateurs" in probe
        or "n'ai pas 3" in probe
        or "n ai pas 3" in probe
    )


def _inbound_is_short_refusal(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe:
        return False
    first_line = probe.split("\n")[0].strip()
    import re

    return bool(
        re.match(r"^(non|nope|pas intéressé|pas interesse)\b", first_line)
        and len(first_line) < 40
    )


def inbound_needs_follow_up(text: str) -> bool:
    if _inbound_is_short_refusal(text):
        return False
    return (
        inbound_looks_like_question(text)
        or inbound_looks_like_partner_due_diligence(text)
        or inbound_looks_like_prospect_quality_objection(text)
        or inbound_looks_like_phone_request(text)
        or inbound_looks_like_scheduling_answer(text)
        or inbound_provides_phone_number(text)
        or inbound_shows_interest(text)
        or inbound_shows_confusion(text)
        or inbound_requests_verification(text)
        or inbound_is_polite_proposal_acknowledgment(text)
        or inbound_complains_partial_answer(text)
        or inbound_calendly_person_mismatch(text)
        or inbound_mentions_low_associate_count(text)
    )


def is_calendly_system_email(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe or probe == "(empty body)":
        return False
    if "calendly" not in probe:
        return (
            "accepted your invitation" in probe
            or "a accepté votre invitation" in probe
        )
    return (
        "a new event has been scheduled" in probe
        or "the event below has been canceled" in probe
        or "accepted your invitation" in probe
        or "a accepté votre invitation" in probe
        or "nouvel événement" in probe
        or "nouvel evenement" in probe
        or ("hi hercule" in probe and "event type" in probe)
    )


def is_captcha_or_bounce_email(text: str) -> bool:
    probe = _inbound_probe(text)
    if not probe or probe == "(empty body)":
        return False
    return (
        "captcha" in probe
        or "non-délivrance" in probe
        or "non-delivrance" in probe
        or "message could not be delivered" in probe
        or "delivery status notification" in probe
    )


def evaluate_post_e1_interest_gate(
    *,
    e1_sent_at: str | None,
    allow_reply: bool,
    inbound_text: str,
) -> tuple[bool, str]:
    if not e1_sent_at or not allow_reply:
        return False, ""
    if inbound_is_pure_interest_signal(inbound_text):
        return True, "Pure interest signal after E1 — E1 already sent the answer"
    return False, ""
