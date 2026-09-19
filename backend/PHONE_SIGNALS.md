# Optional phone observations

Status: Implemented on the isolated feature branches

Owner: Backend team

Last updated: 2026-09-19

`phone_visible` means **a phone appeared in the camera frame**. It says nothing
about attention or comprehension. A phone may support class participation,
notes, chat, or accessibility. Detection stays on the device; this change adds
no detector, image upload, raw audio upload, or media endpoint.

## Ingestion contract

POST `/api/v1/sessions/{session_id}/events/batch` (`/signals` remains an alias).
Bearer session membership and signal consent are required. Participant identity
comes from authentication: `student_id` and other caller-selected identities are
rejected. Example using synthetic identifiers and lecture-relative milliseconds:

```json
{
  "events": [{
    "event_id": "phone-observation-1",
    "lecture_id": "lecture_123",
    "event_type": "phone_visible",
    "start_ms": 240000,
    "end_ms": 260000,
    "signals": ["phone_visible"],
    "confidence": 0.82,
    "source": "local_yolo",
    "user_confirmed": null
  }]
}
```

The authenticated session must belong to `lecture_123` and cover that interval.
The demo session is only 60 seconds; use its lecture ID and shorter timestamps.
`source` is optional for compatibility and accepts `local_yolo`,
`local_mediapipe`, `local_opencv`, `local_client`, or `user_report`.
It is a client-supplied provenance label, not proof of which detector ran.
`confidence` measures confidence in the observation, not missed content.

Event types: `face_absent`, `head_away`, `looking_down`, `window_unfocused`,
`phone_visible`, `student_left_frame`, `student_returned`,
`user_marked_confused`, and `possible_missed_window`.
Use `looking_down` for the proposed head-down observation and `face_absent`
for no-face observations. Return/self-report markers still require a positive
half-open interval, e.g. `[240000, 240001)`.

## Private recovery rules

| Observations | Default behavior |
| --- | --- |
| Phone alone, including a 3-second observation | No possible missed window |
| Phone plus looking down | Candidate after 20 seconds of continuous overlap |
| Phone plus window unfocused plus face absent | Phone-supported candidate after 15 seconds of continuous overlap |
| Looking down alone or student returned | No automatic candidate |
| User marked confused | Explicit recovery candidate; no detector threshold required |

The two phone patterns work with separate events or bundled `signals`.
Evidence must belong to the same authenticated participant/session. Every
observation must meet the configurable detector cutoff (default 0.5).
Dismissed observations are excluded. Exact threshold duration qualifies; any
gap resets the duration. Duplicates and out-of-order arrival cannot accumulate
extra time. Candidates retain source event IDs and actual overlap intervals.

Phone-only events remain insufficient even when labeled `possible_missed_window`
or confirmed. For an explicit request without corroboration, use
`user_marked_confused`. Existing confirmation of non-phone candidates is preserved.
`student_returned` is a passive marker; it does not retroactively truncate other
event intervals. Producers must send accurate absence end times.

`SignalRules.phone_looking_down_duration_ms`,
`phone_unfocused_absent_duration_ms`, and `phone_candidate_confidence_cap`
configure the new behavior. Phone-supported candidates have an uncalibrated
heuristic confidence capped at 0.5 by default; the detector's original 0.82 stays
unchanged. These are demo heuristics, not validated measurements of attention.
Existing independent face/head/window/left-frame rules still apply; they can
produce a candidate earlier without phone evidence. Merging qualifying candidates
preserves the strongest independent confidence and deduplicates source IDs.

## Professor privacy and integration

Professor aggregation excludes phone events and every bundle containing
`phone_visible`, even confirmed bundles. Return markers also do not contribute.
Phone observations cannot change professor signal ratios or suggested actions.
Independent non-phone events retain existing aggregation rules. No phone labels,
detector names, confidence, event IDs, or participant identities reach professors.
Reports retain threshold suppression and compassionate language such as
“Some students may have missed context during this interval.”

The private timeline exposes candidates to the host recovery pipeline. Recovery
card generation remains a separate feature; this change does not add it.
No new dependencies or live provider calls are needed.

Signal logic/tests live in `feature/backend-signal-timeline`; the aggregation
privacy guard/tests live in `feature/backend-professor-aggregation`. Shared signal
DTOs are synchronized across the isolated worktrees to prevent merge divergence.
The combined checkout retains both changes for integration testing.
Generated JSON Schema and OpenAPI snapshots include the new payload fields.
Frontend files remain unchanged; external contract review is still required
before integration. See the feature runbook for branch ownership and checks.
