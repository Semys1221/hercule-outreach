"""Sync Instantly bypass bootstrap defaults into coded source files."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_TEMPLATES_PATH = Path(__file__).resolve().parent / "default_templates.py"


def sync_e1_bootstrap_default(
    body_html: str,
    *,
    path: Path | None = None,
) -> None:
    if '"""' in body_html:
        raise ValueError("Body cannot contain triple double-quotes")

    target = path or DEFAULT_TEMPLATES_PATH
    content = target.read_text(encoding="utf-8")
    replacement = f'COMPTABLE_E1_BODY_HTML = """{body_html}"""\n'
    patterns = (
        re.compile(r'COMPTABLE_E1_BODY_HTML = """[\s\S]*?"""\n'),
        re.compile(r"DEFAULT_E1_BODY_HTML = \([\s\S]*?\)\n"),
        re.compile(r'DEFAULT_E1_BODY_HTML = """[\s\S]*?"""\n'),
    )
    new_content = content
    count = 0
    for pattern in patterns:
        new_content, count = pattern.subn(replacement, new_content, count=1)
        if count == 1:
            break
    if count != 1:
        raise ValueError("Could not find COMPTABLE_E1_BODY_HTML in default_templates.py")
    target.write_text(new_content, encoding="utf-8")
