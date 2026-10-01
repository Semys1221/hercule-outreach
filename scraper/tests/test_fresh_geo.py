"""Fresh geo coverage via query planner slots (no commune passes)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from query_planner import build_slots, estimate_query_count  # noqa: E402


def test_department_tier_included_by_default() -> None:
    config = {
        "KEYWORDS": ["expert comptable"],
        "LOCATIONS": ["Paris"],
        "QUERY_PLANNER_USE_DEPARTMENTS": True,
    }
    count = estimate_query_count(config)
    slots = build_slots(config)
    assert count == len(slots)
    assert any(s.tier == "department" for s in slots)
