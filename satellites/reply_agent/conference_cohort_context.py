"""Keep in sync with lib/legacy/ai-reply-agent/conference-cohort-context.ts."""

CONFERENCE_BRIEFING_WHEN = "mercredi 13 octobre à 10h (heure de Paris)"

CONFERENCE_COHORT_SEQUENCE = f"""Cohorte conférence CIF/DEC (sept. 2026) :
- Relances automatiques dans le fil Unibox existant (objet « Re: votre message ») : E1 à J+0, E2 à J+2, E3 à J+5, E4 à J+8 (pas via subsequence Instantly).
- Session collective visio : **{CONFERENCE_BRIEFING_WHEN}**.
- CTA : lien briefing collectif fourni dans le prompt ({{reservation_cif_link}} ou {{reservation_comptable_link}}) → hercule.dev/reservation-conference.html puis réservation Calendly.
- Hercule prévoit de retenir **3 cabinets** par verticale pour traiter les demandes présentées en conférence.
- Question explicite du prospect (date, profil des demandes, lien, places, fonctionnement) → should_reply true, réponse directe et chaleureuse **sans AER**.
- Accusé d'intérêt pur sans question (« Oui », « Merci », « D'accord ») juste après un email conférence automatique → should_reply false (relances E2–E4 déjà programmées).
- Opt-out explicite ou « je ne suis pas intéressé » → should_reply false."""

CONFERENCE_CIF_DEMAND_CONTEXT = (
    "Demandes visées : cabinets de **chirurgiens-dentistes** sous pression fiscale — "
    "levier typique **~50 k€** investissables, **hors Lombard** ; trésorerie et placement d'avoirs pro/privé."
)

CONFERENCE_DEC_DEMAND_CONTEXT = (
    "Demandes visées : **restaurants** en recherche d'un **accompagnement comptable stratégique** "
    "(pilotage compta/paie, rentabilité) — budget récurrent minimal **300 €/mois**."
)
