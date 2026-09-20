"""Strict coarse-signal payloads; raw media and caller-supplied identity are forbidden."""

from typing import Annotated, Literal

from pydantic import Field

from app.timeline.contracts import Identifier, Interval, StrictModel

SignalLabel = Literal[
    "face_absent",
    "head_away",
    "looking_down",
    "window_unfocused",
    "phone_visible",
    "student_left_frame",
    "student_returned",
    "user_marked_confused",
]


class SignalEvent(Interval):
    """A possible missed-content signal, never a measurement of attention."""

    event_id: Identifier
    lecture_id: Identifier
    event_type: Literal[
        "possible_missed_window",
        "face_absent",
        "head_away",
        "looking_down",
        "window_unfocused",
        "phone_visible",
        "student_left_frame",
        "student_returned",
        "user_marked_confused",
    ]
    signals: Annotated[list[SignalLabel], Field(min_length=1, max_length=8)]
    confidence: Annotated[
        float,
        Field(
            ge=0,
            le=1,
            description="Confidence in the observation, not attention or comprehension.",
        ),
    ]
    user_confirmed: bool | None = None
    source: (
        Literal[
            "local_yolo",
            "local_mediapipe",
            "local_opencv",
            "local_client",
            "user_report",
        ]
        | None
    ) = Field(
        default=None,
        description="Optional local producer label; conveys no identity or authorization. phone_visible only means a phone appeared in the camera frame.",
    )


class SignalBatch(StrictModel):
    """At most 100 derived signal events for the URL's authorized session."""

    events: Annotated[list[SignalEvent], Field(min_length=1, max_length=100)]


class SignalFeedback(StrictModel):
    """The student may confirm or dismiss a possible missed-content window."""

    user_confirmed: Annotated[bool, Field(strict=True)]


class StoredSignal(StrictModel):
    """Private storage envelope; participant identity is never in public responses."""

    participant_key: Identifier
    original: SignalEvent
    event: SignalEvent


class MissedWindow(Interval):
    """Derived interval eligible for recovery, with editable supporting signals."""

    event_type: Literal["possible_missed_window"] = "possible_missed_window"
    source_event_ids: list[Identifier]
    signals: list[SignalLabel]
    confidence: float = Field(
        description="Uncalibrated recovery heuristic, never an attention score or probability of missed content."
    )


class SignalRules(StrictModel):
    """Configurable demo heuristics; these are not validated attention thresholds."""

    minimum_duration_ms: Annotated[int, Field(strict=True, gt=0)] = 5000
    minimum_confidence: Annotated[float, Field(ge=0, le=1)] = 0.5
    merge_gap_ms: Annotated[int, Field(strict=True, ge=0)] = 1000
    phone_looking_down_duration_ms: Annotated[int, Field(strict=True, gt=0)] = 20_000
    phone_unfocused_absent_duration_ms: Annotated[int, Field(strict=True, gt=0)] = 15_000
    phone_candidate_confidence_cap: Annotated[float, Field(ge=0, le=1)] = 0.5
