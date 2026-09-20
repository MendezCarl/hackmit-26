"""Opt-in bounded tool-assisted recovery using the frozen read interfaces."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field

from app.ai.tools import (
    ToolArguments,
    ToolCall,
    ToolModel,
    ToolRegistry,
    ToolRunner,
    ToolTurn,
)
from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    GroundedFact,
    LectureInterval,
    RecoveryDraft,
    StrictPayload,
)
from app.contracts.models import ErrorResponse
from app.core.errors import AppError, ErrorCode
from app.transcript.repository import InMemoryTimelineReader


class ToolRecoveryResult(StrictPayload):
    """A validated tool-assisted draft; no permanent card or provider billing claims in mock mode."""

    draft: RecoveryDraft
    provider_mode: Literal["mock", "live"]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class SyntheticToolModel:
    """Two deterministic turns exercise actual authorization, tools and output validation."""

    def __init__(self, interval: LectureInterval) -> None:
        """Retain only the authorized request interval for this one run."""
        self.interval = interval

    def next_turn(self, results: list[tuple[str, str]]) -> ToolTurn:
        """Request context, then build an extractive synthetic draft from the result."""
        import json

        if not results:
            return ToolTurn(
                calls=[
                    ToolCall(
                        call_id="context",
                        name="get_transcript_window",
                        arguments=ToolArguments(
                            start_ms=self.interval.start_ms, end_ms=self.interval.end_ms
                        ),
                    )
                ]
            )
        sources = json.loads(results[0][1])["sources"]
        if not sources:
            raise AppError(ErrorCode.VALIDATION_FAILED, "No final transcript is available.")
        source = sources[0]
        quote = source["text"][:500]
        draft = RecoveryDraft(
            topic="Lecture recap",
            explanation=quote,
            facts=[
                GroundedFact(text=quote, chunk_id=source["chunk_id"], evidence_quote=quote)
            ],
            follow_up_question="Would another example help?",
        )
        return ToolTurn(final_json=draft.model_dump_json())


router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["recovery"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 413, 422, 502)},
)


@router.post(
    "/recovery/tool-runs",
    response_model=ToolRecoveryResult,
    description="Student JWT required. Run bounded read-only tools within the requested interval. Mock by default. Live mode requires separate provider consent; no raw media, phone observations or cross-user history is sent.",
)
def run_tools(
    session_id: str,
    interval: LectureInterval,
    request: Request,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ToolRecoveryResult:
    """Execute one bounded tool loop and verify the final draft's evidence quotes."""
    from pydantic import ValidationError

    state = request.app.state
    state.session_access.resolve_membership(actor, session_id)
    if actor.role != "student":
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Tool-assisted personal recovery is private to students.",
        )
    if interval.end_ms - interval.start_ms > 600_000:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Select at most ten minutes.")
    model: ToolModel = SyntheticToolModel(interval)
    mode: Literal["mock", "live"] = "mock"
    delegate = state.recovery_generator.delegate
    if delegate.provider == "openai":
        if (
            session_id,
            actor.user_id,
            "openai",
        ) not in state.learning_state.external_consent:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "External text processing requires provider consent.",
            )
        from app.integrations.openai.tools import OpenAIToolModel

        model = OpenAIToolModel(
            delegate.client,
            delegate.model,
            "Recover the lecture interval "
            + interval.model_dump_json()
            + ". Return JSON matching "
            + json.dumps(RecoveryDraft.model_json_schema()),
            ("get_transcript_window",),
        )
        mode = "live"
    registry = ToolRegistry(
        actor,
        session_id,
        interval,
        state.session_access,
        state.store,
        InMemoryTimelineReader(state.store),
        state.professor_metrics,
    )
    try:
        # Revocation and generation use the same lock, preventing a consent race.
        with state.learning_state.lock:
            if (
                mode == "live"
                and (session_id, actor.user_id, "openai")
                not in state.learning_state.external_consent
            ):
                raise AppError(ErrorCode.FORBIDDEN, "External text consent was revoked.")
            result = ToolRunner().run(model, registry)
        draft = RecoveryDraft.model_validate_json(result)
        chunks = {
            c.chunk_id: c
            for c in registry.timeline.read_window(
                session_id, interval.start_ms, interval.end_ms
            ).chunks
        }
        if any(
            f.chunk_id not in chunks or f.evidence_quote not in chunks[f.chunk_id].text
            for f in draft.facts
        ):
            raise ValueError("Unverifiable source")
    except (ValueError, ValidationError):
        raise AppError(
            ErrorCode.PROVIDER_MALFORMED_OUTPUT,
            "The tool-assisted recap could not be grounded.",
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return ToolRecoveryResult(
        draft=draft,
        provider_mode=mode,
        input_tokens=getattr(model, "input_tokens", None),
        output_tokens=getattr(model, "output_tokens", None),
    )
