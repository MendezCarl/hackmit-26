"""Transparent, input-only cost illustration for the synthetic judge demo."""

from typing import Literal

from pydantic import Field

from app.contracts.learning import StrictPayload
from app.contracts.models import CostMetrics, RecoveryCard, TranscriptChunk

CHARACTERS_PER_ESTIMATED_TOKEN = 4
ILLUSTRATIVE_INPUT_USD_PER_MILLION = 1.0


class DemoCostComparison(StrictPayload):
    """Compare fixture text sizes without claiming measured provider savings.

    Tokens use a character heuristic, not a model tokenizer. Dollar values use
    a deliberately hypothetical rate, exclude prompts/output, and are not bills.
    """

    data_label: Literal["synthetic_estimate"] = "synthetic_estimate"
    baseline_method: Literal["all_final_fixture_transcript_text"] = (
        "all_final_fixture_transcript_text"
    )
    estimation_method: Literal["ceil_unicode_characters_div_4"] = (
        "ceil_unicode_characters_div_4"
    )
    scope: Literal["transcript_input_only_excludes_prompt_metadata_and_output"] = (
        "transcript_input_only_excludes_prompt_metadata_and_output"
    )
    pricing_basis: Literal["hypothetical_not_provider_pricing"] = (
        "hypothetical_not_provider_pricing"
    )
    illustrative_input_usd_per_million_tokens: float = Field(default=1.0, ge=1, le=1)
    full_transcript_characters: int = Field(ge=0)
    selected_context_characters: int = Field(ge=0)
    full_transcript_estimated_tokens: int = Field(ge=0)
    selected_context_estimated_tokens: int = Field(ge=0)
    estimated_input_reduction_ratio: float = Field(ge=0, le=1)
    full_transcript_illustrative_input_usd: float = Field(ge=0)
    selected_context_illustrative_input_usd: float = Field(ge=0)
    illustrative_input_reduction_usd: float = Field(ge=0)
    mock_generation_calls: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    generation_calls_avoided: int = Field(ge=0)
    provider_api_calls: Literal[0] = 0
    measured_input_tokens: None = None
    measured_output_tokens: None = None
    measured_savings_usd: None = None


def estimate_transcript_tokens(character_count: int) -> int:
    """Estimate transcript tokens with an explicit character-count heuristic.

    Args:
        character_count: Number of Unicode characters, excluding prompt metadata.

    Returns:
        The count rounded up after dividing by four; zero for empty text.

    Raises:
        ValueError: If the character count is negative.
    """
    if character_count < 0:
        raise ValueError("Character counts cannot be negative.")
    return (
        character_count + CHARACTERS_PER_ESTIMATED_TOKEN - 1
    ) // CHARACTERS_PER_ESTIMATED_TOKEN


def compare_context_cost(
    chunks: list[TranscriptChunk], card: RecoveryCard, usage: list[CostMetrics]
) -> DemoCostComparison:
    """Compare final fixture text with the card's exact selected source set.

    Args:
        chunks: Full synthetic final transcript from this run.
        card: Successful mock card identifying selected chunks.
        usage: This session's mock ledger, including the repeated cache request.

    Returns:
        Explicit heuristic tokens, hypothetical dollars and observed mock reuse.

    Raises:
        ValueError: If sources are missing or measured/live usage is supplied.
    """
    final = {chunk.chunk_id: chunk for chunk in chunks if chunk.is_final}
    selected = {source.chunk_id for source in card.source_timestamps}
    if not selected or not selected <= final.keys():
        raise ValueError("The demo comparison requires valid transcript sources.")
    if card.model_metadata.provider_mode != "mock" or any(
        entry.provider_mode != "mock"
        or entry.data_label != "synthetic"
        or entry.session_id != card.session_id
        for entry in usage
    ):
        raise ValueError("The demo comparison accepts synthetic mock usage only.")
    full_characters = sum(len(chunk.text) for chunk in final.values())
    selected_characters = sum(len(final[key].text) for key in selected if key is not None)
    full_tokens = estimate_transcript_tokens(full_characters)
    selected_tokens = estimate_transcript_tokens(selected_characters)
    rate = ILLUSTRATIVE_INPUT_USD_PER_MILLION / 1_000_000
    cache_hits = sum(entry.cache_status == "hit" for entry in usage)
    return DemoCostComparison(
        full_transcript_characters=full_characters,
        selected_context_characters=selected_characters,
        full_transcript_estimated_tokens=full_tokens,
        selected_context_estimated_tokens=selected_tokens,
        estimated_input_reduction_ratio=(full_tokens - selected_tokens) / full_tokens
        if full_tokens
        else 0.0,
        full_transcript_illustrative_input_usd=round(full_tokens * rate, 8),
        selected_context_illustrative_input_usd=round(selected_tokens * rate, 8),
        illustrative_input_reduction_usd=round((full_tokens - selected_tokens) * rate, 8),
        mock_generation_calls=sum(entry.cache_status == "miss" for entry in usage),
        cache_hits=cache_hits,
        generation_calls_avoided=cache_hits,
    )
