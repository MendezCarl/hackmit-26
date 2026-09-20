"""Post locally derived delivery events to the backend as the course professor.

The vision worker only prints events; nothing in the app launches it or uploads its
output. This operator tool is the explicit, consented hand-off. It sends derived
events only (never frames or boxes) and refuses non-loopback hosts unless allowed.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.contracts.learning import DeliveryBatch, DeliveryEvent

MAX_EVENTS_PER_BATCH = 50  # Matches DeliveryBatch.events max_length.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def load_events(path: Path) -> list[DeliveryEvent]:
    """Read worker output: one event per line, or runner summaries with an "events" list.

    Args:
        path: JSON Lines file written by the vision worker or run_vision_on_video.py.

    Returns:
        Validated delivery events.

    Raises:
        ValueError: If a line is not a valid delivery event; nothing is posted.
    """
    events: list[DeliveryEvent] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record: dict[str, Any] = json.loads(line)
        for item in record.get("events", [record]):
            events.append(DeliveryEvent.model_validate(item))
    return events


def post_events(
    client: httpx.Client, session_id: str, events: list[DeliveryEvent], token: str
) -> dict[str, int]:
    """Send events in bounded batches and total the backend receipts.

    Args:
        client: HTTP client whose base_url is the backend.
        session_id: Active session owned by the authenticated professor's course.
        events: Validated derived events.
        token: Professor JWT, sent only in the Authorization header.

    Returns:
        Total accepted and duplicate counts.

    Raises:
        httpx.HTTPStatusError: If the backend rejects a batch.
    """
    totals = {"accepted": 0, "duplicates": 0}
    for start in range(0, len(events), MAX_EVENTS_PER_BATCH):
        batch = DeliveryBatch(events=events[start : start + MAX_EVENTS_PER_BATCH])
        response = client.post(
            f"/api/v1/sessions/{session_id}/delivery-events/batch",
            headers={"Authorization": f"Bearer {token}"},
            json=batch.model_dump(mode="json"),
        )
        response.raise_for_status()
        receipt = response.json()
        totals["accepted"] += receipt["accepted"]
        totals["duplicates"] += receipt["duplicates"]
    return totals


def main() -> None:
    """Validate a worker output file and post it; the token comes from the environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-remote", action="store_true")
    arguments = parser.parse_args()
    token = os.environ.get("PROFESSOR_TOKEN")
    if not token:
        parser.error("Set PROFESSOR_TOKEN in the environment; tokens are never arguments.")
    if urlparse(arguments.base_url).hostname not in LOOPBACK_HOSTS and not arguments.allow_remote:
        parser.error("Use a loopback URL, or pass --allow-remote deliberately.")
    events = load_events(arguments.events_file)
    with httpx.Client(base_url=arguments.base_url, timeout=10, trust_env=False) as client:
        print(json.dumps(post_events(client, arguments.session_id, events, token)))


if __name__ == "__main__":
    main()
