"""Tests for Calendly booking helper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from calendly_booking import _format_booking_context, resolve_booking_context
from inbound_question import (
    inbound_looks_like_phone_request,
    inbound_looks_like_scheduling_answer,
)


class CalendlyBookingTests(unittest.TestCase):
    def test_phone_request_detection(self) -> None:
        text = "Nous ne remplirons pas de formulaire, joignez-nous par téléphone"
        self.assertTrue(inbound_looks_like_phone_request(text))
        self.assertFalse(inbound_looks_like_scheduling_answer(text))

    def test_scheduling_answer_detection(self) -> None:
        self.assertTrue(inbound_looks_like_scheduling_answer("Je suis libre mardi 14h30"))

    def test_format_booked_context(self) -> None:
        context = _format_booking_context(
            {
                "status": "booked",
                "slotLabel": "mardi 10 septembre à 14h30",
                "rescheduleUrl": "https://calendly.com/reschedulings/RS",
            }
        )
        self.assertIn("visio Zoom", context or "")
        self.assertIn("14h30", context or "")

    @patch("calendly_booking._auto_book_enabled", return_value=True)
    @patch("calendly_booking.requests.post")
    def test_resolve_booking_context_calls_api(
        self,
        post_mock: MagicMock,
        _enabled_mock: MagicMock,
    ) -> None:
        post_mock.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "ok": True,
                "result": {
                    "status": "suggest_slots",
                    "slots": [
                        {"label": "mardi 10 septembre à 10h"},
                        {"label": "jeudi 12 septembre à 15h"},
                    ],
                },
            },
        )

        context = resolve_booking_context(
            campaign_id="camp-1",
            niche_preset_id="cabinets_expertise_comptable",
            inbound_text="Appelez-nous par téléphone",
            lead_email="cabinet@example.com",
            lead_name="Cabinet Test",
        )

        self.assertIsNotNone(context)
        self.assertIn("visio", (context or "").lower())
        post_mock.assert_called_once()
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["mode"], "suggest_slots")
        self.assertEqual(payload["event"], "comptable")

    @patch("calendly_booking.requests.post")
    def test_resolve_international_1to1_context(
        self,
        post_mock: MagicMock,
    ) -> None:
        post_mock.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "ok": True,
                "bookingContext": "Lien de planification unique (ne pas inventer) : https://calendly.com/d/abc/xyz",
            },
        )

        context = resolve_booking_context(
            campaign_id="camp-1",
            niche_preset_id="cabinets_expertise_comptable",
            inbound_text="J'accepte les tarifications.",
            lead_email="achraf@duxcompta.be",
            lead_name="Achraf",
            thread_context="Tarif Hercule 1 499 USD/mois pour la Belgique. Acceptez ces tarifications.",
        )

        self.assertIsNotNone(context)
        self.assertIn("calendly.com", (context or "").lower())
        post_mock.assert_called_once()
        payload = post_mock.call_args.kwargs["json"]
        self.assertIn("international-1to1-link", post_mock.call_args.args[0])

    @patch("calendly_booking._auto_book_enabled", return_value=False)
    def test_resolve_booking_context_disabled(self, _enabled_mock: MagicMock) -> None:
        context = resolve_booking_context(
            campaign_id="camp-1",
            niche_preset_id="cabinets_expertise_comptable",
            inbound_text="mardi 14h",
            lead_email="cabinet@example.com",
            lead_name="Cabinet",
        )
        self.assertIsNone(context)


if __name__ == "__main__":
    unittest.main()
