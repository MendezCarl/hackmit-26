"""Grounding helpers for provider-produced evidence quotes."""

from __future__ import annotations

import re
import unicodedata

_PUNCTUATION_TRANSLATIONS = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def normalize_evidence_text(text: str) -> str:
    """Normalize text for tolerant, case-insensitive evidence matching.

    Args:
        text: Evidence quote or source transcript text.

    Returns:
        NFKC-normalized, punctuation-normalized, whitespace-collapsed,
        case-folded text.
    """

    normalized = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION_TRANSLATIONS)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def is_quote_grounded(quote: str, source_text: str) -> bool:
    """Return whether a non-empty normalized quote occurs in source text.

    Args:
        quote: Provider-produced evidence quote.
        source_text: Transcript text from the cited source chunk.

    Returns:
        ``True`` when the normalized quote is a non-empty substring of the
        normalized source text; otherwise ``False``.
    """

    normalized_quote = normalize_evidence_text(quote)
    if not normalized_quote:
        return False
    return normalized_quote in normalize_evidence_text(source_text)
