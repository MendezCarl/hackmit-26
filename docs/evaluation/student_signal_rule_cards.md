# Student Signal Rule Cards

**Status:** Generated; numbers are read from the code  
**Owner:** ML and Backend teams  
**Last updated:** 2026-09-20

Each card describes one rule: what it does, its numbers, why it exists, the evidence
behind it, and how it is known to fail. Thresholds are generated from
`StudentSignalPolicy`, `VisionPolicy` and `Settings` by
`backend/scripts/generate_rule_cards.py`; a test fails if this file is stale. The evidence
and failure text is hand-written and summarizes
[the evaluation](local_vision_model_and_data.md).

**Read this first.** These rules describe what is visible: a phone in the frame, a turned
head, no face. They are heuristics tuned on three short synthetic clips plus false-alarm
counts on class recordings. They are not measurements of attention or comprehension, and
none of them has been validated on real webcam footage of real students.

## How signals are produced

```text
frame -> pretrained detectors -> per-frame flags -> rules below -> signal interval -> backend
```

Frames are sampled about every 334 ms (3.0 per second). Frames
are erased after use; only labelled intervals with a confidence leave the worker.

---

## Persistence: a condition must last

| | |
| --- | --- |
| **Rule** | A flag must stay true for at least 1 s before it becomes a signal. |
| **Numbers** | Minimum duration 1000 ms. A gap between samples longer than 2000 ms discards a candidate that is still running. |
| **Why** | A single noisy frame should never become an event. |
| **Evidence** | Covered by unit tests. No one-frame event appeared on the evaluation clips, but that is not proof it never happens on real footage. |
| **Known failure** | Real behaviors shorter than the minimum are missed: `student_d`'s second head turn (about 0.8 s) was dropped. |

## Merging: brief dropouts do not split an event

| | |
| --- | --- |
| **Rule** | If a condition stops and resumes within the merge gap, it is one interval. The interval ends at the first non-matching sample. |
| **Numbers** | Merge gap 1000 ms. |
| **Why** | Detectors drop out for a frame or two; that should not split one phone-in-hand period into pieces. |
| **Evidence** | `student_b`'s phone was two events (1.0-3.0 s and 3.7-5.7 s) and became one covering the clip. |
| **Known failure** | Two genuinely separate short events closer than the gap are joined. Events are emitted up to one merge gap after they end. |

## `phone_visible`

| | |
| --- | --- |
| **Rule** | A person is in frame and the phone score is at least the threshold. The phone search also runs on crops of the person's body, because a phone is tiny at the detector's input size. |
| **Numbers** | Phone score at least 0.4; person score at least 0.5. |
| **Why** | The threshold is the lowest value that kept false positives under 1% on about 1,900 frames of class recordings (0.7% at this value, counting a phone only while a person is present). |
| **Evidence** | Found for the whole of `student_a` and `student_b`; about a fifth of `student_d`. No phone detections on the teacher clips at this threshold. On a real laptop webcam a phone held up near the face scored 0.7-0.9 (median) and fired; in a guided run where it was probably held lower, it fired nothing. |
| **Known failure** | Recall is poor when the phone is small or held low (`student_d`). A shared tablet screen or handwriting page can still be read as a phone: the highest-scoring negatives were 0.56-0.71. |
| **Not claimed** | A visible phone does not mean distraction; phones are used for notes, chat and accessibility. It never creates a possible missed window on its own. |

## Corroboration: a phone needs a person

| | |
| --- | --- |
| **Rule** | `phone_visible` counts only in frames where a person is detected. |
| **Numbers** | Person score at least 0.5. |
| **Why** | A phone must be held by someone. Many false phone detections came from frames with nobody in them. |
| **Evidence** | Cut false-positive rates by more than half at every threshold (3.9% to 1.6% at 0.3), which allowed the lower 0.4 threshold. |
| **Known failure** | A person detected in the same frame as a phone-like object (for example a professor beside a shared tablet) still counts. |

## `head_away`

| | |
| --- | --- |
| **Rule** | A face is found and its yaw (nose offset over eye distance, from landmarks) differs from this person's own baseline by more than the threshold. |
| **Numbers** | Yaw difference above 0.7. |
| **Why** | Measuring against the person's own posture avoids flagging someone who simply sits at an angle. |
| **Evidence** | Fired on `student_d`'s first turn (yaw about 1.0-1.5 against a baseline near 0.1); not on `student_a`, who sits at an angle (yaw about 0.4). On a real webcam it fired for the first part of a turn to the side, then the face was lost (see turn continuity). |
| **Known failure** | The threshold was chosen after inspecting the same three clips, so it is not independently tested. It measures yaw only; it cannot tell looking down. |

## Head-angle baseline

| | |
| --- | --- |
| **Rule** | The baseline is the median yaw of the person's recent face-found frames. Head turn is not judged until enough frames exist. Turned frames never feed the baseline, so a long turn keeps being reported. A turn longer than the reset is taken as a new seating position. |
| **Numbers** | At least 3 face-found frames (about 1 s); window of 180 frames; reset after 60 s. |
| **Why** | Without a baseline an angled seat is a permanent false alarm; with a naive rolling baseline a long turn is absorbed and stops being reported (found and fixed by a test). |
| **Evidence** | Unit tests cover an angled person, a real turn, a 30 s turn, a turn past the reset, and camera loss discarding the baseline. |
| **Known failure** | Whoever is turned away in the first frames is treated as facing their normal direction. Slow posture drift is absorbed. |

## Turn continuity: a turned head that loses its face is still a turn

| | |
| --- | --- |
| **Rule** | If the face disappears while the person is still in frame and the last face seen was turned, the turn continues as `head_away`. It does not become `face_absent`. |
| **Numbers** | None beyond the head-turn threshold; no time limit, and the memory is cleared when the person leaves the frame or the camera is lost. |
| **Why** | The face detector only sees near-frontal faces. A real turn to the side loses the face, and the worker used to switch labels midway. |
| **Evidence** | On a real webcam (guided smoke test, look to the side) one turn was reported as three `head_away` intervals followed by two `face_absent` intervals. Unit tests cover the fix; it has not been rerun on a camera yet. |
| **Known failure** | A person who turns and then covers their face is still reported as a turn. |

## `face_absent`

| | |
| --- | --- |
| **Rule** | A person is detected but no face is found, and the last face seen was facing forward (or none was seen). |
| **Numbers** | Face score threshold 0.6 (detector). Confidence is a fixed placeholder of 0.5. |
| **Why** | Distinguishes "turned or leaning away" from "left the frame". |
| **Evidence** | Fired as the teacher left in `teacher_b` (4.7-5.7 s). |
| **Known failure** | Fires when a face is hidden by a hand, hair or low light while facing forward. Confidence is a placeholder, not a measurement. |

## `student_left_frame`

| | |
| --- | --- |
| **Rule** | No person is detected. |
| **Numbers** | Person score below 0.5. Confidence is a fixed placeholder of 0.5. |
| **Why** | Reports that the student is no longer in the camera view. |
| **Evidence** | Fired on a real webcam when the person left the camera view (87.0-101.8 s in the guided run), and stayed silent for 5 minutes of normal sitting. |
| **Known failure** | Not evaluated on real footage. A covered lens still delivers frames and is reported as this signal; only a lost camera source is reported as unavailable, with no event. |

## Backend: which signals become possible missed windows

| | |
| --- | --- |
| **Rule** | The backend marks a signal recovery-eligible only by duration. `head_away` may use a shorter minimum; `phone_visible` never qualifies alone; absence keeps the general minimum. |
| **Numbers** | General minimum 30 s. Head-away minimum: unset by default (uses the general one); 5 s when `APP_ENV=demo`, or set `MIN_HEAD_AWAY_WINDOW_MS`. Phone corroboration patterns need 20 s with looking down, or 15 s with window unfocused and face absent. |
| **Why** | "Phone alone never qualifies" is a product rule: a phone may be for notes or accessibility. |
| **Evidence** | Verified that this list is advisory: a real 5.7 s phone signal was not eligible, yet a recovery request citing it still returned a completed card. |
| **Known failure** | The worker cannot emit looking down, so the phone patterns that need it cannot be met by the worker. |

## Presenter out of frame (professor side, not validated)

| | |
| --- | --- |
| **Rule** | No person is detected in the configured presenter region for a sustained period, then a cooldown. |
| **Numbers** | Minimum duration 3000 ms; cooldown 5000 ms; person confidence at least 0.5. |
| **Why** | Lets a professor learn that a stretch of the lecture had no visible presenter. |
| **Evidence** | **None in its favor.** All four events inspected on real Zoom recordings were layout changes (speaker view, active-speaker switch, detector miss), not absences. |
| **Known failure** | Invalid on recordings whose layout changes. It is intended for the presenter's own webcam, which has not been tested. Do not present it as validated. |

## Not detected

- **Looking down.** The landmark pitch proxy separated looking down from looking ahead
  barely better than chance (AUC 0.59); the features that separated well described camera
  framing, not head angle. No rule is shipped.
- **Attention, engagement, emotion or comprehension.** Not measured, by design.
