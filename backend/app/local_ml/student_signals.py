"""Local student-webcam observations turned into coarse derived signal events.

Frames stay on the device: the caller transfers ownership of each frame and the worker
erases it on every exit. Only labelled intervals with a confidence leave this module.
The labels are observations about what is visible (a phone, a turned head, no face),
never measurements of attention or comprehension. No model download, frame
persistence, telemetry or networking happens here.
"""

import hashlib
import statistics
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from app.contracts.learning import StrictPayload
from app.local_ml.vision import ModelManifest

Frame = NDArray[np.uint8]
StudentSignalLabel = Literal[
    "student_left_frame", "face_absent", "head_away", "phone_visible"
]

DETECTOR_INPUT_SIZE = 320
COCO_PERSON_CLASS_ID = 1  # torchvision 91-index COCO scheme.
COCO_CELL_PHONE_CLASS_ID = 77
MAXIMUM_MODEL_BYTES = 30 * 1024 * 1024
MAXIMUM_FRAME_BYTES = 1920 * 1080 * 3
MAXIMUM_LECTURE_MS = 28_800_000
FACE_SCORE_THRESHOLD = 0.6
BODY_CROP_BANDS = ((0.35, 1.0), (0.5, 1.1), (0.25, 0.9))  # Vertical span of the person box.
BODY_CROP_SIDE_PADDING = 0.15
MINIMUM_CROP_PIXELS = 20
FEATURE_NAMES = (
    "person_score",
    "person_height",
    "person_top",
    "phone_full",
    "phone_body",
    "face_score",
    "has_face",
    "face_height",
    "face_center_y",
    "yaw_magnitude",
    "pitch",
)
PLACEHOLDER_CONFIDENCE = 0.5  # Used when no positive detector score exists to average.


@dataclass(frozen=True)
class FrameObservation:
    """Derived per-frame detector scores; contains no pixels, boxes or identities."""

    person_score: float
    phone_score: float
    face_score: float  # 0.0 when no face was found.
    face_yaw: float | None  # Nose offset over eye distance; None when no face was found.


class StudentFrameAnalyzer(Protocol):
    """Local-only inference boundary; implementations must not retain frames."""

    def analyze(self, frame: Frame) -> FrameObservation:
        """Return derived scores for one BGR frame, or raise ValueError on bad input."""
        ...


class StudentSignalPolicy(StrictPayload):
    """Configurable heuristics. The phone threshold was chosen on a small evaluation.

    ``phone_threshold`` keeps the false-positive rate under 1% (0.7%) on about 1,900 frames
    of class recordings, counting a phone only while a person is in frame, at the cost of
    low recall for small or low-held phones.
    ``head_turn_yaw`` was chosen after inspecting three short clips and needs a larger,
    independent evaluation before it is trusted.
    """

    sampling_ms: int = Field(default=334, ge=100, le=2000)
    minimum_duration_ms: int = Field(default=1000, ge=100, le=60_000)
    maximum_sample_gap_ms: int = Field(default=2000, ge=100, le=10_000)
    person_threshold: float = Field(default=0.5, ge=0, le=1)
    phone_threshold: float = Field(default=0.4, ge=0, le=1)
    head_turn_yaw: float = Field(default=0.7, gt=0, le=3)
    merge_gap_ms: int = Field(
        default=1000,
        ge=0,
        le=10_000,
        description="A condition that resumes within this gap continues the same interval.",
    )
    baseline_window_samples: int = Field(
        default=180,
        ge=6,
        le=1000,
        description="Recent face-found samples (about a minute) used for the head-angle baseline.",
    )
    baseline_min_samples: int = Field(
        default=3,
        ge=3,
        le=100,
        description="Face-found samples (about a second) needed before head_away is judged.",
    )
    baseline_reset_ms: int = Field(
        default=60_000,
        ge=5_000,
        le=600_000,
        description="A turn lasting longer than this is taken as a new seating position.",
    )
    detector_version: str = "local-student-v1"


class StudentSignal(StrictPayload):
    """One derived observation interval; the caller adds the session and lecture ids."""

    event_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    event_type: StudentSignalLabel
    start_ms: int = Field(ge=0, le=MAXIMUM_LECTURE_MS)
    end_ms: int = Field(gt=0, le=MAXIMUM_LECTURE_MS)
    signals: list[StudentSignalLabel] = Field(min_length=1, max_length=1)
    confidence: float = Field(ge=0, le=1)


def verify_model_file(path: Path, manifest: ModelManifest) -> None:
    """Require operator approval, a bounded size and a matching digest before loading.

    Args:
        path: Model artifact chosen by the operator.
        manifest: Operator-approved provenance for that artifact.

    Raises:
        ValueError: If the model is unapproved, too large, or its digest differs.
    """
    if not manifest.is_approved or path.stat().st_size > MAXIMUM_MODEL_BYTES:
        raise ValueError("Model must be approved and at most 30 MiB")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.sha256:
        raise ValueError("Model digest mismatch")


class OnnxStudentAnalyzer:
    """CPU analyzer: SSDLite person and phone detection plus YuNet face landmarks."""

    def __init__(
        self,
        person_model: Path,
        person_manifest: ModelManifest,
        face_model: Path,
        face_manifest: ModelManifest,
    ) -> None:
        """Verify both artifacts, then load them on the CPU."""
        verify_model_file(person_model, person_manifest)
        verify_model_file(face_model, face_manifest)
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(person_model), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = self.session.get_inputs()
        if (
            len(inputs) != 1
            or inputs[0].shape
            != [1, 3, person_manifest.input_size, person_manifest.input_size]
            or inputs[0].type != "tensor(float)"
        ):
            raise ValueError("Unsupported model input tensor")
        self.input_name = inputs[0].name
        self.input_size = person_manifest.input_size
        self.face_detector = cv2.FaceDetectorYN.create(
            str(face_model),
            "",
            (DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE),
            FACE_SCORE_THRESHOLD,
            0.3,
            50,
        )

    @classmethod
    def from_files(cls, person_model: Path, face_model: Path) -> OnnxStudentAnalyzer:
        """Load both models with the ``<name>.manifest.json`` stored beside each file.

        Args:
            person_model: Operator-supplied ONNX person and phone detector.
            face_model: Operator-supplied ONNX YuNet face detector.

        Returns:
            A verified analyzer.

        Raises:
            ValueError: If a manifest is missing, unapproved or does not match its model.
            FileNotFoundError: If a model or manifest file does not exist.
        """
        return cls(
            person_model,
            ModelManifest.model_validate_json(
                person_model.with_suffix(".manifest.json").read_text()
            ),
            face_model,
            ModelManifest.model_validate_json(
                face_model.with_suffix(".manifest.json").read_text()
            ),
        )

    def _detect(self, image: NDArray[np.uint8]) -> NDArray[np.float32]:
        """Return validated Nx6 normalized xyxy/score/class rows; erase temporaries."""
        resized = cv2.resize(image, (self.input_size, self.input_size))
        tensor = (
            np.ascontiguousarray(
                resized[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32
            )
            / 255.0
        )
        outputs: list[NDArray[np.float32]] = []
        try:
            outputs = self.session.run(None, {self.input_name: tensor})
            rows = np.array(outputs[0], dtype=np.float32)
            if (
                rows.ndim != 2
                or rows.shape[1] != 6
                or rows.shape[0] > 1000
                or not np.isfinite(rows).all()
            ):
                raise ValueError("Unsupported model output tensor")
            return rows
        finally:
            tensor.fill(0)
            resized.fill(0)
            for output in outputs:
                output.fill(0)

    @staticmethod
    def _best_score(rows: NDArray[np.float32], class_id: int) -> float:
        """Highest score for a class, or 0 when it is absent."""
        selected = rows[rows[:, 5] == class_id]
        return float(selected[:, 4].max()) if len(selected) else 0.0

    def _person_phone_box(
        self, frame: Frame
    ) -> tuple[float, float, float, tuple[float, float] | None]:
        """Return person score, whole-frame phone score, body-crop phone score, person box.

        A phone is only a few pixels wide when the whole frame is squashed to the
        detector input, so the phone search also runs on crops of the person's body.
        The box is (normalized height, normalized top) of the best person, or None.
        """
        height, width = frame.shape[:2]
        full = self._detect(frame)
        person_score = self._best_score(full, COCO_PERSON_CLASS_ID)
        phone_full = self._best_score(full, COCO_CELL_PHONE_CLASS_ID)
        phone_body = 0.0
        people = full[full[:, 5] == COCO_PERSON_CLASS_ID]
        if not len(people):
            return person_score, phone_full, phone_body, None
        best = people[np.argmax(people[:, 4])]
        x1, y1, x2, y2 = best[:4] * [width, height, width, height]
        box_width, box_height = x2 - x1, y2 - y1
        for top, bottom in BODY_CROP_BANDS:
            left = max(0, int(x1 - BODY_CROP_SIDE_PADDING * box_width))
            right = min(width, int(x2 + BODY_CROP_SIDE_PADDING * box_width))
            upper = max(0, int(y1 + top * box_height))
            lower = min(height, int(y1 + bottom * box_height))
            if right - left > MINIMUM_CROP_PIXELS and lower - upper > MINIMUM_CROP_PIXELS:
                crop_rows = self._detect(frame[upper:lower, left:right])
                phone_body = max(
                    phone_body, self._best_score(crop_rows, COCO_CELL_PHONE_CLASS_ID)
                )
        return (
            person_score,
            phone_full,
            phone_body,
            (float(best[3] - best[1]), float(best[1])),
        )

    def person_and_phone(self, frame: Frame) -> tuple[float, float]:
        """Return the person score and the higher of the whole-frame and body-crop phone scores."""
        person_score, phone_full, phone_body, _ = self._person_phone_box(frame)
        return person_score, max(phone_full, phone_body)

    def _best_face(self, frame: Frame) -> NDArray[np.float32] | None:
        """Return the highest-scoring YuNet row (box, 5 landmarks, score), or None."""
        height, width = frame.shape[:2]
        self.face_detector.setInputSize((width, height))
        _, faces = self.face_detector.detect(frame)
        if faces is None or not len(faces):
            return None
        return faces[np.argmax(faces[:, -1])]

    def extract_features(self, frame: Frame) -> list[float]:
        """Derived numeric features for one frame, in ``FEATURE_NAMES`` order.

        Contains only scores and normalized geometry; no pixels, crops or identities.
        A missing face or person yields zeros for its features.
        """
        height, width = frame.shape[:2]
        person_score, phone_full, phone_body, box = self._person_phone_box(frame)
        face = self._best_face(frame)
        has_face = face is not None
        face_score = face_height = face_center_y = yaw_magnitude = pitch = 0.0
        if face is not None:
            right_eye, left_eye, nose = face[4:6], face[6:8], face[8:10]
            mouth = (face[10:12] + face[12:14]) / 2
            eye_middle = (right_eye + left_eye) / 2
            eye_distance = float(np.linalg.norm(right_eye - left_eye)) + 1e-6
            yaw_magnitude = abs(float((nose[0] - eye_middle[0]) / eye_distance))
            pitch = float((nose[1] - eye_middle[1]) / (mouth[1] - eye_middle[1] + 1e-6))
            face_score = float(face[-1])
            face_height = float(face[3] / height)
            face_center_y = float((face[1] + face[3] / 2) / height)
        return [
            person_score,
            box[0] if box else 0.0,
            box[1] if box else 0.0,
            phone_full,
            phone_body,
            face_score,
            float(has_face),
            face_height,
            face_center_y,
            yaw_magnitude,
            pitch,
        ]

    def face_score_and_yaw(self, frame: Frame) -> tuple[float, float | None]:
        """Return the best face score and a yaw proxy (nose offset over eye distance)."""
        best = self._best_face(frame)
        if best is None:
            return 0.0, None
        right_eye, left_eye, nose = best[4:6], best[6:8], best[8:10]
        eye_distance = float(np.linalg.norm(right_eye - left_eye)) + 1e-6
        yaw = float((nose[0] - (right_eye[0] + left_eye[0]) / 2) / eye_distance)
        return float(best[-1]), yaw

    def analyze(self, frame: Frame) -> FrameObservation:
        """Derive person, phone and face scores from one frame without keeping it."""
        person_score, phone_score = self.person_and_phone(frame)
        face_score, yaw = self.face_score_and_yaw(frame)
        return FrameObservation(person_score, phone_score, face_score, yaw)


@dataclass
class _Candidate:
    """A running condition. ``gap_start_ms`` is the first sample that stopped matching."""

    begin_ms: int
    count: int
    total: float
    gap_start_ms: int | None = None


class StudentSignalWorker:
    """One frame at a time; unavailable sources clear candidates without false events.

    Three rules make the raw per-frame flags steadier:

    - **Merging:** a condition that stops for less than ``merge_gap_ms`` and then resumes is
      one interval, so a brief detector dropout does not split an event.
    - **Head-angle baseline:** ``head_away`` measures the turn away from this person's own
      median yaw, so someone who sits at an angle is not flagged. It is judged only once
      ``baseline_min_samples`` face-found frames exist. Turned frames never feed the
      baseline, so a long turn keeps being reported; a turn longer than
      ``baseline_reset_ms`` is taken as a new seating position and re-baselined. The first
      frames define "normal", so someone already turned away at the start is not flagged.
    - **Turn continuity:** if the face disappears while the head was already turned (a profile
      the face detector cannot see), that continues ``head_away``. ``face_absent`` means the
      face disappeared while the person was facing forward, or was never seen.
    - **Corroboration:** ``phone_visible`` counts only while a person is in frame, since a
      phone has to be held by someone. This removes phone detections on screens or objects
      with nobody present.
    """

    def __init__(self, analyzer: StudentFrameAnalyzer, policy: StudentSignalPolicy) -> None:
        """Inject a local analyzer; no camera is opened."""
        self.analyzer = analyzer
        self.policy = policy
        self.active: dict[StudentSignalLabel, _Candidate] = {}
        self.yaw_history: deque[float] = deque(maxlen=policy.baseline_window_samples)
        self.turn_since_ms: int | None = None
        self.last_face_was_turned: bool | None = None
        self.previous_ms: int | None = None
        self.last_latency_ms = 0
        self.is_available = True

    def unavailable(self) -> None:
        """Discard incomplete candidates and the baseline after camera loss; emit nothing."""
        self.active.clear()
        self.yaw_history.clear()
        self.turn_since_ms = None
        self.last_face_was_turned = None
        self.previous_ms = None
        self.is_available = False

    def _yaw_baseline(self) -> float | None:
        """Median yaw for this person, or None until enough face-found samples exist."""
        if len(self.yaw_history) < self.policy.baseline_min_samples:
            return None
        return float(statistics.median(self.yaw_history))

    def _update_baseline(self, yaw: float | None, is_turned: bool, now_ms: int) -> None:
        """Feed the baseline, skipping turned frames once it exists; re-baseline on long turns."""
        established = len(self.yaw_history) >= self.policy.baseline_min_samples
        if yaw is not None and not (is_turned and established):
            self.yaw_history.append(yaw)
        if not is_turned:
            self.turn_since_ms = None
        elif self.turn_since_ms is None:
            self.turn_since_ms = now_ms
        elif now_ms - self.turn_since_ms > self.policy.baseline_reset_ms:
            self.yaw_history.clear()
            self.turn_since_ms = None

    def _flags(
        self, observation: FrameObservation, baseline: float | None
    ) -> dict[StudentSignalLabel, tuple[bool, float]]:
        """Map one observation to (is_positive, confidence contribution) per label."""
        policy = self.policy
        is_person = observation.person_score >= policy.person_threshold
        has_face = observation.face_yaw is not None
        is_turned = (
            has_face
            and baseline is not None
            and abs((observation.face_yaw or 0.0) - baseline) > policy.head_turn_yaw
        )
        # A turned head that leaves the detector's view (a profile) loses the face; that is
        # still the same turn, so it continues "head_away" instead of becoming "face_absent".
        lost_after_turn = is_person and not has_face and bool(self.last_face_was_turned)
        return {
            "student_left_frame": (not is_person, PLACEHOLDER_CONFIDENCE),
            "face_absent": (
                is_person and not has_face and not lost_after_turn,
                PLACEHOLDER_CONFIDENCE,
            ),
            "head_away": (
                is_turned or lost_after_turn,
                observation.face_score if is_turned else PLACEHOLDER_CONFIDENCE,
            ),
            "phone_visible": (
                is_person and observation.phone_score >= policy.phone_threshold,
                observation.phone_score,
            ),
        }

    def _close(
        self, label: StudentSignalLabel, candidate: _Candidate, end_ms: int
    ) -> StudentSignal | None:
        """Build a signal for a finished candidate, or None when it was too short."""
        if (
            end_ms - candidate.begin_ms < self.policy.minimum_duration_ms
            or candidate.count == 0
        ):
            return None
        return StudentSignal(
            event_id=f"student_{uuid4().hex}",
            event_type=label,
            start_ms=candidate.begin_ms,
            end_ms=end_ms,
            signals=[label],
            confidence=min(1.0, max(0.0, candidate.total / candidate.count)),
        )

    def _advance(
        self, label: StudentSignalLabel, is_positive: bool, contribution: float, now_ms: int
    ) -> StudentSignal | None:
        """Update one label's candidate for this sample; return a signal if one finished."""
        candidate = self.active.get(label)
        if is_positive:
            if candidate is None:
                self.active[label] = _Candidate(now_ms, 1, contribution)
                return None
            if candidate.gap_start_ms is not None and (
                now_ms - candidate.gap_start_ms >= self.policy.merge_gap_ms
            ):
                # The pause was too long to bridge: finish the old interval, start a new one.
                finished = self._close(label, candidate, candidate.gap_start_ms)
                self.active[label] = _Candidate(now_ms, 1, contribution)
                return finished
            candidate.count += 1
            candidate.total += contribution
            candidate.gap_start_ms = None
            return None
        if candidate is None:
            return None
        if candidate.gap_start_ms is None:
            candidate.gap_start_ms = now_ms
        if now_ms - candidate.gap_start_ms >= self.policy.merge_gap_ms:
            del self.active[label]
            return self._close(label, candidate, candidate.gap_start_ms)
        return None

    def _finish_ended(self) -> list[StudentSignal]:
        """Close candidates that had already stopped matching; drop those still running."""
        finished = []
        for label, candidate in self.active.items():
            if candidate.gap_start_ms is not None:
                signal = self._close(label, candidate, candidate.gap_start_ms)
                if signal is not None:
                    finished.append(signal)
        self.active.clear()
        return finished

    def observe(self, frame: Frame, lecture_time_ms: int) -> list[StudentSignal]:
        """Consume and erase an owned BGR frame; emit closed, sustained intervals only.

        Raises:
            ValueError: Invalid frame or non-monotonic lecture timestamp. Inference
                failures mark the worker unavailable and propagate without raw data.
        """
        started = time.perf_counter()
        try:
            if (
                frame.dtype != np.uint8
                or frame.ndim != 3
                or frame.shape[2] != 3
                or frame.size > MAXIMUM_FRAME_BYTES
            ):
                raise ValueError("Invalid bounded BGR frame")
            if not 0 <= lecture_time_ms <= MAXIMUM_LECTURE_MS or (
                self.previous_ms is not None and lecture_time_ms <= self.previous_ms
            ):
                raise ValueError("Lecture timestamps must increase")
            if (
                self.previous_ms is not None
                and lecture_time_ms - self.previous_ms < self.policy.sampling_ms
            ):
                return []
            events: list[StudentSignal] = []
            if (
                self.previous_ms is not None
                and lecture_time_ms - self.previous_ms > self.policy.maximum_sample_gap_ms
            ):
                events += self._finish_ended()
            self.previous_ms = lecture_time_ms
            observation = self.analyzer.analyze(frame)
            flags = self._flags(observation, self._yaw_baseline())
            if observation.face_yaw is not None:
                self.last_face_was_turned = flags["head_away"][0]
            elif observation.person_score < self.policy.person_threshold:
                self.last_face_was_turned = None
            self._update_baseline(
                observation.face_yaw, flags["head_away"][0], lecture_time_ms
            )
            for label, (is_positive, contribution) in flags.items():
                signal = self._advance(label, is_positive, contribution, lecture_time_ms)
                if signal is not None:
                    events.append(signal)
            self.is_available = True
            return events
        except Exception:
            self.unavailable()
            raise
        finally:
            frame.fill(0)
            self.last_latency_ms = int((time.perf_counter() - started) * 1000)

    def flush(self, lecture_time_ms: int) -> list[StudentSignal]:
        """Close conditions still open when observation stops, e.g. at end of lecture."""
        events = []
        for label, candidate in self.active.items():
            end_ms = (
                candidate.gap_start_ms
                if candidate.gap_start_ms is not None
                else lecture_time_ms
            )
            signal = self._close(label, candidate, end_ms)
            if signal is not None:
                events.append(signal)
        self.active.clear()
        return events
