"""Unit tests for tolerant but grounded evidence matching."""

from app.recovery.evidence_matching import (
    is_quote_grounded,
    normalize_evidence_text,
)


def test_normalize_evidence_text_handles_curly_quotes_and_dashes() -> None:
    """Curly punctuation is normalized to the corresponding ASCII forms."""

    assert (
        normalize_evidence_text("A ‘student’s’ path – from “input”")
        == "a 'student's' path - from \"input\""
    )


def test_normalize_evidence_text_collapses_whitespace_and_casefolds() -> None:
    """Whitespace variants and case differences do not affect normalization."""

    assert normalize_evidence_text("  A\tSTACK\nuses  ") == "a stack uses"


def test_is_quote_grounded_accepts_normalized_substrings() -> None:
    """Formatting differences still match the cited transcript source."""

    assert is_quote_grounded(
        " a student’s stack uses last-in - first-out ",
        "A student's stack uses last-in – first-out ordering.",
    )


def test_is_quote_grounded_rejects_empty_quote() -> None:
    """An empty or whitespace-only quote cannot establish grounding."""

    assert not is_quote_grounded(" \t\n ", "The source contains text.")


def test_is_quote_grounded_rejects_non_matching_quote() -> None:
    """A normalized quote absent from the source remains invalid."""

    assert not is_quote_grounded("a queue uses first-in first-out", "A stack uses LIFO.")
