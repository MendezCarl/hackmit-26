"""Meta Muse recovery-card adapter through the OpenAI-compatible Responses API."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.integrations.openai.recovery import OpenAIRecoveryGenerator


class MuseRecoveryGenerator(OpenAIRecoveryGenerator):
    """Meta Muse adapter; reuses the OpenAI-compatible Responses request/validation path."""

    provider = "meta_muse"
    prompt_version = "recovery-grounded-muse-v1"

    def __init__(self, client: Any, model: str) -> None:
        """Use an explicitly configured Muse model and SDK client."""
        if not model:
            raise ValueError("An explicit Muse model is required")
        super().__init__(client, model)


def create_muse_generator(settings: Settings) -> MuseRecoveryGenerator:
    """Build the Muse generator from settings.

    Args:
        settings: Runtime settings containing the Muse API key, model, and base URL.

    Returns:
        A configured Muse recovery generator.

    Raises:
        RuntimeError: If MUSE_API_KEY is missing or the openai package is absent.
    """
    if not settings.muse_api_key:
        raise RuntimeError("LIVE_PROVIDER=meta_muse requires MUSE_API_KEY.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "LIVE_PROVIDER=meta_muse requires the openai package; install the ai extra."
        ) from exc
    return MuseRecoveryGenerator(
        OpenAI(
            base_url=settings.muse_base_url,
            api_key=settings.muse_api_key,
            timeout=20.0,
            max_retries=1,
        ),
        settings.muse_model,
    )
