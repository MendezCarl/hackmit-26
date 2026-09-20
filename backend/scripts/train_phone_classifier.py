"""Train and cross-validate a small phone-use classifier on derived detector features.

The classifier is a logistic regression over scores and geometry that the pretrained
detectors already produce (phone score, head angle, face size, ...). It is trained in
plain numpy so no dependency is added. It never sees pixels.

Evaluation is leave-one-positive-clip-out: each student clip is held out in turn, and
negative sources are split across the same folds, so every reported number is on data
the model did not train on. A hand-set rule (phone score >= 0.5) is scored on the same
held-out data for comparison. Two feature sets are compared: all features, and
behaviour-only features that ignore framing (to reduce the chance that the model learns
camera placement instead of phone use).

Frames are analyzed in memory only; only feature vectors are cached, under the
gitignored data/local/.
"""

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from app.local_ml.student_signals import FEATURE_NAMES, OnnxStudentAnalyzer
from scripts.evaluate_clip_signals import load_analyzer

CLIP_STRIDE_FRAMES = 6
RECORDING_SAMPLE_SECONDS = 15
MINIMUM_RECORDING_SECONDS = 60  # Skips the short synthetic clips copied into the folders.
FOLD_COUNT = 3
MAX_FALSE_POSITIVE_RATE = 0.01
BASELINE_PHONE_THRESHOLD = 0.5
FACE_SIZE_PERCENTILE = 5
BEHAVIOUR_FEATURES = ("phone_full", "phone_body", "face_score", "yaw_magnitude", "pitch")
L2_STRENGTH = 1.0
LEARNING_RATE = 0.1
ITERATIONS = 3000


def clip_features(analyzer: OnnxStudentAnalyzer, path: Path) -> list[list[float]]:
    """Feature vectors for every sampled frame of a short clip."""
    capture = cv2.VideoCapture(str(path))
    rows, index = [], 0
    while capture.grab():
        if index % CLIP_STRIDE_FRAMES == 0:
            valid, frame = capture.retrieve()
            if valid:
                rows.append(analyzer.extract_features(frame))
                frame.fill(0)
        index += 1
    capture.release()
    return rows


def recording_features(analyzer: OnnxStudentAnalyzer, path: Path) -> list[list[float]]:
    """Feature vectors at a fixed interval through a long recording."""
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    rows = []
    for second in np.arange(5, duration - 1, RECORDING_SAMPLE_SECONDS):
        capture.set(cv2.CAP_PROP_POS_MSEC, float(second) * 1000)
        valid, frame = capture.read()
        if valid:
            rows.append(analyzer.extract_features(frame))
            frame.fill(0)
    capture.release()
    return rows


def unique_recordings(paths: list[Path]) -> list[Path]:
    """Drop duplicate files (same size and head bytes) and clips too short to sample."""
    seen, kept = set(), []
    for path in paths:
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        seconds = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
        capture.release()
        with path.open("rb") as handle:
            key = (path.stat().st_size, hashlib.sha256(handle.read(1 << 20)).hexdigest())
        if seconds >= MINIMUM_RECORDING_SECONDS and key not in seen:
            seen.add(key)
            kept.append(path)
    return kept


def extract_all(
    analyzer, positives, negative_clips, recordings, cache: Path
) -> dict[str, object]:
    """Extract (or load cached) features with a source name per row."""
    if cache.exists():
        stored = np.load(cache, allow_pickle=False)
        return {key: stored[key] for key in stored.files}
    rows, kinds, sources = [], [], []
    for kind, paths, extractor in (
        ("positive", positives, clip_features),
        ("negative_clip", negative_clips, clip_features),
        ("negative_recording", recordings, recording_features),
    ):
        for path in paths:
            features = extractor(analyzer, path)
            rows += features
            kinds += [kind] * len(features)
            sources += [path.name] * len(features)
            print(f"  {kind:18} {path.name[:44]:44} {len(features)} rows", flush=True)
    data = {"x": np.array(rows), "kind": np.array(kinds), "source": np.array(sources)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, **data)
    return data


def fit_logistic(
    x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Fit a class-balanced, L2-regularized logistic regression by gradient descent.

    Args:
        x: Feature matrix.
        y: Labels, 1 for phone in use.

    Returns:
        Weights, bias, and the mean and standard deviation used to standardize features.
    """
    mean, std = x.mean(axis=0), x.std(axis=0) + 1e-6
    z = (x - mean) / std
    positive_weight = len(y) / (2 * max(1, int(y.sum())))
    negative_weight = len(y) / (2 * max(1, int((1 - y).sum())))
    sample_weight = np.where(y == 1, positive_weight, negative_weight)
    weights, bias = np.zeros(z.shape[1]), 0.0
    for _ in range(ITERATIONS):
        probability = 1 / (1 + np.exp(-np.clip(z @ weights + bias, -30, 30)))
        error = (probability - y) * sample_weight
        weights -= LEARNING_RATE * (z.T @ error / len(y) + L2_STRENGTH * weights / len(y))
        bias -= LEARNING_RATE * error.mean()
    return weights, float(bias), mean, std


def predict(
    x: np.ndarray, model: tuple[np.ndarray, float, np.ndarray, np.ndarray]
) -> np.ndarray:
    """Probability of phone use for each row."""
    weights, bias, mean, std = model
    return 1 / (1 + np.exp(-np.clip(((x - mean) / std) @ weights + bias, -30, 30)))


def threshold_for(negative_probabilities: np.ndarray) -> float:
    """Smallest probability threshold whose training false-positive rate is acceptable."""
    for threshold in np.linspace(0.05, 0.99, 95):
        if np.mean(negative_probabilities >= threshold) <= MAX_FALSE_POSITIVE_RATE:
            return float(threshold)
    return 0.99


def cross_validate(
    x, y, groups, positive_clips, negative_sources, columns
) -> dict[str, object]:
    """Leave-one-positive-clip-out evaluation for one feature set and the rule baseline."""
    fold_of_source = {
        name: index % FOLD_COUNT for index, name in enumerate(negative_sources)
    }
    per_fold = []
    for fold, held_clip in enumerate(positive_clips):
        is_held_pos = np.array([g == held_clip for g in groups])
        is_held_neg = np.array([fold_of_source.get(g) == fold for g in groups])
        train = ~(is_held_pos | is_held_neg)
        model = fit_logistic(x[train][:, columns], y[train])
        train_negative = predict(x[train & (y == 0)][:, columns], model)
        threshold = threshold_for(train_negative)
        held_positive = predict(x[is_held_pos][:, columns], model)
        held_negative = predict(x[is_held_neg & (y == 0)][:, columns], model)
        phone_body = x[:, FEATURE_NAMES.index("phone_body")]
        phone_full = x[:, FEATURE_NAMES.index("phone_full")]
        rule = np.maximum(phone_body, phone_full)
        per_fold.append(
            {
                "held_out_clip": held_clip,
                "threshold": round(threshold, 2),
                "model_recall": round(float(np.mean(held_positive >= threshold)), 2),
                "model_false_positive_rate": round(
                    float(np.mean(held_negative >= threshold)), 3
                ),
                "rule_recall": round(
                    float(np.mean(rule[is_held_pos] >= BASELINE_PHONE_THRESHOLD)), 2
                ),
                "rule_false_positive_rate": round(
                    float(
                        np.mean(rule[is_held_neg & (y == 0)] >= BASELINE_PHONE_THRESHOLD)
                    ),
                    3,
                ),
                "held_out_negative_rows": int((is_held_neg & (y == 0)).sum()),
            }
        )
    return {
        "folds": per_fold,
        "mean_model_recall": round(
            float(np.mean([f["model_recall"] for f in per_fold])), 2
        ),
        "mean_rule_recall": round(float(np.mean([f["rule_recall"] for f in per_fold])), 2),
    }


def main() -> None:
    """Extract features, cross-validate two feature sets, and save the final model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-clips", nargs="+", type=Path, required=True)
    parser.add_argument("--negative-clips", nargs="+", type=Path, default=[])
    parser.add_argument("--recordings", nargs="+", type=Path, default=[])
    parser.add_argument(
        "--person-model", type=Path, default=Path("models/person_detector.onnx")
    )
    parser.add_argument(
        "--face-model", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx")
    )
    parser.add_argument(
        "--cache", type=Path, default=Path("data/local/eval/phone_features.npz")
    )
    parser.add_argument(
        "--output-model", type=Path, default=Path("models/phone_classifier.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("data/local/eval/phone_training_report.json")
    )
    arguments = parser.parse_args()

    analyzer = load_analyzer(arguments.person_model, arguments.face_model)
    recordings = unique_recordings(arguments.recordings)
    print(f"extracting features ({len(recordings)} unique recordings)", flush=True)
    data = extract_all(
        analyzer,
        arguments.positive_clips,
        arguments.negative_clips,
        recordings,
        arguments.cache,
    )
    x, kind, source = data["x"], data["kind"], data["source"]

    face_height = x[:, FEATURE_NAMES.index("face_height")]
    has_face = x[:, FEATURE_NAMES.index("has_face")] > 0
    positive_mask = kind == "positive"
    minimum_face = float(np.percentile(face_height[positive_mask], FACE_SIZE_PERCENTILE))
    # Matched negatives: a person with a face at least as large as the student clips show,
    # so the classifier cannot separate classes by "close-up webcam" versus "screen share".
    keep = positive_mask | (~positive_mask & has_face & (face_height >= minimum_face))
    x, kind, source = x[keep], kind[keep], source[keep]
    y = (kind == "positive").astype(float)
    print(f"minimum face height for negatives: {minimum_face:.3f}")
    print(
        f"rows: {int(y.sum())} positive, {int((1 - y).sum())} matched negative "
        f"from {len(set(source[y == 0]))} sources"
    )

    positive_clips = sorted(set(source[y == 1]))
    negative_sources = sorted(set(source[y == 0]))
    feature_sets = {
        "all_features": list(range(len(FEATURE_NAMES))),
        "behaviour_only": [FEATURE_NAMES.index(n) for n in BEHAVIOUR_FEATURES],
    }
    report: dict[str, object] = {"matched_negative_rows": int((1 - y).sum())}
    for name, columns in feature_sets.items():
        result = cross_validate(
            x, y, list(source), positive_clips, negative_sources, columns
        )
        report[name] = result
        print(
            f"\n{name}: mean held-out recall {result['mean_model_recall']} "
            f"(rule {result['mean_rule_recall']})"
        )
        for fold in result["folds"]:
            print(
                f"  hold out {fold['held_out_clip']:14} model recall {fold['model_recall']:.2f} "
                f"FPR {fold['model_false_positive_rate']:.3f} | rule recall {fold['rule_recall']:.2f} "
                f"FPR {fold['rule_false_positive_rate']:.3f} | thr {fold['threshold']} "
                f"({fold['held_out_negative_rows']} held-out negatives)"
            )

    columns = feature_sets["behaviour_only"]
    model = fit_logistic(x[:, columns], y)
    threshold = threshold_for(predict(x[y == 0][:, columns], model))
    weights, bias, mean, std = model
    arguments.output_model.parent.mkdir(parents=True, exist_ok=True)
    arguments.output_model.write_text(
        json.dumps(
            {
                "feature_names": [FEATURE_NAMES[i] for i in columns],
                "weights": weights.tolist(),
                "bias": bias,
                "mean": mean.tolist(),
                "std": std.tolist(),
                "threshold": threshold,
                "trained_on": {
                    "positive_rows": int(y.sum()),
                    "negative_rows": int((1 - y).sum()),
                },
            },
            indent=2,
        )
    )
    arguments.report.write_text(json.dumps(report, indent=2))
    print(
        f"\nfinal behaviour-only model saved to {arguments.output_model} (threshold {threshold:.2f})"
    )


if __name__ == "__main__":
    main()
