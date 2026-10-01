"""Tests for skip/limit query planner."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from query_planner import (  # noqa: E402
    QueryPlanner,
    build_slots,
    format_query,
    MAX_QUERIES_PER_REQUEST,
)


def _mini_config() -> dict:
    return {
        "KEYWORDS": ["kiné"],
        "LOCATIONS": ["Paris", "Lyon"],
        "EXPANSION_KEYWORDS": [],
        "EXPANSION_LOCATIONS": [],
        "QUERY_PLANNER_USE_DEPARTMENTS": False,
    }


def test_format_query() -> None:
    assert format_query("kiné", "Paris") == "kiné in Paris, France"


def test_build_slots_keyword_times_locations() -> None:
    slots = build_slots(_mini_config())
    assert len(slots) == 2
    assert slots[0].slot_id == 0


def test_next_batch_respects_max_queries() -> None:
    config = {
        **_mini_config(),
        "LOCATIONS": [f"City{i}" for i in range(300)],
    }
    planner = QueryPlanner.from_config(config)
    batch = planner.next_batch(MAX_QUERIES_PER_REQUEST + 50)
    assert batch is not None
    assert len(batch.queries) <= MAX_QUERIES_PER_REQUEST


def test_skip_advances_when_page_full() -> None:
    planner = QueryPlanner.from_config(_mini_config())
    batch = planner.next_batch(10)
    assert batch is not None
    planner.record_batch_result(batch, raw_places_per_query=[400, 400], limit_per_query=400)
    batch2 = planner.next_batch(10)
    assert batch2 is not None
    assert batch2.skip_places == 400


def test_slot_exhausted_when_partial_page() -> None:
    planner = QueryPlanner.from_config(_mini_config())
    batch = planner.next_batch(10)
    assert batch is not None
    planner.record_batch_result(batch, raw_places_per_query=[10, 5], limit_per_query=400)
    assert len(planner.exhausted_slots) == 2
