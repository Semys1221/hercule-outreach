"""Format plain-text AI replies into HTML with Hercule link and signature rules."""

from __future__ import annotations

import html
import re
from typing import Literal

from lead_links import TargetType, resolve_lead_cta_link

HERCULE_WEBSITE_URL = "https://hercule.dev"
BEATRICE_SIGNATURE = "Béatrice Meyer"
HERCULE_SIGNATURE_TAGLINE = "Hercule, Courtage contrat BNC/BIC"
HERCULE_SIGNATURE_TAGLINE_LEGACY = "hercule.dev Courtage contrat BNC/BIC"
HERCULE_SIGNATURE_TAGLINE_SUFFIX = "Courtage contrat BNC/BIC"
HERCULE_SIGNATURE_TAGLINE_HTML = f"Hercule, <i>{HERCULE_SIGNATURE_TAGLINE_SUFFIX}</i>"
CORDIALEMENT_CLOSING = "Cordialement,"

OUTREACH_SIGNATURE_PLAIN = "\n".join(
    (CORDIALEMENT_CLOSING, BEATRICE_SIGNATURE, HERCULE_SIGNATURE_TAGLINE)
)

OPT_OUT_DISCLAIMER_PLAIN = "Répondez non si vous ne souhaitez plus de messages."
OPT_OUT_DISCLAIMER_HTML = (
    "<p><i>Répondez non si vous ne souhaitez plus de messages.</i></p>"
)
OPT_OUT_DISCLAIMER_MARKER = "Répondez non si vous ne souhaitez plus de messages"

_RESERVATION_PATH_RE = re.compile(
    r"reservation(?:-entreprise)?\.html|/r/comptable/",
    re.I,
)
_URL_RE = re.compile(
    r"https?://[^\s<>]+|(?:www\.)?hercule\.dev[/\w\-.?=&%]*",
    re.I,
)
_HTTPS_ONLY_URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
_HERCULE_URL_RE = re.compile(
    r"https?://(?:www\.)?hercule\.dev(?:/[^\s]*)?",
    re.I,
)


def _normalize_plain_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _has_reservation_url(text: str) -> bool:
    return bool(_RESERVATION_PATH_RE.search(text))


def _is_reservation_url(url: str) -> bool:
    return bool(_RESERVATION_PATH_RE.search(url))


def _is_hercule_site_url(url: str) -> bool:
    return "hercule.dev" in url.lower() and not _is_reservation_url(url)


def _normalize_url(url: str) -> str:
    cleaned = url.strip().rstrip(".,;)")
    if cleaned.lower().startswith("www."):
        return f"https://{cleaned}"
    if "hercule.dev" in cleaned.lower() and not cleaned.lower().startswith("http"):
        return f"https://{cleaned.lstrip('/')}"
    return cleaned


def _signature_index(text: str) -> int:
    for marker in (BEATRICE_SIGNATURE, "Beatrice Meyer"):
        idx = text.rfind(marker)
        if idx >= 0:
            return idx
    return -1


def _has_explicit_hercule_url(text: str) -> bool:
    return bool(_HERCULE_URL_RE.search(text))


def _normalize_signature_spacing(text: str) -> str:
    """Collapse blank lines between name and tagline in the outreach signature block."""
    out = text
    for marker in (BEATRICE_SIGNATURE, "Beatrice Meyer"):
        pattern = (
            rf"({re.escape(marker)})(?:[ \t]*\n[ \t]*)+"
            rf"({re.escape(HERCULE_SIGNATURE_TAGLINE)})"
        )
        out = re.sub(pattern, r"\1\n\2", out)
    return out


def _structure_reply_plaintext(text: str) -> str:
    """Insert paragraph breaks before signature, CTA URLs, and site link."""
    body = _normalize_plain_text(text)
    if not body:
        return body

    for marker in (BEATRICE_SIGNATURE, "Beatrice Meyer"):
        body = re.sub(
            rf"([^\n])\s+({re.escape(marker)})",
            rf"\1\n\n\2",
            body,
            count=1,
        )

    url_pattern = _URL_RE.pattern
    body = re.sub(
        rf"([.!?:])\s+({url_pattern})",
        r"\1\n\n\2",
        body,
        flags=re.I,
    )
    body = re.sub(
        rf"(ici\s*:\s*)({url_pattern})",
        r"\1\n\2",
        body,
        flags=re.I,
    )

    idx = _signature_index(body)
    if idx >= 0:
        for marker in (BEATRICE_SIGNATURE, "Beatrice Meyer"):
            if body[idx:].startswith(marker):
                sig_end = idx + len(marker)
                rest = body[sig_end:]
                stripped = rest.lstrip()
                if stripped and not rest.startswith("\n"):
                    body = f"{body[:sig_end]}\n{stripped}"
                break

    return body.strip()


def _normalize_legacy_signature_tagline(text: str) -> str:
    return text.replace(HERCULE_SIGNATURE_TAGLINE_LEGACY, HERCULE_SIGNATURE_TAGLINE)


def _strip_trailing_signature_site_url(text: str) -> str:
    idx = _signature_index(text)
    if idx < 0:
        return text
    signature_block = text[idx:]
    trimmed = re.sub(
        r"\nhttps?://(?:www\.)?hercule\.dev/?\s*$",
        "",
        signature_block,
        flags=re.I,
    )
    if trimmed == signature_block:
        return text
    return f"{text[:idx]}{trimmed}".rstrip()


def ensure_outreach_signature(text: str) -> str:
    """Ensure reply closing: Cordialement, name, tagline (no trailing site URL)."""
    body = _strip_trailing_signature_site_url(_normalize_legacy_signature_tagline(text))
    if _signature_index(body) < 0:
        body = f"{body.rstrip()}\n\n{BEATRICE_SIGNATURE}"

    idx = _signature_index(body)
    before_signature = body[:idx].rstrip()
    after_signature = body[idx:]
    if HERCULE_SIGNATURE_TAGLINE not in after_signature:
        body = f"{before_signature}\n\n{BEATRICE_SIGNATURE}\n{HERCULE_SIGNATURE_TAGLINE}"

    return _strip_trailing_signature_site_url(body)


def ensure_cordialement_closing(text: str) -> str:
    if CORDIALEMENT_CLOSING in text:
        return text
    idx = _signature_index(text)
    if idx < 0:
        return f"{text.rstrip()}\n\n{CORDIALEMENT_CLOSING}\n\n{BEATRICE_SIGNATURE}"
    prefix = text[:idx].rstrip()
    signature_and_after = text[idx:]
    return f"{prefix}\n\n{CORDIALEMENT_CLOSING}\n\n{signature_and_after}"


def ensure_beatrice_signature(text: str) -> str:
    """Deprecated alias for ensure_outreach_signature."""
    return ensure_outreach_signature(text)


def ensure_cta_present(text: str, cta_link: str) -> str:
    """Append reservation CTA URL when missing from the body."""
    if not cta_link.strip():
        return text
    if cta_link in text or _has_reservation_url(text):
        return text
    return f"{text.rstrip()}\n\nRéservez un créneau ici : {cta_link}"


def _anchor_for_url(url: str) -> str:
    normalized = _normalize_url(url)
    escaped_href = html.escape(normalized, quote=True)
    if _is_reservation_url(url):
        return f'<strong><a href="{escaped_href}">Réserver</a></strong>'
    if _is_hercule_site_url(url) or "hercule.dev" in url.lower():
        return f'<a href="{escaped_href}">hercule.dev</a>'
    escaped_url = html.escape(url, quote=False)
    return f'<a href="{escaped_href}">{escaped_url}</a>'


def _linkify_plain_segment(plain: str, *, https_only: bool = False) -> str:
    parts: list[str] = []
    last = 0
    pattern = _HTTPS_ONLY_URL_RE if https_only else _URL_RE
    for match in pattern.finditer(plain):
        start, end = match.span()
        if start > last:
            parts.append(html.escape(plain[last:start], quote=False))
        parts.append(_anchor_for_url(match.group(0)))
        last = end
    if last < len(plain):
        parts.append(html.escape(plain[last:], quote=False))
    return "".join(parts)


def _plain_to_linked_html(plain: str) -> str:
    idx = _signature_index(plain)
    if idx < 0:
        return _linkify_plain_segment(plain)
    before = _linkify_plain_segment(plain[:idx])
    signature_block = _linkify_plain_segment(plain[idx:], https_only=True)
    return before + signature_block


def _emphasize_reply_linked_text(linked: str) -> str:
    out = linked
    if "<i>Répondez non" not in out:
        out = out.replace(
            OPT_OUT_DISCLAIMER_PLAIN,
            f"<i>{OPT_OUT_DISCLAIMER_PLAIN}</i>",
        )
    out = out.replace(HERCULE_SIGNATURE_TAGLINE, HERCULE_SIGNATURE_TAGLINE_HTML)
    out = out.replace(HERCULE_SIGNATURE_TAGLINE_LEGACY, HERCULE_SIGNATURE_TAGLINE_HTML)
    return out


def _paragraphs_from_linked_text(linked: str) -> str:
    blocks = [block for block in linked.split("\n\n") if block.strip()]
    paragraphs: list[str] = []
    for block in blocks:
        inner = block.replace("\n", "<br/>")
        paragraphs.append(f"<p>{inner}</p>")
    return "".join(paragraphs)


def plain_text_to_html(text: str) -> str:
    """Legacy escape-only HTML wrapper (no link formatting)."""
    escaped = html.escape(text, quote=False)
    return _paragraphs_from_linked_text(escaped)


def _normalize_legacy_disclaimer(text: str) -> str:
    return text.replace(
        "_Répondez non si vous ne souhaitez plus de messages._",
        OPT_OUT_DISCLAIMER_PLAIN,
    )


def format_reply_html(
    text: str,
    *,
    lead_email: str | None = None,
    target_type: TargetType | None = None,
    cta_link: str | None = None,
) -> str:
    """Convert plain reply text to HTML with Réserver / hercule.dev anchors."""
    body = _normalize_plain_text(_normalize_legacy_disclaimer(text))
    if not body:
        body = BEATRICE_SIGNATURE

    resolved_cta = (cta_link or "").strip()
    if not resolved_cta and lead_email and target_type:
        resolved_cta = resolve_lead_cta_link(lead_email, target_type)
    if resolved_cta:
        body = ensure_cta_present(body, resolved_cta)

    body = ensure_outreach_signature(body)
    if OPT_OUT_DISCLAIMER_MARKER not in body:
        cord_idx = body.find(CORDIALEMENT_CLOSING)
        sig_idx = _signature_index(body)
        insert_idx = cord_idx if cord_idx >= 0 else sig_idx
        if insert_idx >= 0:
            body = (
                f"{body[:insert_idx].rstrip()}\n\n{OPT_OUT_DISCLAIMER_PLAIN}\n\n"
                f"{body[insert_idx:]}"
            )
        else:
            body = f"{body}\n\n{OPT_OUT_DISCLAIMER_PLAIN}"
    body = ensure_cordialement_closing(body)
    body = _normalize_signature_spacing(body)
    body = _structure_reply_plaintext(body)
    linked = _plain_to_linked_html(body)
    if OPT_OUT_DISCLAIMER_MARKER not in linked:
        sig_idx = linked.find(BEATRICE_SIGNATURE)
        if sig_idx >= 0:
            linked = f"{linked[:sig_idx]}{OPT_OUT_DISCLAIMER_HTML}{linked[sig_idx:]}"
        else:
            linked = f"{linked}{OPT_OUT_DISCLAIMER_HTML}"
    linked = _emphasize_reply_linked_text(linked)
    html_out = _paragraphs_from_linked_text(linked)
    # #region agent log
    try:
        import json
        import time
        import urllib.request

        payload = json.dumps(
            {
                "sessionId": "a778c7",
                "runId": "post-fix-signature-spacing",
                "hypothesisId": "F-G-H",
                "location": "email_format.py:format_reply_html",
                "message": "reply html emphasis applied",
                "data": {
                    "has_italic_disclaimer": "<i>Répondez non" in html_out,
                    "has_italic_tagline": "<i>Courtage contrat BNC/BIC</i>" in html_out,
                    "has_double_br_in_signature": f"{BEATRICE_SIGNATURE}<br/> <br/>Hercule" in html_out,
                    "has_bold_cta": "<strong><a href=" in html_out and ">Réserver</a></strong>" in html_out,
                    "html_preview": html_out[:400],
                },
                "timestamp": int(time.time() * 1000),
            }
        ).encode()
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:7849/ingest/172cb84e-a8e1-4d83-b273-2b61310f5e7d",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Debug-Session-Id": "a778c7",
                },
                method="POST",
            ),
            timeout=2,
        )
    except Exception:
        pass
    # #endregion
    return html_out
