"""Unit tests for Instantly reply subject resolution."""

from reply_subject import BYPASS_REPLY_SUBJECT_FALLBACK, resolve_bypass_reply_subject


def test_e1_uses_webhook_subject_with_re_prefix() -> None:
    assert (
        resolve_bypass_reply_subject(
            flow="interested_email1",
            webhook_reply_subject="Question clients",
        )
        == "Re: Question clients"
    )


def test_e1_fallback_when_all_empty() -> None:
    assert (
        resolve_bypass_reply_subject(
            flow="interested_email1",
            thread_subject="",
            template_subject="",
        )
        == BYPASS_REPLY_SUBJECT_FALLBACK
    )


def test_e2_prefers_thread_subject() -> None:
    assert (
        resolve_bypass_reply_subject(
            flow="interested_email2",
            thread_subject="Re: Question clients",
            template_subject="Re: votre message",
        )
        == "Re: Question clients"
    )


def test_e3_template_fallback() -> None:
    assert (
        resolve_bypass_reply_subject(
            flow="interested_email3",
            thread_subject="",
            template_subject="Re: relance",
        )
        == "Re: relance"
    )


if __name__ == "__main__":
    test_e1_uses_webhook_subject_with_re_prefix()
    test_e1_fallback_when_all_empty()
    test_e2_prefers_thread_subject()
    test_e3_template_fallback()
    print("OK reply_subject tests passed")
