# Streamlit Reply Agent

## AI agents

Before editing this app, read:
1. [`.cursor/skills/hercule-streamlit/SKILL.md`](../../../.cursor/skills/hercule-streamlit/SKILL.md) (router)
2. [`.cursor/skills/hercule-streamlit-reply-agent/SKILL.md`](../../../.cursor/skills/hercule-streamlit-reply-agent/SKILL.md) (this app)

Human reference: sections below.

AI-assisted replies to Instantly pending leads using Grok.

## Quick start

```bash
pnpm streamlit-reply-agent
pnpm activate-reply-agents
```

## Presets

Niche presets are imported from `lib/backend/streamlit_scraper/config_loader.PRESET_LABELS`. New niches created via `python -m bootstrap create` must scaffold buyer + seller prompts in `prompts/`.

## Key areas

- **Pending replies** — fetch, preview, edit, send within send window
- **Prompts** — per-niche `*_buyer.md` and `*_seller.md` stored in Supabase via `prompt_store.py`
- **Bulk actions** — `pending_bulk_actions.py`
- **Health audit** — `pnpm audit-reply-agent` (Supabase failures + Instantly slow pending)
- **Problem tab** — failures, stale pending (>24h), recovery gate (<70%), abstentions, OOO
- **Recovery mode** — Lead tag only calls Grok; reply only if `recovery_confidence ≥ 70`. Not interested (-1) and No show (-4) are skipped without reading inbound (`reply_gate.py` / `lib/ai-reply-agent/reply-gate.ts`)
- **Reprocess skipped** — `pnpm reprocess-skipped-replies -- --campaign-id <id> --execute [--send]`
- **Opt-out global** — `pnpm stop-lead-relances -- --email=... --campaign-id=... --execute` (stop Resend, E1/E2/E3, reply agent)

## Niche CIF (`conseillers_gestion_patrimoine`)

| Rôle | Prompt | CTA |
|------|--------|-----|
| **buyer** | `prompts/conseillers_gestion_patrimoine_buyer.md` | `{reservation_cif_link}` → briefing collectif uniquement |

Knowledge pack : `app/(legacy)/content/tech/ai-reply-knowledge-cif.md` + `app/(marketing)/content/legal-documentation/cif/faq.json`.

**Recovery + AER :** toutes les réponses `should_reply=true` suivent Acknowledge → Explain → Redirect. Tag Lead uniquement : gate 70 % ; envoi réussi → retag Instantly **Interested**. Tag Not interested : pas de lecture Grok.

**Conference cutover :** `{reservation_cif_link}` → `hercule.dev/reservation-conference.html`. Objection conférence : script 2 500 € sur-mesure + clé en main en conférence + option 1:1 en répondant au mail.

Après modification des prompts :

```bash
pnpm resync-reply-agent-prompts
```

## Niche comptable (`cabinets_expertise_comptable`)

Preset principal : `cabinets_expertise_comptable_fresh_geo` (scraper VPS comptable, même campagne Instantly).

| Rôle | Cible | Prompt | CTA variable |
|------|-------|--------|--------------|
| **buyer** | Cabinet EC (> 3 associés/collaborateurs) | `prompts/cabinets_expertise_comptable_buyer.md` | `{reservation_comptable_link}` |
| **seller** | Dirigeant TPE / indépendant | `prompts/cabinets_expertise_comptable_seller.md` | `{reservation_comptable_link}` ou entreprise selon campagne |

### Knowledge pack (ground truth)

Assemblé à la volée pour Grok :

| Source | Agence | Comptable |
|--------|--------|-----------|
| Faits condensés | `doc/tech-stack/ai-reply-knowledge.md` | `doc/tech-stack/ai-reply-knowledge-comptable.md` |
| FAQ | `app/(marketing)/content/legal-documentation/entreprise/faq.json` | `app/(marketing)/content/legal-documentation/comptable/faq.json` |
| Overview | `doc/tech-stack/00-overview.md` (tronqué) | idem |

Code : `legal_content.py` (Streamlit preview) · `lib/ai-reply-agent/knowledge.ts` (webhook prod).

**Règle tarifs comptable :** renvoyer vers `https://hercule.dev/cvg/comptable` **sans chiffrer** dans l'email (exception : objection conférence → 2 500 € sur-mesure autorisé). Abstention (`should_reply=false`) si la question n'est pas couverte par le pack.

**Conference cutover :** `{reservation_comptable_link}` → `hercule.dev/reservation-conference.html`. Même script AER conférence que CIF (wording BNC/BIC/TNS).

### Flux reply (comptable)

```
Instantly reply_received
  → POST /api/webhooks/instantly/reply
  → lib/ai-reply-agent/handler.ts
  → buildKnowledgePack (preset comptable)
  → resolveLeadCtaLink (table comptable → reservation_comptable_link)
  → Grok JSON { should_reply, reply_text, reason }
  → draft ai_reply_agent_leads / auto-send si activé
  → Streamlit pending table (review manuelle)
```

Le reply agent est **distinct** de la subsequence E1–E3 (`orch-bypass`) et du booking orchestrator (`orch-booking`).

### Resync Supabase après changement de prompt

Les fichiers `prompts/*.md` ne mettent pas à jour prod tant que `prompt_snapshot` n'est pas resauvegardé :

1. Streamlit → onglet campagne comptable → **Save prompt**, ou
2. Internal → Bookings comptable → onglet **Reply agent** → enregistrer.

Sans cette étape, le webhook prod continue d'utiliser l'ancien texte en base.

### Liens utiles

- CGV cabinets : [/cvg/comptable](/cvg/comptable)
- Pricing canon : `app/(marketing)/content/legal-documentation/comptable/pricing.json` + `app/(marketing)/content/legal-documentation/comptable/cgv.md`
- Alignement site ↔ CGV : `doc/tech-stack/cvg_site-sync.md` (section comptable)
- Internal SequenceWorkspace : onglet Reply agent sous Bookings comptable

## Environment

Load API keys from repo root `.env` (Grok, Instantly, Supabase). See `config.py`.

**International 1:1 (DEC · IAS · CIF, BE/CH/CA) :** après acceptation explicite des tarifs (1 499 USD/mois · 400 USD/mois profils), le webhook génère un lien Calendly à usage unique via l'event `hercule-connect/echange-avec-dirigeant`. Env optionnelle : `CALENDLY_EVENT_TYPE_URI_INTERNATIONAL_1TO1` (défaut : URI de l'event créé le 2026-09-21). Questions Calendly à configurer dans l'UI : IAS/DEC/CIF + téléphone.
