# Local Vision Model, Data, and Attribution

**Status:** Draft; evaluated on consented recordings and short synthetic clips  
**Owner:** ML and Backend teams  
**Last updated:** 2026-09-20

This document records what the local vision pipeline uses, where every external
component came from, what was and was not trained, and how it was evaluated. It
supports the attribution requirement for open-source code and pretrained models.

## Summary

- **No neural network was trained.** The detectors are pretrained, publicly released
  models used unchanged. Two things were fitted from data: a hand-set phone-score threshold
  (Threshold calibration) and, as an experiment, a small logistic-regression classifier over
  the detectors' outputs (Trained phone classifier). The classifier did not clearly beat the
  threshold and is not used by the worker. The project's own contributions are the temporal
  rules, the privacy-preserving event contract, the export, calibration, training and
  evaluation tools, and the backend integration.
- **The classifier trains on derived numbers only.** It sees detector scores and normalized
  geometry, never pixels. The videos are otherwise used to evaluate the detectors and choose
  rule thresholds. Too little labelled data exists to
  train a network that would generalize (three unique six-second student clips).
- **The approved person detector is committed for the Electron app.** Evaluation
  videos remain under `data/local/` and are never committed.

## How the pipeline works

```text
video frame -> [1] pretrained detector -> [2] hand-written temporal rules -> [3] derived event
```

1. **Detector (pretrained, frozen).** SSDLite320 with a MobileNetV3-Large backbone
   detects COCO object classes. The worker keeps only `person`.
2. **Temporal rules (project code).** `VisionWorker` in
   `backend/app/local_ml/vision.py` converts per-frame detections into events. A
   condition must persist for `minimum_duration_ms` (default 3000) and respects a
   cooldown (default 5000 ms). These thresholds are tunable heuristics, not learned values.
3. **Derived event (project contract).** Only `DeliveryEvent` records leave the
   worker. They contain no frames, boxes, faces, or identities.

## In-app student drift detection

The Electron renderer captures camera frames only after explicit student consent.
ONNX Runtime Web preprocesses and runs the approved person detector in the renderer;
raw frames, canvases, and detection rows never leave the device. The renderer sends
only derived `phone_visible` and `student_left_frame` `SignalEvent` records to the
local backend, where they can support a compassionate recovery-card prompt. These
signals describe possible missed content and do not prove attention, focus, or
comprehension.

The committed artifact is `frontend/models/person_detector.onnx` with manifest
`frontend/models/person_detector.manifest.json`; its SHA-256 is
`558b5f9013a792225ade2e22fcd07811fbe177cc942bb5a465b9718c3aedcdbe`.

## External components and attribution

| Component | Use | License | Reference |
| --- | --- | --- | --- |
| torchvision `ssdlite320_mobilenet_v3_large`, `COCO_V1` weights | Pretrained person detector | BSD-3-Clause (code). Weights are trained on COCO; confirm terms before any redistribution | [torchvision SSDlite docs](https://pytorch.org/vision/stable/models/ssdlite.html); weights fetched from `download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth` |
| SSD architecture | Detector design | Research paper | Liu et al., "SSD: Single Shot MultiBox Detector", ECCV 2016. [arXiv:1512.02325](https://arxiv.org/abs/1512.02325) |
| SSDLite / MobileNetV2 | Lightweight detection head | Research paper | Sandler et al., "MobileNetV2: Inverted Residuals and Linear Bottlenecks", CVPR 2018. [arXiv:1801.04381](https://arxiv.org/abs/1801.04381) |
| MobileNetV3 | Backbone | Research paper | Howard et al., "Searching for MobileNetV3", ICCV 2019. [arXiv:1905.02244](https://arxiv.org/abs/1905.02244) |
| COCO dataset | Data the detector was pretrained on (not used directly by this project) | Annotations CC BY 4.0; images carry their original Flickr licenses | Lin et al., "Microsoft COCO: Common Objects in Context", ECCV 2014. [arXiv:1405.0312](https://arxiv.org/abs/1405.0312) |
| PyTorch | One-time model export only; not an application dependency | BSD-style | Paszke et al., "PyTorch: An Imperative Style, High-Performance Deep Learning Library", NeurIPS 2019. [arXiv:1912.01703](https://arxiv.org/abs/1912.01703) |
| ONNX Runtime Web | CPU inference in the Electron renderer | MIT | [onnxruntime.ai](https://onnxruntime.ai) |
| OpenCV | Frame decoding, resizing, region analysis | Apache-2.0 | [opencv.org](https://opencv.org) |
| YuNet face detector (`face_detection_yunet_2023mar.onnx`, 232,589 bytes, sha256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`) | Face box and 5 landmarks for the student head-turn signal | MIT per the OpenCV Zoo model listing (verify) | Wu et al., "YuNet: A Tiny Millisecond-level Face Detector", Machine Intelligence Research, 2023; model from [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), run through OpenCV `FaceDetectorYN` |
| certifi | CA bundle used once so the weight download could verify TLS | MPL-2.0 | [pypi.org/project/certifi](https://pypi.org/project/certifi/) |

Licenses in this table were recorded from the projects' public descriptions and
have not been legally reviewed. Verify them before redistributing any model file.

## Model provenance

- Export tool: `backend/scripts/export_person_detector.py`. It wraps the detector so
  the ONNX output is `Nx6` rows of normalized `x1, y1, x2, y2, score, class`.
- Artifact: `models/person_detector.onnx`, 14,218,221 bytes, opset 17, input
  `[1, 3, 320, 320]` float RGB.
- SHA-256: `558b5f9013a792225ade2e22fcd07811fbe177cc942bb5a465b9718c3aedcdbe`.
- Manifest: `models/person_detector.manifest.json`, with `is_approved: true` set by
  the operator for local evaluation only.
- Person class id is 1 in torchvision's 91-index COCO scheme. The same model also
  emits `cell phone` (class 77), which the worker currently discards.

## Evaluation data

The evaluation videos are Zoom class recordings supplied by the team, who
state they hold consent for their use. They are stored locally under
`data/local/` and are never committed or uploaded.

| Group | Count | Resolution | Total length | Use |
| --- | --- | --- | --- | --- |
| Professor (`profs`) | 14 | 600x360 or 640x360 | about 1,114 minutes | Presenter-tile evaluation |
| Student (`student`) | 5 | 640x342 to 854x480 | about 222 minutes | Robustness on gallery layouts |

- Layout: in most recordings the professor is a small tile at the top right beside a
  shared screen, so the runner crops `x 0.72-1.00, y 0.00-0.30`. Layouts are not stable,
  though: recordings switch to speaker view, full-screen sharing, or another
  participant's tile. See the presenter results below.
- Two professor files (`videoplayback (1).mp4` and `(2).mp4`) produced identical
  results and are probably duplicate downloads.
- Files named `YTSave_YouTube_...` were downloaded from YouTube through a
  third-party service. Their YouTube video ids, taken from the file names, are:
  professor group `pIU9fyiR-Fg`, `G-Co8U5dXzI`, `hbax9pm42N4`, `k0mTO8mb_sQ`;
  student group `JpTDF4w-6Yc`, `uWTDkG1w-cY`, `aIC3V4iqi4_`, `YKz5c46HXE8`,
  `i-w2sxYTQbc`. The `videoplayback*.mp4` files carry no source id. Confirm the
  original uploaders' terms before sharing any output beyond aggregate statistics.

## Method

`backend/scripts/run_vision_on_video.py` decodes each video in memory, crops the
presenter tile, and passes it to the real `VisionWorker`, which erases each frame
after use. No frame is written to disk. The `balanced` profile samples about 3
frames per second. Output is one JSON summary per video: sampled frames,
presenter-present ratio, and derived `presenter_out_of_frame` events.

## Results

### Finding: layout changes, not absences

A first run cropped a fixed top-right tile and produced many `presenter_out_of_frame`
events (for example 36 in one 79-minute video). A manual check of 6 randomly sampled
events, viewed at each interval midpoint, showed no presenter in the tile crop in all
6. The full frame was inspected for 3 of them, and in all 3 the recording had
switched to full-screen sharing (the shared page filled the whole video), so the
presenter's camera was simply not shown. The other 3 were not inspected beyond the
crop. The detector was correct that no person was visible, but the label "out of
frame" was wrong for the 3 confirmed cases.

Fix: the runner now treats a mostly near-black or near-white tile as *unavailable*
(`is_tile_visible`) and clears candidates instead of emitting an event, following
the rule in the detection architecture that a disappearing source is reported as
unavailable. After this change the same video gives 0 events in its first 40 minutes,
and a second video (Review session 3) gives 0 events with 42% of samples unavailable.

The sample was small (6 events, 1 video) and the fix has not been validated on a
real absence, because none has been located in the footage. The events above no
longer fire, but the recall of the rule for a genuine absence is **unknown**.

### Presenter statistics (14 professor recordings, about 1,114 minutes)

"Tile unavailable" is the share of samples where the crop was near-black or near-white
and was therefore not analyzed. Presence is over analyzed samples only.

| Video | Minutes | Tile unavailable | Presenter present | Events |
| --- | --- | --- | --- | --- |
| Lecture 14 | 40.8 | 0% | 0.976 | 1 |
| Lecture 17 | 39.5 | 0% | 0.960 | 1 |
| Review session 3 | 116.5 | 53% | 0.979 | 1 |
| Review session 4 | 75.4 | 0% | 0.992 | 1 |
| `videoplayback (1)` | 79.3 | 4% | 0.998 | 1 |
| `videoplayback (2)` (duplicate of 1) | 79.3 | 4% | 0.998 | 1 |
| `videoplayback (3)` | 83.3 | 1% | 0.997 | 1 |
| `videoplayback (4)` | 78.9 | 8% | 0.971 | 5 |
| `videoplayback (5)` | 129.9 | 6% | 0.997 | 2 |
| `videoplayback (6)` | 80.0 | 100% | n/a | 0 |
| `videoplayback (7)` | 77.5 | 4% | 0.982 | 1 |
| `videoplayback (8)` | 77.3 | 100% | n/a | 0 |
| `videoplayback (9)` | 79.6 | 74% | 0.952 | 0 |
| `videoplayback` | 76.4 | 3% | 0.997 | 2 |

The 17 events are not evidence of presenters leaving. Four of the 17 were inspected at
the full frame, and **all four were false alarms**: two were speaker view with the
professor filling the frame (Lecture 14 at 0-58 s, `videoplayback (7)` at 1273 s),
one was the professor's tile on screen while looking down and missed by the detector
(`videoplayback (4)` at 3651 s), and one was a tile showing a different participant
after an active-speaker switch (`videoplayback` at 2725 s). Thirteen events were not
inspected. Several start at 0 s, which may be recording start-up.

**Conclusion:** a fixed-position crop is not a valid presenter-absence detector for
Zoom recordings, because their layout changes. The worker is designed to read the
presenter's own webcam (`cv2.VideoCapture`), a stable single-person view. The
recordings are therefore a poor test distribution for it. They remain useful for
throughput and for showing how layout changes cause false alarms.

Inference latency measured on the exported model: median 8.5 ms and p95 11.5 ms per
frame on an Apple-silicon laptop CPU (30 sampled frames), against the design
budget of 200 ms p95.

### Synthetic webcam-style clips (student phone, head turn, teacher leaving)

Six clips were generated from text prompts and supplied by the team (the generator
tool and its terms are not recorded here; add them). One student clip was a
byte-identical duplicate and was removed, leaving 3 student clips and 2 teacher
clips. Each is 5.9 s at 1366x768, 24 fps. They are AI-generated, so they may differ
from real webcam footage. `backend/scripts/evaluate_clip_signals.py` samples about 4
frames per second in memory and reports per-clip signal fractions.

Ground truth is the author's visual reading of an 8-frame contact sheet per clip and is
approximate (about +/-0.7 s). A phone is in hand for the whole clip in all three
student clips. The teacher leaves between about 3.5 s and 5.2 s in both teacher clips.
Frame fractions at the calibrated phone threshold of 0.5:

| Clip | Person present | Phone visible | Face found | Head turned |
| --- | --- | --- | --- | --- |
| `student_a` | 1.00 | 1.00 | 1.00 | 0.00 |
| `student_b` | 1.00 | 0.92 | 1.00 | 0.00 |
| `student_d` | 1.00 | 0.04 | 1.00 | 0.33 |
| `teacher_a` | 0.92 | 0.00 | 0.83 | 0.04 |
| `teacher_b` | 0.96 | 0.00 | 0.79 | 0.04 |

Findings:

- **Phone.** The pretrained `cell phone` class found the phone in nearly every sample for
  `student_a` and `student_b`, but almost never for `student_d` (4%). Searching the whole
  frame alone was much worse (4% for `student_b`), because a phone is a few pixels wide at
  the 320x320 detector input. Running the detector on crops of the person's body fixed
  `student_b`. The teacher clips gave no phone detections at 0.5.
- **Head turn.** A yaw proxy from YuNet landmarks (nose offset over eye distance)
  reached about 1.0-1.5 while `student_d` turned aside, against baselines under 0.5.
  The threshold of 0.7 was chosen after inspecting these same clips, so this result is
  not independent. `student_a` sits at a constant angle (yaw about 0.4), so a fixed
  threshold needs a per-user baseline.
- **Looking down.** Not solved and not emitted. The landmark pitch proxy did not separate
  looking at a phone from looking ahead, since a face is still found in every student frame.
- **Teacher leaving.** The face disappears from about 4.8 s in both clips. The person
  detector keeps reporting a person until about 5.2 s in `teacher_a` and through the
  end of `teacher_b` (a partial body at the edge). Face loss is the earlier and more
  accurate cue.
- **Clips are too short to test the event rules.** Presenter absence lasts about 1 s
  against a 3 s minimum, and the backend's phone patterns need 15-20 s.

### Threshold calibration (the fitted part)

`backend/scripts/calibrate_phone_threshold.py` chooses the phone-score threshold. Positives
are the 72 sampled frames of the three student clips. Negatives are 1,921 frames: every
sampled frame of the two teacher clips plus one frame per minute of the professor and
student class recordings (24 sources). The threshold is the lowest grid value whose
false-positive rate on the negatives is at most 1%. The positives are not used to choose
it, so their recall at that threshold is an out-of-sample estimate, though a small one.

| Threshold | Recall (a / b / d) | False-positive rate |
| --- | --- | --- |
| 0.30 | 100% / 100% / 38% | 3.9% |
| 0.40 | 100% / 100% / 21% | 2.2% |
| **0.50 (chosen)** | 100% / 92% / 4% | 0.8% |
| 0.60 | 96% / 25% / 0% | 0.3% |

Caveats: the negatives assume no phone is present, which is unverified. The five highest
scoring negatives (0.61-0.71) were inspected in four frames, and none showed a phone;
they look like a shared tablet screen or handwriting page being read as a phone. That
makes the negatives a harder test than a single-person webcam. The negative set contains
duplicates (the two identical professor downloads and one recording present in both
folders).

### Trained phone classifier (experiment, not adopted)

`backend/scripts/train_phone_classifier.py` trains a class-balanced, L2-regularized logistic
regression in plain numpy (no new dependency) on features from
`OnnxStudentAnalyzer.extract_features`: phone scores (whole frame and body crops), face score,
head-angle proxies, and framing geometry. It is evaluated leave-one-positive-clip-out: each
student clip is held out in turn while negative sources are split across the same three
folds, and the decision threshold is chosen on training data only (false-positive rate at most
1%). Every figure below is on data the model did not train on.

Data: 72 positive frames (three student clips) and 79 negative frames from 18 sources: the
two teacher clips plus one frame per 15 s of the real recordings, **kept only where a face
at least as large as in the student clips is visible** (height at least 0.209 of the frame).
That matching stops the model from separating classes by "close-up webcam" versus "screen
share". The negatives assume no phone is present, which is unverified.

| Method | Held-out recall (a / b / d) | False-positive rate on held-out negatives (a / b / d) |
| --- | --- | --- |
| Rule: phone score at least 0.5 | 100% / 92% / 4% | 0% / 0% / 0% |
| Trained, behaviour features only | 100% / 100% / 33% | 12% / 0% / 0% |
| Trained, all features | 100% / 100% / 50% | 50% / 0% / 0% |

Mean held-out recall is 0.65 for the rule, 0.78 for behaviour-only, and 0.83 for all features.

Reading it honestly:

- The trained model finds much more of the phone in the hard clip (`student_d`), which the rule
  nearly misses.
- It also produces false alarms the rule does not (12% and 50% on the `student_a` fold), even
  though its threshold was set for 1% on the training negatives. That gap means the 1% target
  did not transfer, which is expected from only 79 negatives.
- Each fold has 22-34 held-out negatives and 24 held-out positives from one clip, so none of
  these differences is statistically reliable.
- Adding framing features (all features) made false alarms worse, which suggests it partly
  learns camera placement, so behaviour-only is the safer variant.

Decision: the worker keeps the hand-set rule. A final behaviour-only model trained on all rows
is saved locally as `models/phone_classifier.json` (gitignored, threshold 0.63) for
experimentation, but it has no held-out validation of its own and is not loaded by any code.
More consented clips with the phone away, from more people, are the data that would change
this decision. Four unit tests cover the numpy training code on synthetic clusters.

### Student signal worker

`backend/app/local_ml/student_signals.py` turns per-frame scores into coarse derived events.
`OnnxStudentAnalyzer` verifies both models (operator approval, size and SHA-256), then
computes person, phone and face scores per frame. `StudentSignalWorker` applies temporal
rules and emits `StudentSignal` intervals that fit the backend `SignalEvent` fields.

| Label | Condition | Confidence |
| --- | --- | --- |
| `phone_visible` | phone score at least 0.5 | mean phone score |
| `head_away` | face found and yaw magnitude above 0.7 | mean face score |
| `face_absent` | person present but no face | placeholder 0.5 |
| `student_left_frame` | no person | placeholder 0.5 |

Each condition must persist for 1000 ms (sampling about every 334 ms) and a gap over
2000 ms discards the candidate. Frames are erased on every exit; only labelled intervals,
timestamps and a confidence leave the worker. `backend/scripts/run_student_signals.py`
replays a clip through it. Worker output on the synthetic clips:

| Clip | Emitted signals | Against ground truth |
| --- | --- | --- |
| `student_a` | `phone_visible` 0.0-5.7 s | whole clip: correct |
| `student_b` | `phone_visible` 1.0-3.0 s and 3.7-5.7 s | whole clip: about two thirds found |
| `student_d` | `head_away` 1.7-2.7 s | first turn found; second turn (about 0.8 s) under the 1 s minimum; phone missed |
| teacher clips | none | absence under 1 s, below the minimum; no false alarms |

Integration pieces, all opt-in and never launched by the application:

- `backend/app/local_ml/student_worker.py` is a camera CLI that requires
  `--consent-local-camera`, both model paths (each with a manifest beside it) and a session
  clock offset. It prints derived signals as JSON lines. If the camera is lost it marks the
  worker unavailable and emits nothing further, so a vanished source is never reported as
  the student leaving. It has not been run against a physical camera; only a fake source
  was tested.
- `backend/scripts/post_student_signals.py` validates worker output and posts it to
  `POST /api/v1/sessions/{id}/events/batch` in batches of 50. The student token comes from
  the `STUDENT_TOKEN` environment variable, never an argument, and non-loopback hosts are
  refused unless `--allow-remote` is passed. Identity comes from the token.
- Tests (16, synthetic frames and a fake analyzer only): timing, label mapping, frame
  erasure, flush, invalid input, digest gating, `SignalEvent` compatibility, posting
  through the real FastAPI app, a stranger being rejected with 403, clip-to-lecture time
  offsets, and camera loss. A 40 s phone-only signal is accepted but never marked recovery
  eligible, while a 40 s head turn meets the backend's 30 s rule.
- End to end with the real models: the four signals from the synthetic clips above were
  posted to the real app in-process and accepted. None was recovery eligible, because they
  last a few seconds and the backend's default minimum is 30 s.

## Limitations

- **No verified true positive for presenter absence.** No genuine presenter absence has been
  located in the lecture recordings, and the synthetic teacher clips are too short to
  trigger an event. All four presenter events inspected were false alarms, so the recall of
  `presenter_out_of_frame` is unknown.
- **Small, synthetic student evidence.** Three unique AI-generated student clips of under 6
  seconds each. There is no clip without a phone for students, so phone false positives on
  students specifically were not measured; the false-positive rate comes from class
  recordings.
- **Phone recall is weak for some poses.** 4% on `student_d` at the calibrated threshold. A
  trained classifier raised it to 33-50% in cross-validation but with more false alarms, and was
  not adopted.
- **Thresholds were partly fit on the evaluation data.** The head-turn threshold was chosen
  after inspecting the same clips. The phone threshold used negatives only, but its recall
  estimate rests on three clips.
- **The tile-visibility check is a heuristic.** It reports a black or blank tile as
  unavailable and does not detect layout changes that leave a plausible-looking tile.
- **Confidence is partly a placeholder.** Presenter events, `face_absent` and
  `student_left_frame` use a fixed 0.5 instead of a detector score.
- **Not run on a live camera or a live server.** The camera CLI was tested only with a
  fake source, and posting was tested through the in-process app and a mocked transport,
  not against a running server. Delivery events use `post_delivery_events.py` the same way.
  The backend's default 30-second minimum would not mark the short events these clips
  produce as possible missed windows; longer real sessions are needed for that path.
- **Looking down is not detected.** The label is not emitted.
- **Signals are not attention signals.** They describe framing and visible head or phone
  position. They say nothing about attention or comprehension.

## Reproduce

```sh
# Export the model (separate environment; needs torch/torchvision)
python -m venv .venv-export && . .venv-export/bin/activate
pip install -e "./backend[vision]" -r backend/requirements-model-export.txt certifi
SSL_CERT_FILE=$(python -c 'import certifi; print(certifi.where())') \
  python backend/scripts/export_person_detector.py --output-dir models --approve

# Analyze a local video (backend environment with the vision extra)
python backend/scripts/run_vision_on_video.py data/local/profs/<video>.mp4 --max-minutes 10
```

Pass `--approve` only after reviewing the model license. The default manifest leaves
`is_approved` false and the worker refuses to load it.

Evaluate short webcam-style clips (needs `models/face_detection_yunet_2023mar.onnx` from
OpenCV Zoo):

```sh
python backend/scripts/evaluate_clip_signals.py data/local/synthetic/*.mp4 --timeline
```

Replay a clip through the student worker, and re-run the threshold calibration (from the
repository root, with the backend on the path):

```sh
PYTHONPATH=backend python -m scripts.run_student_signals data/local/synthetic/student_a.mp4
PYTHONPATH=backend python -m scripts.calibrate_phone_threshold \
  --positive-clips data/local/synthetic/student_*.mp4 \
  --negative-clips data/local/synthetic/teacher_*.mp4 \
  --negative-recordings data/local/profs/*.mp4 data/local/student/*.mp4
```

Both YuNet and the person detector need a `*.manifest.json` beside the model file
(source, license, version, SHA-256, `is_approved`).

Run the student worker on a camera and post what it emits (opt-in, local; the model files
each need a manifest beside them):

```sh
python -m app.local_ml.student_worker --consent-local-camera \
  --person-model models/person_detector.onnx \
  --face-model models/face_detection_yunet_2023mar.onnx \
  --clock-offset-ms 0 > signals.jsonl
STUDENT_TOKEN=... PYTHONPATH=backend python -m scripts.post_student_signals signals.jsonl \
  --session-id <session> --lecture-id <lecture>
```

Train and cross-validate the phone classifier (features are cached under data/local/eval/):

```sh
PYTHONPATH=backend python -m scripts.train_phone_classifier \
  --positive-clips data/local/synthetic/student_*.mp4 \
  --negative-clips data/local/synthetic/teacher_*.mp4 \
  --recordings data/local/profs/*.mp4 data/local/student/*.mp4
```
