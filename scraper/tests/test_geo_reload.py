"""Planner exhaustion replaces legacy geo reload rounds."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from query_planner import QueryPlanner  # noqa: E402


def test_planner_exhausted_when_all_slots_done() -> None:
    config = {
        "KEYWORDS": ["a"],
        "LOCATIONS": ["Paris"],
        "QUERY_PLANNER_USE_DEPARTMENTS": False,
    }
    planner = QueryPlanner.from_config(config)
    batch = planner.next_batch(1)
    assert batch is not None
    planner.record_batch_result(batch, raw_places_per_query=[0], limit_per_query=400)
    assert planner.exhausted()
