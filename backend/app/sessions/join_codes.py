"""Generation and normalization for human-typeable lecture codes."""

from __future__ import annotations

import secrets
from collections.abc import Callable

JOIN_CODE_LENGTH = 6
JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_join_code(is_taken: Callable[[str], bool]) -> str:
    """Generate one unused six-character human-typeable code.

    Args:
        is_taken: Predicate returning whether a candidate is already reserved.

    Returns:
        An unused code from ``JOIN_CODE_ALPHABET``.

    Raises:
        RuntimeError: If 100 generated candidates are already reserved.
    """
    for _ in range(100):
        code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        if not is_taken(code):
            return code
    raise RuntimeError("Could not generate an unused join code after 100 attempts.")


def normalize_join_code(raw: str) -> str:
    """Normalize user-entered join-code whitespace and casing.

    Args:
        raw: Raw code entered by a user.

    Returns:
        The trimmed uppercase code.
    """
    return raw.strip().upper()
