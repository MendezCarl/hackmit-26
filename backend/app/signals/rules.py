"""Local observations support private recovery; they do not measure attention."""

from collections import Counter, defaultdict

from app.signals.models import MissedWindow, SignalEvent, SignalLabel, SignalRules


def observation_labels(event: SignalEvent) -> set[SignalLabel]:
    """Return declared labels plus the observable event type, preventing label omission.

    Args:
        event: A validated coarse event from the authorized participant.
    Returns:
        Unique observations; the derived possible-window type is not an observation.
    """
    labels = set(event.signals)
    if event.event_type != "possible_missed_window":
        labels.add(event.event_type)
    return labels


def build_phone_windows(
    events: list[SignalEvent], rules: SignalRules
) -> list[MissedWindow]:
    """Find continuous corroboration of a phone observation, using two demo rules.

    Args:
        events: Events from one participant and session; dismissal removes evidence.
        rules: Configurable durations, detector cutoff and low heuristic confidence cap.
    Returns:
        Private candidates covering only simultaneous evidence, with source IDs.
        Phone visibility alone never qualifies, even if a client calls it a window.
    """
    observations = [
        event
        for event in events
        if event.user_confirmed is not False
        and event.confidence >= rules.minimum_confidence
        and event.event_type != "student_returned"
    ]
    patterns: list[tuple[set[SignalLabel], int]] = [
        ({"phone_visible", "looking_down"}, rules.phone_looking_down_duration_ms),
        (
            {"phone_visible", "window_unfocused", "face_absent"},
            rules.phone_unfocused_absent_duration_ms,
        ),
    ]
    windows: list[MissedWindow] = []
    for labels, duration_ms in patterns:
        windows.extend(_corroborated_spans(observations, labels, duration_ms, rules))
    return windows


def _corroborated_spans(
    events: list[SignalEvent],
    required: set[SignalLabel],
    duration_ms: int,
    rules: SignalRules,
) -> list[MissedWindow]:
    """Sweep half-open intervals; gaps reset duration even within the usual merge gap.

    Args:
        events: Non-dismissed observations meeting the detector confidence cutoff.
        required: Every label that must be present simultaneously.
        duration_ms: Minimum uninterrupted overlap in milliseconds.
        rules: Supplies the conservative phone candidate confidence cap.
    Returns:
        Qualified spans with deduplicated provenance and capped heuristic confidence.
    """
    boundaries: dict[int, list[tuple[int, int]]] = defaultdict(list)
    labels_by_index = [observation_labels(event) & required for event in events]
    for index, event in enumerate(events):
        if labels_by_index[index]:
            boundaries[event.start_ms].append((index, 1))
            boundaries[event.end_ms].append((index, -1))
    counts: Counter[SignalLabel] = Counter()
    active: set[int] = set()
    contributing: set[int] = set()
    start_ms: int | None = None
    windows: list[MissedWindow] = []
    for timestamp, changes in sorted(boundaries.items()):
        entering: set[int] = set()
        for index, direction in changes:
            for label in labels_by_index[index]:
                counts[label] += direction
            if direction == 1:
                active.add(index)
                entering.add(index)
            else:
                active.remove(index)
        is_supported = all(counts[label] > 0 for label in required)
        if is_supported:
            if start_ms is None:
                start_ms = timestamp
                contributing = active.copy()
            else:
                contributing.update(entering)
        elif start_ms is not None:
            if timestamp - start_ms >= duration_ms:
                windows.append(
                    MissedWindow(
                        start_ms=start_ms,
                        end_ms=timestamp,
                        source_event_ids=sorted(
                            {events[index].event_id for index in contributing}
                        ),
                        signals=sorted(required),
                        confidence=min(
                            rules.phone_candidate_confidence_cap,
                            *(events[index].confidence for index in contributing),
                        ),
                    )
                )
            start_ms = None
    return windows
