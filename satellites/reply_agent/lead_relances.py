"""Opt-out detection and unified relance stop for reply agent scripts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

OPT_OUT_DISCLAIMER_PLAIN = "_Répondez non si vous ne souhaitez plus de messages._"
OPT_OUT_DISCLAIMER_HTML = (
    "<p><i>Répondez non si vous ne souhaitez plus de messages.</i></p>"
)
OPT_OUT_DISCLAIMER_MARKER = "Répondez non si vous ne souhaitez plus de messages"

_OPT_OUT_PATTERNS = [
    re.compile(r"\bnon\s+merci\b", re.I),
    re.compile(r"\bpas\s+int[ée]ress[ée]\b", re.I),
    re.compile(r"\bne\s+plus\s+me\s+contacter\b", re.I),
    re.compile(r"\bne\s+relancez\s+plus\b", re.I),
    re.compile(r"\bd[ée]sinscri", re.I),
    re.compile(r"\bc'?est\s+mort\b", re.I),
    re.compile(r"\bc'?est\s+bon\b", re.I),
    re.compile(r"\bstop\b", re.I),
    re.compile(r"^non[.!?\s]*$", re.I | re.M),
]
_RECOVERY_NON_MAIS = re.compile(r"\bnon\s+mais\b", re.I)


def detect_opt_out(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or _RECOVERY_NON_MAIS.search(raw):
        return False
    normalized = (
        raw.lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
    )
    return any(pattern.search(normalized) for pattern in _OPT_OUT_PATTERNS)


def stop_all_lead_relances(
    *,
    lead_email: str,
    campaign_id: str | None = None,
    reason: str = "opt-out",
    dry_run: bool = True,
) -> dict[str, object]:
    """Delegate to TS stop script for a single source of truth."""
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "crm" / "stopLeadRelances.ts"
    cmd = [
        "npx",
        "tsx",
        "--env-file",
        str(repo_root / ".env"),
        str(script),
        f"--email={lead_email.strip().lower()}",
    ]
    if campaign_id:
        cmd.append(f"--campaign-id={campaign_id}")
    if not dry_run:
        cmd.append("--execute")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "stop failed")
    import json

    return json.loads(result.stdout)
