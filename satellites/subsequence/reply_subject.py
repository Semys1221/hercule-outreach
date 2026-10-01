"""Subject line for Instantly Unibox reply sends (E1/E2/E3 threading)."""

from __future__ import annotations

import re

from typing import Literal

Flow = Literal["interested_email1", "interested_email2", "interested_email3"]

BYPASS_REPLY_SUBJECT_FALLBACK = "Re: votre message"
_RE_PREFIX = re.compile(r"^re:", re.IGNORECASE)


def _with_re_prefix(subject: str) -> str:
    trimmed = subject.strip()
    if not trimmed:
        return BYPASS_REPLY_SUBJECT_FALLBACK
    if _RE_PREFIX.match(trimmed):
        return trimmed
    return f"Re: {trimmed}"


def resolve_bypass_reply_subject(
    *,
    flow: Flow,
    thread_subject: str | None = None,
    template_subject: str | None = None,
    webhook_reply_subject: str | None = None,
) -> str:
    thread = (thread_subject or "").strip()
    template = (template_subject or "").strip()
    webhook = (webhook_reply_subject or "").strip()

    if flow == "interested_email1":
        base = webhook or thread or template
        return _with_re_prefix(base) if base else BYPASS_REPLY_SUBJECT_FALLBACK

    if thread:
        return thread
    if template:
        return _with_re_prefix(template)
    return BYPASS_REPLY_SUBJECT_FALLBACK
