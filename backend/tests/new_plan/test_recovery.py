"""Private recovery, explicit external consent, grounding and usage regressions."""

from types import SimpleNamespace

import pytest
from app.contracts.learning import RecoveryDraft
from app.integrations.openai.recovery import OpenAIRecoveryGenerator

from .fixtures import headers, setup


def draft():
    """Schema-valid provider fixture with an exact synthetic evidence quote."""
    return RecoveryDraft(
        topic="Stacks",
        explanation="A stack uses last-in, first-out ordering.",
        facts=[
            {
                "text": "The last item is removed first.",
                "chunk_id": "source_0",
                "evidence_quote": "last-in, first-out",
            }
        ],
        follow_up_question="Would a worked example help?",
    )


class Responses:
    """SDK-shaped fake captures requests and simulates failures without HTTP."""

    def __init__(self, value=None):
        self.value = value or draft()
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.value, Exception):
            raise self.value
        return SimpleNamespace(
            status="completed",
            output=[],
            output_parsed=self.value,
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )


def request(client, base, user="owner", **changes):
    """Request the synthetic interval."""
    return client.post(
        base + "/recovery/jobs",
        headers=headers(user),
        json={"start_ms": 0, "end_ms": 30_000, **changes},
    )


def test_jobs_and_cards_private_even_to_session_owner():
    client, _session, base = setup()
    job = request(client, base, "s2").json()
    for suffix in [
        f"/recovery/jobs/{job['job_id']}",
        f"/recovery/cards/{job['card_id']}",
    ]:
        assert client.get(base + suffix, headers=headers()).status_code == 403
        assert client.get(base + suffix, headers=headers("s2")).status_code == 200


def test_cache_tracks_content_not_only_max_revision():
    client, session, base = setup()
    first = request(client, base).json()
    assert request(client, base).json()["cache_status"] == "hit"
    client.app.state.store.transcript_chunks[session][
        0
    ].text = "A queue uses first-in, first-out ordering."
    after = request(client, base).json()
    assert after["cache_status"] == "miss" and after["card_id"] != first["card_id"]


def test_openai_consent_minimal_payload_measured_usage_and_revocation():
    responses = Responses()
    generator = OpenAIRecoveryGenerator(
        SimpleNamespace(responses=responses), "explicit-test-model"
    )
    client, session, base = setup(generator)
    assert request(client, base).status_code == 403 and responses.calls == []
    consent = {"provider": "openai", "is_allowed": True}
    assert (
        client.put(
            base + "/external-text-consent", headers=headers(), json=consent
        ).status_code
        == 200
    )
    job = request(client, base).json()
    assert job["status"] == "completed", job
    provider_request = responses.calls[0]
    assert provider_request["store"] is False
    for forbidden in [session, "owner", "phone_visible", "Synthetic stacks"]:
        assert forbidden not in provider_request["input"]
    metrics = client.get(base + "/cost/metrics", headers=headers()).json()[0]
    assert (
        metrics["data_label"] == "measured" and metrics["input_usage"]["tokens"] == 100
    )
    client.put(
        base + "/external-text-consent",
        headers=headers(),
        json={**consent, "is_allowed": False},
    )
    assert request(client, base).status_code == 403


@pytest.mark.parametrize(
    "value",
    [
        TimeoutError("private text"),
        ValueError("private key"),
        draft().model_copy(update={"facts": []}),
    ],
)
def test_invalid_provider_responses_fail_without_sensitive_error_text(value):
    responses = Responses(value)
    client, _session, base = setup(
        OpenAIRecoveryGenerator(SimpleNamespace(responses=responses), "test")
    )
    client.put(
        base + "/external-text-consent", headers=headers(), json={"is_allowed": True}
    )
    response = request(client, base)
    assert response.json()["status"] == "failed"
    assert "private" not in response.text
