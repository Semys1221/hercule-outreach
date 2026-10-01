"""Tests for agent_preview prompt assembly."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pathlib import Path

from agent_preview import (
    DEFAULT_GROK_TEMPERATURE,
    assemble_system_prompt,
    build_global_rules,
    build_knowledge_pack,
    generate_reply_preview,
    grok_temperature,
    truncate_inbound_text,
)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class BuildGlobalRulesTests(unittest.TestCase):
    def test_single_sentence(self) -> None:
        rules = build_global_rules(max_sentences=1)
        self.assertIn(
            "Maximum 1 phrase courte dans reply_text (hors signature et lien CTA).",
            rules,
        )

    def test_multiple_sentences(self) -> None:
        rules = build_global_rules(max_sentences=5)
        self.assertIn(
            "Maximum 5 phrases courtes dans reply_text (hors signature et lien CTA).",
            rules,
        )

    def test_clamps_above_ten(self) -> None:
        rules = build_global_rules(max_sentences=99)
        self.assertIn(
            "Maximum 10 phrases courtes dans reply_text (hors signature et lien CTA).",
            rules,
        )

    def test_clamps_below_one(self) -> None:
        rules = build_global_rules(max_sentences=0)
        self.assertIn(
            "Maximum 1 phrase courte dans reply_text (hors signature et lien CTA).",
            rules,
        )

    def test_requires_french_reply_text(self) -> None:
        rules = build_global_rules(max_sentences=2)
        self.assertIn("Rédige reply_text en français", rules)

    def test_includes_tone_anti_patterns(self) -> None:
        rules = build_global_rules(max_sentences=2)
        self.assertIn("urgence forcée", rules)
        self.assertIn("Merci pour votre message", rules)
        self.assertIn("Je note votre question sur notre identité", rules)
        self.assertIn("groupement d'entrepreneurs dirigé par Evan Sinclair", rules)
        self.assertNotIn("CTA urgent", rules)
        self.assertNotIn("accuser réception →", rules)

    def test_includes_recovery_and_aer_rules(self) -> None:
        rules = build_global_rules(max_sentences=2)
        self.assertIn("recovery_confidence", rules)
        self.assertIn("Structure AER", rules)
        self.assertIn("UNIQUEMENT pour les objections", rules)
        self.assertIn("mercredi 13 octobre", rules)
        self.assertIn("E4 à J+8", rules)
        self.assertIn("briefing collectif", rules)
        self.assertNotIn("ne jamais relancer", rules)

    def test_comptable_includes_conference_objection_script(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="cabinets_expertise_comptable",
        )
        lower = rules.lower()
        self.assertIn("objection conférence explicite (comptable", lower)
        self.assertIn("2 500 €", rules)
        self.assertIn("bnc/bic/tns", lower)
        self.assertIn("répondez à ce mail", lower)
        self.assertNotIn("pas d'audit 1:1", lower)

    def test_cif_includes_conference_objection_script(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="conseillers_gestion_patrimoine",
        )
        lower = rules.lower()
        self.assertIn("première réponse", lower)
        self.assertIn("objection conférence explicite (cif", lower)
        self.assertIn("2 500 €", rules)
        self.assertIn("dentistes et vétérinaires", lower)
        self.assertIn("répondez à ce mail", lower)
        self.assertIn("pas d'option 1:1", lower)
        self.assertNotIn("pas d'audit 1:1", lower)

    def test_comptable_includes_international_rules(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="cabinets_expertise_comptable",
        )
        lower = rules.lower()
        self.assertIn("international be/ch/ca (dec", lower)
        self.assertIn("1 499 usd", lower)
        self.assertIn("400 usd", lower)

    def test_cif_includes_international_rules(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="conseillers_gestion_patrimoine",
        )
        lower = rules.lower()
        self.assertIn("international be/ch/ca (ias + cif", lower)
        self.assertIn("dentistes et vétérinaires", lower)

    def test_courtiers_prevoyance_uses_ias_conference_rules(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="courtiers_prevoyance_b2b",
        )
        lower = rules.lower()
        self.assertIn("objection conférence explicite (ias", lower)
        self.assertIn("2 500 €", rules)
        self.assertIn("tns / libéraux", lower)
        self.assertIn("reservation-conference.html", lower)
        self.assertIn("international be/ch/ca", lower)

class GrokTemperatureTests(unittest.TestCase):
    def test_defaults_to_half(self) -> None:
        with patch.dict("os.environ", {"GROK_TEMPERATURE": ""}):
            self.assertEqual(grok_temperature(), DEFAULT_GROK_TEMPERATURE)

    def test_clamps_invalid_values(self) -> None:
        with patch.dict("os.environ", {"GROK_TEMPERATURE": "bad"}):
            self.assertEqual(grok_temperature(), DEFAULT_GROK_TEMPERATURE)


class AssembleSystemPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "niche_preset_id": "comptables",
            "target_type": "buyer",
            "niche_metadata": {"angle": "Comptables", "effectif_cible": "5-20"},
        }

    @patch("agent_preview.build_knowledge_pack", return_value="KNOWLEDGE")
    def test_includes_knowledge_and_campaign(self, _mock_knowledge: object) -> None:
        prompt = assemble_system_prompt(
            self.config,
            "Campaign body",
            max_sentences=3,
        )
        self.assertIn("## Pack de connaissances", prompt)
        self.assertIn("KNOWLEDGE", prompt)
        self.assertIn("## Prompt campagne", prompt)
        self.assertIn("Campaign body", prompt)
        self.assertIn(
            "Maximum 3 phrases courtes dans reply_text (hors signature et lien CTA).",
            prompt,
        )

    @patch("agent_preview.build_knowledge_pack", return_value="KNOWLEDGE")
    def test_includes_custom_directive_when_provided(self, _mock_knowledge: object) -> None:
        prompt = assemble_system_prompt(
            self.config,
            "Campaign body",
            custom_directive="Be more direct.",
        )
        self.assertIn("## Directive custom (opérateur)", prompt)
        self.assertIn("Be more direct.", prompt)

    @patch("agent_preview.build_knowledge_pack", return_value="KNOWLEDGE")
    def test_omits_empty_custom_directive(self, _mock_knowledge: object) -> None:
        prompt = assemble_system_prompt(
            self.config,
            "Campaign body",
            custom_directive="   ",
        )
        self.assertNotIn("## Directive custom (opérateur)", prompt)

    @patch("agent_preview.build_knowledge_pack", return_value="KNOWLEDGE")
    def test_includes_booking_context_when_provided(self, _mock_knowledge: object) -> None:
        prompt = assemble_system_prompt(
            self.config,
            "Campaign body",
            booking_context="Un rendez-vous Calendly a été créé automatiquement.",
        )
        self.assertIn("## Contexte Calendly (ne pas inventer)", prompt)
        self.assertIn("créé automatiquement", prompt)

    def test_comptable_system_prompt_includes_bandwidth_guidance(self) -> None:
        config = {
            "niche_preset_id": "cabinets_expertise_comptable",
            "target_type": "buyer",
            "niche_metadata": {
                "angle": "Cabinets expertise comptable",
                "effectif_cible": ">3",
            },
        }
        buyer_prompt = (
            _PROMPTS_DIR / "cabinets_expertise_comptable_buyer.md"
        ).read_text(encoding="utf-8")
        prompt = assemble_system_prompt(config, buyer_prompt, max_sentences=3)
        lower = prompt.lower()
        self.assertIn("bande passante", lower)
        self.assertIn("objection conférence", lower)
        self.assertIn("2 500 €", prompt)
        self.assertIn("je n'ai pas 3 collaborateurs", lower)


class PartnerDueDiligencePromptTests(unittest.TestCase):
    BORIS_EXCERPT = """
Bonjour, le projet peut m'intéresser. J'aurais besoin de précisions.
Quel est le cadre réglementaire ? Attendez-vous le statut CIF ou une immatriculation ORIAS ?
Qui porte la responsabilité du conseil ? Comment les mises en relation sont-elles exclusives ?
Quel est le modèle économique : commission ou rétrocession ?
"""

    def test_boris_excerpt_is_due_diligence(self) -> None:
        from inbound_question import inbound_looks_like_partner_due_diligence

        self.assertTrue(
            inbound_looks_like_partner_due_diligence(self.BORIS_EXCERPT)
        )

    def test_short_question_is_not_due_diligence(self) -> None:
        from inbound_question import inbound_looks_like_partner_due_diligence

        self.assertFalse(
            inbound_looks_like_partner_due_diligence("Quelle est votre commission ?")
        )

    PAPPERS_EXCERPT = """
Lorsque vous indiquez que les restaurants sont des prospects identifiés et qualifiés via Pappers,
pouvez-vous me confirmer qu'ils ont été contactés directement par Hercule et qu'ils ont expressément confirmé
rechercher actuellement un nouveau cabinet d'expertise comptable, et qu'il ne s'agit pas uniquement d'entreprises
identifiées à partir de signaux issus de Pappers/Sirene ?
Pouvez-vous également me communiquer le tarif HT de votre offre, sans prise de rendez-vous préalable ?
"""

    def test_pappers_excerpt_is_prospect_quality_objection(self) -> None:
        from inbound_question import inbound_looks_like_prospect_quality_objection

        self.assertTrue(
            inbound_looks_like_prospect_quality_objection(self.PAPPERS_EXCERPT)
        )

    def test_prospect_quality_rules_embed_r2(self) -> None:
        rules = build_global_rules(
            max_sentences=3,
            niche_preset_id="cabinets_expertise_comptable",
            prospect_quality_objection=True,
        )
        self.assertIn("double verrou", rules)
        self.assertIn("appel téléphonique", rules)
        self.assertIn("Interdit : reframe perception", rules)

    def test_cif_pack_contains_due_diligence_anchors(self) -> None:
        pack = build_knowledge_pack(
            {
                "niche_preset_id": "conseillers_gestion_patrimoine",
                "target_type": "buyer",
                "niche_metadata": {"angle": "CGP", "effectif_cible": "2+"},
            }
        )
        for anchor in (
            "placement des avoirs",
            "responsabilité réglementaire",
            "0 % de commission",
            "une demande, un partenaire",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, pack.lower() if anchor.islower() else pack)

    def test_assurance_pack_uses_ias_not_cif_faq(self) -> None:
        pack = build_knowledge_pack(
            {
                "niche_preset_id": "courtiers_prevoyance_b2b",
                "target_type": "buyer",
                "niche_metadata": {"angle": "IAS", "effectif_cible": ""},
            }
        )
        self.assertIn("cabinet IAS / courtier ORIAS (Buyer)", pack)
        self.assertIn("ORIAS", pack)
        self.assertIn("FAQ IAS", pack)
        self.assertNotIn("cabinet CIF (Buyer)", pack)


class TruncateInboundTests(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        self.assertEqual(truncate_inbound_text("Hello"), "Hello")

    def test_long_text_truncated(self) -> None:
        long_text = "x" * 3000
        result = truncate_inbound_text(long_text, max_chars=2000)
        self.assertEqual(len(result), 2000)
        self.assertTrue(result.endswith("…"))


class GenerateReplyPreviewTests(unittest.TestCase):
    def test_recovery_rules_apply_to_lead_tag_only(self) -> None:
        rules = build_global_rules(max_sentences=3, niche_preset_id="comptables")
        self.assertIn("Recovery (tag Lead)", rules)
        self.assertNotIn("Not interested", rules.split("Recovery")[1].split("Signature")[0])

    def test_jomega_collaborator_objection_reply_preview(self) -> None:
        config = {
            "prompt_snapshot": (
                _PROMPTS_DIR / "cabinets_expertise_comptable_buyer.md"
            ).read_text(encoding="utf-8"),
            "target_type": "buyer",
            "niche_preset_id": "cabinets_expertise_comptable",
            "niche_metadata": {},
            "max_sentences": 3,
        }
        inbound = (
            "Je n'ai pas 3 collaborateurs. Nous sommes 2 associés avec une partie "
            "sous-traités à un ami qui a aussi son cabinet. "
            "C'est donc problématique d'après ce que vous me dites.."
        )
        decision = {
            "should_reply": True,
            "reply_text": (
                "Merci pour votre message. L'enjeu est la bande passante pour "
                "intégrer des visioconférences qualifiantes, pas des appels de "
                "10 minutes, tout en assurant la production comptable.\n\n"
                "https://www.hercule.dev/reservation-entreprise.html/test\n\n"
                "Béatrice Meyer\nhercule.dev"
            ),
            "reason": "Objection éligibilité couverte par le pack connaissances.",
        }
        reserve = "https://www.hercule.dev/reservation-entreprise.html/test"
        links = {
            "primary": reserve,
            "agence_link": reserve,
            "entreprise_link": reserve,
            "comptable_link": reserve,
            "cif_link": reserve,
        }
        with (
            patch(
                "agent_preview._generate_with_models",
                return_value=(decision, "grok-test", None),
            ),
            patch("agent_preview.resolve_prompt_links", return_value=links),
        ):
            preview = generate_reply_preview(
                config,
                inbound,
                "jomega.expertise@gmail.com",
                interest_label="Interested",
            )
        self.assertTrue(preview["should_reply"])
        self.assertIn("bande passante", (preview.get("reply_text") or "").lower())
        pack = build_knowledge_pack(config)
        self.assertIn("bande passante", pack.lower())


if __name__ == "__main__":
    unittest.main()
