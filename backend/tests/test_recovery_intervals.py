"""Recovery interval-merging and cache-key composition tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.recovery.cache import build_cache_key  # noqa: E402
from app.recovery.intervals import (  # noqa: E402
    build_context_interval,
    merge_overlapping_intervals,
)


def test_merges_overlapping_intervals() -> None:
    """Overlapping intervals must merge into one."""

    merged = merge_overlapping_intervals([(0, 10), (5, 15), (20, 30)])
    assert merged == [(0, 15), (20, 30)]


def test_merges_touching_intervals() -> None:
    """Contiguous half-open intervals must merge; disjoint ones stay apart."""

    merged = merge_overlapping_intervals([(0, 10), (10, 20), (30, 40)])
    assert merged == [(0, 20), (30, 40)]


def test_merge_sorts_unsorted_input() -> None:
    """Merging must not depend on input order."""

    merged = merge_overlapping_intervals([(50, 60), (0, 10), (10, 20), (55, 65)])
    assert merged == [(0, 20), (50, 65)]


def test_merge_empty_input() -> None:
    """Merging nothing must produce nothing."""

    assert merge_overlapping_intervals([]) == []


def test_context_interval_merges_connected_source_events() -> None:
    """Source events overlapping the request must expand the window."""

    interval = build_context_interval((100, 200), [(150, 260), (900, 950)])
    assert interval == (100, 260)


def test_context_interval_ignores_distant_source_events() -> None:
    """Source events elsewhere must not expand the window."""

    interval = build_context_interval((100, 200), [(900, 950), (500, 600)])
    assert interval == (100, 200)


def test_context_interval_with_no_source_events() -> None:
    """A request without source events keeps its own interval."""

    assert build_context_interval((100, 200), []) == (100, 200)


def test_cache_key_contains_every_required_component() -> None:
    """Cache keys must cover scope, session, window, revision, and versions."""

    key = build_cache_key(
        "user-1",
        "session-1",
        0,
        60_000,
        2,
        "model-a",
        "prompt-1",
        "schema-1",
    )
    for component in (
        "scope:user-1",
        "session:session-1",
        "window:0-60000",
        "revision:2",
        "model:model-a",
        "prompt:prompt-1",
        "schema:schema-1",
    ):
        assert component in key


def test_cache_key_changes_for_every_component() -> None:
    """Changing any single component must change the cache key."""

    base = build_cache_key("user-1", "session-1", 0, 100, 1, "m", "p", "s")
    variants = (
        build_cache_key("user-2", "session-1", 0, 100, 1, "m", "p", "s"),
        build_cache_key("user-1", "session-2", 0, 100, 1, "m", "p", "s"),
        build_cache_key("user-1", "session-1", 10, 100, 1, "m", "p", "s"),
        build_cache_key("user-1", "session-1", 0, 200, 1, "m", "p", "s"),
        build_cache_key("user-1", "session-1", 0, 100, 2, "m", "p", "s"),
        build_cache_key("user-1", "session-1", 0, 100, 1, "m2", "p", "s"),
        build_cache_key("user-1", "session-1", 0, 100, 1, "m", "p2", "s"),
        build_cache_key("user-1", "session-1", 0, 100, 1, "m", "p", "s2"),
    )
    for variant in variants:
        assert variant != base
