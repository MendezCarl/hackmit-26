"""Request-scoped read-only tools from the AI provider plan.

No arbitrary files, SQL, URLs, media, export or mutation tools are exposed.
"""

import json
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import Field, ValidationError

from app.auth.access import SessionAccess
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import LectureInterval, StrictPayload
from app.core.errors import AppError, ErrorCode
from app.professor.ports import MetricsReader
from app.storage.in_memory import InMemoryStore
from app.transcript.repository import TimelineReader


class ToolArguments(StrictPayload):
    """Tool inputs cannot select a different actor, session, provider or course."""

    start_ms: int | None = Field(default=None, strict=True, ge=0, le=28_800_000)
    end_ms: int | None = Field(default=None, strict=True, ge=1, le=28_800_000)


class ToolCall(StrictPayload):
    """Normalized provider call; provider wire dictionaries stop at the adapter."""

    call_id: str = Field(min_length=1, max_length=128)
    name: Literal[
        "get_transcript_window",
        "get_session_metrics",
        "get_signal_events",
        "get_course_context",
        "get_recovery_history",
    ]
    arguments: ToolArguments


class CourseExcerpt(StrictPayload):
    """Approved, selected derived course text; never an arbitrary file path."""

    reference: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class CourseContextReader(Protocol):
    """Host-authorized materials lookup, scoped to the current actor and course."""

    def read(self, actor: AuthenticatedActor, course_id: str) -> list[CourseExcerpt]:
        """Return selected excerpts; raise AppError when authorization is revoked."""
        ...


class EmptyCourseContext:
    """Explicitly unavailable materials boundary for the default mocked demo."""

    def read(self, actor: AuthenticatedActor, course_id: str) -> list[CourseExcerpt]:
        """Return no material rather than inventing course content."""
        return []


@dataclass
class ToolRegistry:
    """One request's immutable authority plus bounded, validated read operations."""

    actor: AuthenticatedActor
    session_id: str
    interval: LectureInterval
    access: SessionAccess
    store: InMemoryStore
    timeline: TimelineReader
    metrics: MetricsReader
    materials: CourseContextReader = field(default_factory=EmptyCourseContext)
    maximum_output_characters: int = 24_000

    def execute(self, call: ToolCall) -> str:
        """Reauthorize every invocation; return bounded JSON or a sanitized AppError."""
        self.access.resolve_membership(self.actor, self.session_id)
        args = call.arguments
        if call.name in {"get_transcript_window", "get_signal_events"}:
            if args.start_ms is None or args.end_ms is None:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED, "A bounded interval is required."
                )
            try:
                selected = LectureInterval(start_ms=args.start_ms, end_ms=args.end_ms)
            except ValidationError:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED, "Invalid tool interval."
                ) from None
            if (
                selected.start_ms < self.interval.start_ms
                or selected.end_ms > self.interval.end_ms
            ):
                raise AppError(
                    ErrorCode.FORBIDDEN, "Tool interval exceeds the authorized request."
                )
        elif args.start_ms is not None or args.end_ms is not None:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "This tool does not accept interval filters.",
            )
        result: dict[str, object]
        if call.name == "get_transcript_window":
            window = self.timeline.read_window(
                self.session_id, selected.start_ms, selected.end_ms
            )
            result = {
                "sources": [
                    {
                        "chunk_id": c.chunk_id,
                        "start_ms": c.start_ms,
                        "end_ms": c.end_ms,
                        "text": c.text,
                    }
                    for c in window.chunks
                ]
            }
        elif call.name == "get_session_metrics":
            result = self.metrics.report(self.actor, self.session_id).model_dump(
                mode="json", exclude={"session_id"}
            )
        elif call.name == "get_signal_events":
            if self.actor.role != "student":
                raise AppError(
                    ErrorCode.FORBIDDEN,
                    "Individual signals are private to the student.",
                )
            result = {
                "intervals": [
                    {
                        "start_ms": r.event.start_ms,
                        "end_ms": r.event.end_ms,
                        "user_confirmed": r.event.user_confirmed,
                    }
                    for r in self.store.events.get(self.session_id, [])
                    if r.submitted_by == self.actor.user_id
                    and r.event.user_confirmed is not False
                    and r.event.event_type != "phone_visible"
                    and "phone_visible" not in r.event.signals
                    and r.event.start_ms < selected.end_ms
                    and selected.start_ms < r.event.end_ms
                ]
            }
        elif call.name == "get_course_context":
            course = self.store.sessions[self.session_id].course_id
            result = {
                "excerpts": [
                    m.model_dump() for m in self.materials.read(self.actor, course)[:5]
                ]
            }
        else:
            if self.actor.role != "student":
                raise AppError(
                    ErrorCode.FORBIDDEN, "Recovery history is private to its owner."
                )
            result = {
                "topics": [
                    r.card.topic
                    for r in self.store.recovery_cards.values()
                    if r.owner_user_id == self.actor.user_id
                    and r.card.session_id == self.session_id
                ][-5:]
            }
        serialized = json.dumps(result, sort_keys=True)
        if len(serialized) > self.maximum_output_characters:
            raise AppError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "Tool result exceeds the approved context limit.",
            )
        return serialized


class ToolTurn(StrictPayload):
    """Provider-neutral turn, containing calls or a final structured JSON string."""

    calls: list[ToolCall] = Field(default_factory=list, max_length=5)
    final_json: str | None = Field(default=None, max_length=8000)


class ToolModel(Protocol):
    """Provider-specific conversation state is private to one model instance."""

    def next_turn(self, results: list[tuple[str, str]]) -> ToolTurn:
        """Return the next validated turn or raise a safe provider error."""
        ...


class ToolRunner:
    """Bound rounds, cumulative output and duplicate calls across one model request."""

    def __init__(
        self, maximum_rounds: int = 3, maximum_characters: int = 32_000
    ) -> None:
        """Configure positive execution limits; invalid limits raise ValueError."""
        if not 1 <= maximum_rounds <= 5 or not 1 <= maximum_characters <= 64_000:
            raise ValueError("Invalid tool execution limits")
        self.maximum_rounds, self.maximum_characters = (
            maximum_rounds,
            maximum_characters,
        )

    def run(self, model: ToolModel, registry: ToolRegistry) -> str:
        """Return final JSON after reauthorized reads; reject cycles and mixed final/call turns."""
        results: list[tuple[str, str]] = []
        seen_ids, seen_calls = set(), set()
        size = 0
        for _ in range(self.maximum_rounds + 1):
            registry.access.resolve_membership(registry.actor, registry.session_id)
            turn = model.next_turn(results)
            if turn.final_json is not None and not turn.calls:
                try:
                    json.loads(turn.final_json)
                except ValueError:
                    raise AppError(
                        ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                        "Provider final output is not JSON.",
                    ) from None
                return turn.final_json
            if (
                turn.final_json is not None
                or not turn.calls
                or _ == self.maximum_rounds
            ):
                break
            results = []
            for call in turn.calls:
                fingerprint = call.name + call.arguments.model_dump_json()
                if call.call_id in seen_ids or fingerprint in seen_calls:
                    raise AppError(
                        ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                        "Repeated tool calls are not permitted.",
                    )
                seen_ids.add(call.call_id)
                seen_calls.add(fingerprint)
                result = registry.execute(call)
                size += len(result)
                if size > self.maximum_characters:
                    raise AppError(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        "Cumulative tool context exceeds the limit.",
                    )
                results.append((call.call_id, result))
        raise AppError(
            ErrorCode.PROVIDER_MALFORMED_OUTPUT, "The tool round limit was reached."
        )
