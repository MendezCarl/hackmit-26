"""Synthetic checks that the numpy classifier code fits, thresholds and generalizes."""

import sys
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.train_phone_classifier import (  # noqa: E402
    fit_logistic,
    predict,
    threshold_for,
)


def separable_data(count: int = 200, seed: int = 0):
    """Two synthetic clusters: positives have a higher first feature."""
    generator = np.random.default_rng(seed)
    negatives = generator.normal([0.0, 0.0], 0.5, size=(count, 2))
    positives = generator.normal([3.0, 0.0], 0.5, size=(count, 2))
    return np.vstack([negatives, positives]), np.concatenate([np.zeros(count), np.ones(count)])


def test_fit_separates_synthetic_clusters_on_held_out_data():
    x_train, y_train = separable_data(seed=1)
    x_test, y_test = separable_data(seed=2)
    model = fit_logistic(x_train, y_train)
    accuracy = np.mean((predict(x_test, model) >= 0.5) == y_test)
    assert accuracy > 0.95


def test_predict_returns_probabilities():
    x, y = separable_data()
    probabilities = predict(x, fit_logistic(x, y))
    assert probabilities.min() >= 0.0 and probabilities.max() <= 1.0


def test_threshold_keeps_training_false_positive_rate_within_target():
    x, y = separable_data()
    model = fit_logistic(x, y)
    negative_probabilities = predict(x[y == 0], model)
    threshold = threshold_for(negative_probabilities)
    assert np.mean(negative_probabilities >= threshold) <= 0.01


def test_class_balancing_handles_rare_positives():
    generator = np.random.default_rng(3)
    x = np.vstack([generator.normal(0, 0.5, (300, 2)), generator.normal([3, 0], 0.5, (10, 2))])
    y = np.concatenate([np.zeros(300), np.ones(10)])
    model = fit_logistic(x, y)
    assert np.mean(predict(x[y == 1], model) >= 0.5) > 0.8
