"""Interval-merging rules for recovery context retrieval.

All intervals are half-open ``[start_ms, end_ms)`` on the shared lecture
clock. Overlapping or touching intervals within one authorized session are
merged into one context window before retrieval; they never merge across
sessions or authorization scopes.
"""

from __future__ import annotations

Interval = tuple[int, int]


def merge_overlapping_intervals(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or touching half-open intervals.

    Two intervals merge when they overlap or touch exactly (for example
    ``[0, 10)`` and ``[10, 20)`` are contiguous and merge into ``[0, 20)``).

    Args:
        intervals: Half-open ``(start_ms, end_ms)`` pairs; may be unsorted.

    Returns:
        Disjoint merged intervals sorted by start time.
    """

    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[Interval] = []
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    merged.append((current_start, current_end))
    return merged


def is_touching_or_overlapping(interval: Interval, other: Interval) -> bool:
    """Return whether two half-open intervals overlap or touch.

    Args:
        interval: First half-open interval.
        other: Second half-open interval.

    Returns:
        ``True`` when the intervals overlap or share a boundary point.
    """

    return interval[0] <= other[1] and other[0] <= interval[1]


def build_context_interval(
    requested: Interval,
    source_event_intervals: list[Interval],
) -> Interval:
    """Build the merged context interval for one recovery request.

    The requested interval is merged with every source-event interval that
    overlaps or touches it; source events elsewhere in the lecture do not
    expand the window because they belong to other missed moments.

    Args:
        requested: The requested ``(start_ms, end_ms)`` interval.
        source_event_intervals: Intervals of the signal events grounding
            this request.

    Returns:
        The single merged context interval.
    """

    connected = [
        interval
        for interval in source_event_intervals
        if is_touching_or_overlapping(interval, requested)
    ]
    merged = merge_overlapping_intervals([requested, *connected])
    # Every connected interval touches the requested one, so exactly one
    # merged interval remains.
    return merged[0]
