"""Demo: local student signal -> backend -> student requests recovery -> grounded card.

Runs the real FastAPI app in-process with the deterministic mock generator (no OpenAI,
no network). The signal can come from a clip run through the real local models, or from
a JSON Lines file written by the student worker. The recovery request is made the way the
UI's "I missed that" action does: the student asks for an interval, citing the signal.
The 30 s eligibility rule is advisory and does not gate this request.
"""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import DEMO_HEAD_AWAY_WINDOW_MS, Settings
from app.local_ml.model_paths import MODELS_DIR, resolve_model_paths
from app.local_ml.student_signals import StudentSignal
from app.main import create_app
from scripts.post_student_signals import load_signals, post_signals

LECTURE_ID = "lecture-1"
LECTURE_OFFSET_MS = 60_000  # Where the clip's time zero falls on the lecture clock.
TRANSCRIPT = [
    (0, 60_000, "A stack follows last-in, first-out ordering."),
    (60_000, 120_000, "Pushing adds an item to the top and popping removes the top item."),
    (
        120_000,
        180_000,
        "Recursion uses the call stack to remember where each call returns.",
    ),
]


def run_demo(signals: list[StudentSignal]) -> dict[str, object]:
    """Post signals, request a recovery card for the first one, and return the results.

    Args:
        signals: Derived signals from the student worker, in clip time.

    Returns:
        The posting receipt and the recovery job and card as the API returned them.

    Raises:
        ValueError: If there are no signals to ground a request on.
    """
    if not signals:
        raise ValueError("No signals to demonstrate; run a clip that produces one.")
    settings = Settings(app_env="demo", min_head_away_window_ms=DEMO_HEAD_AWAY_WINDOW_MS)
    client = TestClient(create_app(settings))
    token = issue_access_token(
        settings, AuthenticatedActor(user_id="student-1", role="student")
    )
    headers = {"Authorization": f"Bearer {token}"}
    session_id = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": LECTURE_ID,
            "course_id": "course-1",
            "title": "Synthetic stacks lecture",
            "mode": "in_person",
        },
        headers=headers,
    ).json()["session_id"]
    client.post(
        f"/api/v1/sessions/{session_id}/transcript/batch",
        json={
            "lecture_id": LECTURE_ID,
            "chunks": [
                {
                    "chunk_id": f"chunk-{index}",
                    "session_id": session_id,
                    "start_ms": start,
                    "end_ms": end,
                    "text": text,
                    "source": "local_transcription",
                    "is_final": True,
                    "revision": 1,
                }
                for index, (start, end, text) in enumerate(TRANSCRIPT, start=1)
            ],
        },
        headers=headers,
    ).raise_for_status()
    receipt = post_signals(
        client, session_id, LECTURE_ID, signals, token, LECTURE_OFFSET_MS
    )
    first = signals[0]
    job = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={
            "start_ms": first.start_ms + LECTURE_OFFSET_MS,
            "end_ms": first.end_ms + LECTURE_OFFSET_MS,
            "source_event_ids": receipt["accepted_event_ids"][:1],
        },
        headers=headers,
    )
    job.raise_for_status()
    card = client.get(
        f"/api/v1/sessions/{session_id}/recovery/cards/{job.json()['card_id']}",
        headers=headers,
    )
    card.raise_for_status()
    return {"receipt": receipt, "job": job.json(), "card": card.json()}


def main() -> None:
    """Load signals from a clip or a file, run the demo, and print a readable summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--clip", type=Path, help="Run this clip through the local models.")
    source.add_argument(
        "--signals-file", type=Path, help="JSON Lines from the student worker."
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=MODELS_DIR,
        help="Directory with the exported person and face models (default: <repo>/models).",
    )
    arguments = parser.parse_args()
    if arguments.clip:
        from app.local_ml.student_signals import (
            OnnxStudentAnalyzer,
            StudentSignalPolicy,
            StudentSignalWorker,
        )
        from scripts.run_student_signals import analyze_clip

        person_model, face_model = resolve_model_paths(arguments.models_dir)
        analyzer = OnnxStudentAnalyzer.from_files(person_model, face_model)
        policy = StudentSignalPolicy()
        summary = analyze_clip(
            StudentSignalWorker(analyzer, policy), arguments.clip, policy.sampling_ms
        )
        signals = [StudentSignal.model_validate(s) for s in summary["signals"]]  # type: ignore[attr-defined]
    else:
        signals = load_signals(arguments.signals_file)
    for signal in signals:
        print(
            f"signal: {signal.event_type:18} {signal.start_ms / 1000:.1f}-{signal.end_ms / 1000:.1f}s confidence {signal.confidence:.2f}"
        )
    result = run_demo(signals)
    receipt, card = result["receipt"], result["card"]
    print(
        f"backend accepted {len(receipt['accepted_event_ids'])} signal(s); "  # type: ignore[index]
        f"advisory eligible list: {len(receipt['recovery_eligible_event_ids'])}"
    )  # type: ignore[index]
    print("student asks: 'I missed that'  ->  recovery job", result["job"]["status"])  # type: ignore[index]
    print(
        json.dumps(
            {
                k: card[k]
                for k in ("topic", "what_you_missed", "key_facts", "source_timestamps")
                if k in card
            },
            indent=2,
        )
    )  # type: ignore[index,union-attr]
    print(
        "(card from the deterministic mock generator, grounded in the synthetic transcript; not OpenAI)"
    )


if __name__ == "__main__":
    main()
