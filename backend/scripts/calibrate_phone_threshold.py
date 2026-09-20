"""Choose a phone-score threshold from labelled clips and real-footage negatives.

Positives are frames from clips where a phone is held for the whole clip. Negatives
are frames from consented class recordings and teacher clips, where a phone is
assumed absent (any high-scoring negative should be inspected by eye). The threshold
is the lowest score whose false-positive rate on the negatives stays under a target.
The positive clips are not used to choose the threshold, so their recall at the
chosen threshold is an honest (if small-sample) estimate.

Only score statistics are produced; frames are analyzed in memory and never saved.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from app.local_ml.model_paths import FACE_MODEL_PATH, PERSON_MODEL_PATH
from app.local_ml.student_signals import OnnxStudentAnalyzer
from scripts.evaluate_clip_signals import load_analyzer

CLIP_STRIDE_FRAMES = 6
LONG_VIDEO_SAMPLE_SECONDS = 60
PERSON_THRESHOLD = (
    0.5  # Matches the worker: a phone counts only while a person is in frame.
)
THRESHOLD_GRID = [round(value, 2) for value in np.arange(0.10, 0.81, 0.05)]


def gated_phone_score(extractor: OnnxStudentAnalyzer, frame) -> float:
    """Phone score, or zero when no person is in frame (the worker's corroboration rule)."""
    person_score, phone_score = extractor.person_and_phone(frame)
    return phone_score if person_score >= PERSON_THRESHOLD else 0.0


def clip_phone_scores(extractor: OnnxStudentAnalyzer, path: Path) -> list[float]:
    """Phone scores for every sampled frame of a short clip."""
    capture = cv2.VideoCapture(str(path))
    scores, index = [], 0
    while capture.grab():
        if index % CLIP_STRIDE_FRAMES == 0:
            valid, frame = capture.retrieve()
            if valid:
                scores.append(gated_phone_score(extractor, frame))
                frame.fill(0)
        index += 1
    capture.release()
    return scores


def sparse_phone_scores(extractor: OnnxStudentAnalyzer, path: Path) -> list[float]:
    """Phone scores for one frame per minute of a long recording."""
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    duration_s = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    scores = []
    for second in np.arange(5, duration_s - 1, LONG_VIDEO_SAMPLE_SECONDS):
        capture.set(cv2.CAP_PROP_POS_MSEC, float(second) * 1000)
        valid, frame = capture.read()
        if valid:
            scores.append(gated_phone_score(extractor, frame))
            frame.fill(0)
    capture.release()
    return scores


def rate(scores: list[float], threshold: float) -> float:
    """Fraction of scores at or above the threshold."""
    return float(np.mean([score >= threshold for score in scores])) if scores else 0.0


def choose_threshold(negatives: list[float], max_false_positive_rate: float) -> float:
    """Lowest grid threshold whose false-positive rate on negatives is within target."""
    for threshold in THRESHOLD_GRID:
        if rate(negatives, threshold) <= max_false_positive_rate:
            return threshold
    return THRESHOLD_GRID[-1]


def main() -> None:
    """Score every source, sweep thresholds, and report recall and false positives."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-clips", nargs="+", type=Path, required=True)
    parser.add_argument("--negative-clips", nargs="+", type=Path, default=[])
    parser.add_argument("--negative-recordings", nargs="+", type=Path, default=[])
    parser.add_argument("--max-false-positive-rate", type=float, default=0.01)
    parser.add_argument("--person-model", type=Path, default=PERSON_MODEL_PATH)
    parser.add_argument("--face-model", type=Path, default=FACE_MODEL_PATH)
    parser.add_argument(
        "--output", type=Path, default=Path("data/local/eval/phone_calibration.json")
    )
    arguments = parser.parse_args()
    extractor = load_analyzer(arguments.person_model, arguments.face_model)

    positives = {p.name: clip_phone_scores(extractor, p) for p in arguments.positive_clips}
    negatives: list[float] = []
    negative_sources: dict[str, dict[str, float]] = {}
    for path in arguments.negative_clips:
        scores = clip_phone_scores(extractor, path)
        negatives += scores
        negative_sources[path.name] = {"samples": len(scores), "max": round(max(scores), 2)}
    for path in arguments.negative_recordings:
        scores = sparse_phone_scores(extractor, path)
        if (
            not scores
        ):  # Too short to sample (e.g. the 6 s synthetic clips): never a negative.
            continue
        negatives += scores
        negative_sources[path.name[:40]] = {
            "samples": len(scores),
            "max": round(max(scores), 2),
        }

    print(
        f"positives: {sum(map(len, positives.values()))} frames in {len(positives)} clips; "
        f"negatives: {len(negatives)} frames from {len(negative_sources)} sources"
    )
    print(
        "threshold  TPR(all)  FPR   " + "  ".join(f"TPR {name[:9]}" for name in positives)
    )
    for threshold in THRESHOLD_GRID:
        per_clip = "  ".join(f"{rate(s, threshold):9.2f}" for s in positives.values())
        every = [x for s in positives.values() for x in s]
        print(
            f"{threshold:9.2f}  {rate(every, threshold):8.2f}  {rate(negatives, threshold):.3f}  {per_clip}"
        )

    chosen = choose_threshold(negatives, arguments.max_false_positive_rate)
    recall_at_chosen = {name: round(rate(s, chosen), 2) for name, s in positives.items()}
    print(f"\nchosen threshold at FPR <= {arguments.max_false_positive_rate}: {chosen}")
    print("recall per positive clip at that threshold:", recall_at_chosen)
    top_negatives = sorted(negatives, reverse=True)[:5]
    print(
        "highest negative scores (inspect these by eye):",
        [round(x, 2) for x in top_negatives],
    )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            {
                "chosen_threshold": chosen,
                "max_false_positive_rate": arguments.max_false_positive_rate,
                "negative_frames": len(negatives),
                "recall_per_positive_clip": recall_at_chosen,
                "negative_sources": negative_sources,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
