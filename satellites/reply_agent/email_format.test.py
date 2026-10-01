"""Tests for email_format HTML link and signature rules."""

from __future__ import annotations

import unittest

from email_format import (
    BEATRICE_SIGNATURE,
    CORDIALEMENT_CLOSING,
    HERCULE_SIGNATURE_TAGLINE,
    ensure_beatrice_signature,
    format_reply_html,
    plain_text_to_html,
)


class EnsureBeatriceSignatureTests(unittest.TestCase):
    def test_appends_signature_without_site_url(self) -> None:
        result = ensure_beatrice_signature("Merci pour votre message.")
        self.assertIn(BEATRICE_SIGNATURE, result)
        self.assertIn(HERCULE_SIGNATURE_TAGLINE, result)
        self.assertNotIn("https://hercule.dev", result)
        self.assertLess(result.index(BEATRICE_SIGNATURE), result.index(HERCULE_SIGNATURE_TAGLINE))

    def test_appends_closing_after_existing_signature(self) -> None:
        body = f"Bonjour.\n\n{BEATRICE_SIGNATURE}"
        result = ensure_beatrice_signature(body)
        self.assertIn(HERCULE_SIGNATURE_TAGLINE, result)
        self.assertNotIn("https://hercule.dev", result)
        self.assertGreater(result.index(BEATRICE_SIGNATURE), 0)

    def test_normalizes_legacy_tagline_and_strips_signature_url(self) -> None:
        body = (
            f"Bonjour.\n\n{BEATRICE_SIGNATURE}\n"
            "hercule.dev Courtage contrat BNC/BIC\n"
            "https://hercule.dev"
        )
        result = ensure_beatrice_signature(body)
        self.assertIn(HERCULE_SIGNATURE_TAGLINE, result)
        self.assertNotIn("hercule.dev Courtage contrat BNC/BIC", result)
        self.assertNotIn("https://hercule.dev", result)


class FormatReplyHtmlTests(unittest.TestCase):
    def test_reservation_url_becomes_reserver_link(self) -> None:
        url = "https://www.hercule.dev/reservation.html/abc123"
        html_out = format_reply_html(
            f"Réservez ici : {url}\n\n{BEATRICE_SIGNATURE}",
        )
        self.assertIn(f'<strong><a href="{url}">Réserver</a></strong>', html_out)
        self.assertNotIn(f"Réservez ici : {url}", html_out)

    def test_hercule_site_url_becomes_hercule_dev_link(self) -> None:
        html_out = format_reply_html(
            f"Détails sur https://hercule.dev/cvg\n\n{BEATRICE_SIGNATURE}",
        )
        self.assertIn('<a href="https://hercule.dev/cvg">hercule.dev</a>', html_out)

    def test_adds_signature_when_missing(self) -> None:
        html_out = format_reply_html("Merci pour votre retour.")
        self.assertIn(BEATRICE_SIGNATURE, html_out)
        self.assertIn("Hercule, <i>Courtage contrat BNC/BIC</i>", html_out)
        self.assertIn("<i>Répondez non si vous ne souhaitez plus de messages.</i>", html_out)
        self.assertIn("Cordialement,", html_out)
        self.assertNotIn(
            '<p>Béatrice Meyer<br/>Hercule, Courtage contrat BNC/BIC<br/><a href="https://hercule.dev">',
            html_out,
        )

    def test_escapes_html_in_body(self) -> None:
        html_out = format_reply_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_appends_cta_when_missing(self) -> None:
        cta = "https://www.hercule.dev/reservation.html/slug"
        html_out = format_reply_html(
            "Merci.",
            cta_link=cta,
        )
        self.assertIn(f'<a href="{cta}">Réserver</a>', html_out)

    def test_entreprise_reservation_url(self) -> None:
        url = "https://www.hercule.dev/reservation-entreprise.html/xyz"
        html_out = format_reply_html(
            f"CTA: {url}\n\n{BEATRICE_SIGNATURE}",
        )
        self.assertIn(f'<strong><a href="{url}">Réserver</a></strong>', html_out)

    def test_comptable_tracking_url_becomes_reserver_link(self) -> None:
        url = "https://www.hercule.dev/r/comptable/slug99"
        html_out = format_reply_html(
            f"Merci. Réservez ici : {url} {BEATRICE_SIGNATURE}",
            cta_link=url,
        )
        self.assertIn(f'<strong><a href="{url}">Réserver</a></strong>', html_out)
        self.assertGreater(html_out.count("<p>"), 1)

    def test_one_liner_gets_paragraph_breaks(self) -> None:
        url = "https://www.hercule.dev/r/comptable/slug99"
        html_out = format_reply_html(
            f"Merci pour votre retour. Réservez ici : {url} {BEATRICE_SIGNATURE}",
            cta_link=url,
        )
        self.assertIn("<p>Merci pour votre retour.", html_out)
        self.assertIn(f'<strong><a href="{url}">Réserver</a></strong>', html_out)
        self.assertIn(f"<p>{BEATRICE_SIGNATURE}", html_out)

    def test_briefing_confirmation_signature_spacing(self) -> None:
        html_out = format_reply_html(
            "Je confirme votre inscription au briefing collectif du 23 septembre à 10h00.\n\n"
            "Répondez non si vous ne souhaitez plus de messages.\n\n"
            f"{BEATRICE_SIGNATURE}\n \n{HERCULE_SIGNATURE_TAGLINE}",
        )
        self.assertIn("briefing collectif du 23 septembre", html_out)
        self.assertIn(
            f"<p>{BEATRICE_SIGNATURE}<br/>Hercule, <i>Courtage contrat BNC/BIC</i></p>",
            html_out,
        )
        self.assertNotIn(f"{BEATRICE_SIGNATURE}<br/> <br/>Hercule", html_out)

    def test_cleaner_inline_site_format(self) -> None:
        html_out = format_reply_html(
            "Je note votre confirmation positive.\n\n"
            "Pour découvrir les flux qualifiés en cours et le format de collaboration "
            "n'hésitez pas à vous rendre sur notre site internet hercule.dev\n\n"
            f"{BEATRICE_SIGNATURE}",
        )
        self.assertIn(
            "collaboration n'hésitez pas à vous rendre sur notre site internet "
            '<a href="https://hercule.dev">hercule.dev</a>',
            html_out,
        )
        self.assertIn(
            "<p><i>Répondez non si vous ne souhaitez plus de messages.</i></p>",
            html_out,
        )
        self.assertIn("<p>Cordialement,</p>", html_out)
        self.assertIn(
            f"<p>{BEATRICE_SIGNATURE}<br/>Hercule, <i>Courtage contrat BNC/BIC</i></p>",
            html_out,
        )


class PlainTextToHtmlTests(unittest.TestCase):
    def test_wraps_paragraphs(self) -> None:
        html_out = plain_text_to_html("Line one\n\nLine two")
        self.assertIn("<p>Line one</p>", html_out)
        self.assertIn("<p>Line two</p>", html_out)


if __name__ == "__main__":
    unittest.main()
