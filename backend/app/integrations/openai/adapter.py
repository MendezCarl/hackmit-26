"""Live OpenAI adapter for grounded recovery-card generation.

Opt-in via ``PROVIDER_MODE=live`` and an ``OPENAI_API_KEY``. The adapter
requests strict JSON-schema output, validates grounding against the retrieved
transcript chunks, and rejects ungrounded or malformed provider output with
typed failures. The default test suite never imports or calls this adapter;
tests inject a fake client instead of contacting the live provider.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.contracts.models import (
    ContextWindow,
    LectureSession,
    ModelMetadata,
    RecoveryCard,
    SourceTimestamp,
)
from app.core.errors import AppError, ErrorCode

OPENAI_PROVIDER = "openai"
OPENAI_PROMPT_VERSION = "recovery-openai-v1"
OPENAI_OUTPUT_SCHEMA_VERSION = "recovery_card-1"

RECOVERY_CARD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "what_you_missed": {"type": "string"},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "example_from_lecture": {"type": ["string", "null"]},
        "follow_up_question": {"type": "string"},
        "source_timestamps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_ms": {"type": "integer"},
                    "end_ms": {"type": "integer"},
                    "chunk_id": {"type": "string"},
                },
                "required": ["start_ms", "end_ms", "chunk_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "topic",
        "what_you_missed",
        "key_facts",
        "example_from_lecture",
        "follow_up_question",
        "source_timestamps",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a compassionate lecture recovery assistant. Using ONLY the "
    "provided timestamped transcript excerpts, explain what the student "
    "likely missed in a warm, supportive way. Never invent content that is "
    "not in the excerpts. Cite every claim with source_timestamps entries "
    "whose chunk_id and millisecond ranges come from the provided excerpts."
)


class _ProviderSourceTimestamp(BaseModel):
    """One source citation required from the provider."""

    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    chunk_id: str = Field(min_length=1)

    @field_validator("end_ms")
    @classmethod
    def validate_half_open_interval(cls, value: int, info: Any) -> int:
        """Require ``0 <= start_ms < end_ms``."""

        start = info.data.get("start_ms")
        if start is not None and start >= value:
            raise ValueError("source timestamps require start_ms < end_ms.")
        return value


class ProviderRecoveryPayload(BaseModel):
    """Strict parse of the provider's structured output."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    what_you_missed: str = Field(min_length=1)
    key_facts: list[str] = Field(min_length=1)
    example_from_lecture: str | None = None
    follow_up_question: str = Field(min_length=1)
    source_timestamps: list[_ProviderSourceTimestamp] = Field(min_length=1)


class OpenAIRecoveryGenerator:
    """Live generator producing grounded cards through the OpenAI API."""

    provider = OPENAI_PROVIDER
    prompt_version = OPENAI_PROMPT_VERSION
    output_schema_version = OPENAI_OUTPUT_SCHEMA_VERSION

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        client: Any = None,
    ) -> None:
        """Bind the adapter to an API key, model, and optional client.

        Args:
            api_key: OpenAI API key; never logged or returned.
            model: Model identifier for generation.
            client: Optional pre-built client; tests inject a fake here.
        """

        self._api_key = api_key
        self.model = model
        self._injected_client = client

    def _build_client(self) -> Any:
        """Return the injected client or lazily build a real OpenAI client.

        Returns:
            A client object exposing ``chat.completions.create``.

        Raises:
            RuntimeError: When the ``openai`` package is not installed.
        """

        if self._injected_client is not None:
            return self._injected_client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "PROVIDER_MODE=live requires the openai package; install "
                "the backend with the 'live' extra."
            ) from exc
        return OpenAI(api_key=self._api_key)

    def _build_user_prompt(self, session: LectureSession, window: ContextWindow) -> str:
        """Build the bounded prompt from the selected transcript chunks.

        Args:
            session: Authorized lecture session.
            window: Retrieved context window with final chunks.

        Returns:
            The user prompt containing only the selected excerpts.
        """

        lines = [f"Lecture: {session.title}", "Transcript excerpts:"]
        for chunk in window.chunks:
            lines.append(
                f"[{chunk.chunk_id} {chunk.start_ms}-{chunk.end_ms} ms] {chunk.text}"
            )
        lines.append(
            "Explain what the student likely missed during "
            f"{window.requested_start_ms}-{window.requested_end_ms} ms."
        )
        return "\n".join(lines)

    def _parse_response_content(self, response: Any) -> str:
        """Extract the message content from a completion response.

        Args:
            response: Provider completion response object.

        Returns:
            The raw JSON string emitted by the model.

        Raises:
            AppError: ``provider_malformed_output`` when content is missing.
        """

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "Provider response was missing message content.",
            ) from exc
        if not isinstance(content, str) or not content:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "Provider response was missing message content.",
            )
        return content

    def _extract_token_counts(self, response: Any) -> tuple[int | None, int | None]:
        """Extract measured token counts from a response usage object.

        Args:
            response: Provider completion response object.

        Returns:
            Input and output token counts, or ``(None, None)`` when absent.
        """

        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None
        input_tokens = getattr(usage, "prompt_tokens", None) or getattr(
            usage, "input_tokens", None
        )
        output_tokens = getattr(usage, "completion_tokens", None) or getattr(
            usage, "output_tokens", None
        )
        return input_tokens, output_tokens

    def _validate_grounded_payload(
        self, payload: ProviderRecoveryPayload, window: ContextWindow
    ) -> None:
        """Reject provider output that is not grounded in the window.

        Args:
            payload: Parsed provider payload.
            window: Retrieved context window the card must cite.

        Raises:
            AppError: ``provider_malformed_output`` when a citation
                references an unknown chunk or timestamps outside it.
        """

        chunk_bounds = {
            chunk.chunk_id: (chunk.start_ms, chunk.end_ms) for chunk in window.chunks
        }
        for timestamp in payload.source_timestamps:
            bounds = chunk_bounds.get(timestamp.chunk_id)
            if bounds is None:
                raise AppError(
                    ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                    "Provider output cited a chunk outside the retrieved window.",
                )
            if timestamp.start_ms < bounds[0] or timestamp.end_ms > bounds[1]:
                raise AppError(
                    ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                    "Provider output cited timestamps outside its chunk.",
                )

    def generate(
        self, session: LectureSession, window: ContextWindow
    ) -> tuple[RecoveryCard, ModelMetadata]:
        """Generate one grounded card through a live provider call.

        Args:
            session: Authorized lecture session providing scope.
            window: Bounded context window with final chunks.

        Returns:
            The validated card and measured usage metadata.

        Raises:
            AppError: ``provider_timeout`` on provider timeouts and
                ``provider_refused`` on other provider errors.
        """

        started = time.perf_counter()
        client = self._build_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._build_user_prompt(session, window),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "recovery_card",
                        "strict": True,
                        "schema": RECOVERY_CARD_JSON_SCHEMA,
                    },
                },
                temperature=0.2,
            )
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower():
                raise AppError(
                    ErrorCode.PROVIDER_TIMEOUT,
                    "The provider timed out while generating the card.",
                ) from exc
            raise AppError(
                ErrorCode.PROVIDER_REFUSED,
                "The provider could not generate the card.",
            ) from exc

        content = self._parse_response_content(response)
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "Provider output was not valid JSON.",
            ) from exc
        try:
            payload = ProviderRecoveryPayload.model_validate(parsed_json)
        except ValueError as exc:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "Provider output did not match the recovery-card schema.",
            ) from exc
        self._validate_grounded_payload(payload, window)

        chunk_sources = {chunk.chunk_id: chunk.source.value for chunk in window.chunks}
        latency_ms = int((time.perf_counter() - started) * 1000)
        input_tokens, output_tokens = self._extract_token_counts(response)
        metadata = ModelMetadata(
            provider=self.provider,
            model=self.model,
            provider_mode="live",
            data_label="measured",
            prompt_version=self.prompt_version,
            output_schema_version=self.output_schema_version,
            input_character_count=sum(len(chunk.text) for chunk in window.chunks),
            output_character_count=len(content),
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            latency_ms=latency_ms,
        )
        card = RecoveryCard(
            card_id="pending",
            session_id=session.session_id,
            source_event_ids=[],
            topic=payload.topic,
            what_you_missed=payload.what_you_missed,
            key_facts=payload.key_facts,
            example_from_lecture=payload.example_from_lecture,
            source_timestamps=[
                SourceTimestamp(
                    start_ms=timestamp.start_ms,
                    end_ms=timestamp.end_ms,
                    chunk_id=timestamp.chunk_id,
                    source=chunk_sources.get(timestamp.chunk_id),
                )
                for timestamp in payload.source_timestamps
            ],
            follow_up_question=payload.follow_up_question,
            model_metadata=metadata,
            created_at="",
        )
        return card, metadata


def create_openai_generator(settings: Settings) -> OpenAIRecoveryGenerator:
    """Build the live adapter or fail fast with a clear message.

    Args:
        settings: Application settings carrying the API key and model.

    Returns:
        The configured live generator.

    Raises:
        RuntimeError: When the API key or the ``openai`` package is absent.
    """

    if not settings.openai_api_key:
        raise RuntimeError("PROVIDER_MODE=live requires OPENAI_API_KEY.")
    generator = OpenAIRecoveryGenerator(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    # Fail fast when the live extra is not installed.
    generator._build_client()  # noqa: SLF001 - guarded boot check.
    return generator
