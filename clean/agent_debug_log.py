"""NDJSON debug logs for Cursor debug sessions (no secrets / PII)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_LOG_PATH = Path("/Users/evqn/dev/hercule.dev/.cursor/debug-787d04.log")
_SESSION_ID = "787d04"


def agent_debug_log(
    location: str,
    message: str,
    data: dict[str, Any],
    hypothesis_id: str,
    *,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
