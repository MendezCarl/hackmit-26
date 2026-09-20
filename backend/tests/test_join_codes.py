"""Human-typeable join-code helper tests."""

import secrets

import pytest

from app.sessions.join_codes import (
    JOIN_CODE_ALPHABET,
    JOIN_CODE_LENGTH,
    generate_join_code,
    normalize_join_code,
)


def test_generate_join_code_retries_taken_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation retries until it finds an unused code."""
    candidates = iter("ABCDEF234567")
    monkeypatch.setattr(secrets, "choice", lambda _alphabet: next(candidates))

    code = generate_join_code(lambda candidate: candidate == "ABCDEF")

    assert code == "234567"
    assert len(code) == JOIN_CODE_LENGTH
    assert set(code) <= set(JOIN_CODE_ALPHABET)


def test_generate_join_code_raises_after_exhausting_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation stops after 100 taken candidates."""
    monkeypatch.setattr(secrets, "choice", lambda _alphabet: "A")

    with pytest.raises(RuntimeError, match="100 attempts"):
        generate_join_code(lambda _candidate: True)


def test_normalize_join_code_trims_and_uppercases() -> None:
    """User-entered join codes are normalized consistently."""
    assert normalize_join_code("  k7pq2m\n") == "K7PQ2M"
