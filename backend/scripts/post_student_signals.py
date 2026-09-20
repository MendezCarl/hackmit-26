"""Post locally derived student signals to the backend as the authenticated student.

Nothing in the app launches the student worker or uploads its output. This operator
tool is the explicit, consented hand-off: it sends derived labelled intervals only
(never frames or boxes), authenticates with a token from the environment, and refuses
non-loopback hosts unless allowed. Identity comes from the token, not the payload.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.contracts.models import IngestEventsRequest, SignalEvent
from app.local_ml.student_signals import StudentSignal
from scripts.post_delivery_events import LOOPBACK_HOSTS

MAX_EVENTS_PER_BATCH = 50  # Matches the backend's default max_batch_events.


def load_signals(path: Path) -> list[StudentSignal]:
    """Read worker output: one signal per line, or run_student_signals summaries.

    Args:
        path: JSON Lines file from the student worker or ``run_student_signals``.

    Returns:
        Validated derived signals.

    Raises:
        ValueError: If a line is not a valid signal; nothing is posted.
    """
    signals: list[StudentSignal] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record: dict[str, Any] = json.loads(line)
        for item in record.get("signals", [record]) if "clip" in record else [record]:
            signals.append(StudentSignal.model_validate(item))
    return signals


def post_signals(
    client: httpx.Client,
    session_id: str,
    lecture_id: str,
    signals: list[StudentSignal],
    token: str,
    offset_ms: int = 0,
) -> dict[str, list[str]]:
    """Send signals in bounded batches and collect the backend's receipts.

    Args:
        client: HTTP client whose base_url is the backend.
        session_id: Session the authenticated student belongs to.
        lecture_id: Lecture the session belongs to; the backend validates it.
        signals: Validated derived signals.
        token: Student JWT, sent only in the Authorization header.
        offset_ms: Added to every timestamp to align a clip with the lecture clock.

    Returns:
        Accepted and recovery-eligible event ids across all batches.

    Raises:
        httpx.HTTPStatusError: If the backend rejects a batch.
    """
    totals: dict[str, list[str]] = {
        "accepted_event_ids": [],
        "recovery_eligible_event_ids": [],
    }
    for start in range(0, len(signals), MAX_EVENTS_PER_BATCH):
        request = IngestEventsRequest(
            lecture_id=lecture_id,
            events=[
                SignalEvent(
                    session_id=session_id,
                    **{
                        **signal.model_dump(mode="json"),
                        "start_ms": signal.start_ms + offset_ms,
                        "end_ms": signal.end_ms + offset_ms,
                    },
                )
                for signal in signals[start : start + MAX_EVENTS_PER_BATCH]
            ],
        )
        response = client.post(
            f"/api/v1/sessions/{session_id}/events/batch",
            headers={"Authorization": f"Bearer {token}"},
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        receipt = response.json()
        for key in totals:
            totals[key] += receipt[key]
    return totals


def main() -> None:
    """Validate worker output and post it; the token comes from the environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signals_file", type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--offset-ms", type=int, default=0)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-remote", action="store_true")
    arguments = parser.parse_args()
    token = os.environ.get("STUDENT_TOKEN")
    if not token:
        parser.error("Set STUDENT_TOKEN in the environment; tokens are never arguments.")
    if (
        urlparse(arguments.base_url).hostname not in LOOPBACK_HOSTS
        and not arguments.allow_remote
    ):
        parser.error("Use a loopback URL, or pass --allow-remote deliberately.")
    signals = load_signals(arguments.signals_file)
    with httpx.Client(base_url=arguments.base_url, timeout=10, trust_env=False) as client:
        print(
            json.dumps(
                post_signals(
                    client,
                    arguments.session_id,
                    arguments.lecture_id,
                    signals,
                    token,
                    arguments.offset_ms,
                )
            )
        )


if __name__ == "__main__":
    main()
