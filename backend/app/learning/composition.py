"""Compose new plan services with the existing host; local vision stays unmounted."""

import os

from fastapi import FastAPI

from app.ai.routes import router as ai_router
from app.artifacts.export import ExportService, MockArtifactDestination
from app.artifacts.export import router as artifact_router
from app.contracts.learning import MetricsPolicy
from app.delivery.service import DeliveryService
from app.learning.routes import router
from app.learning.state import LearningState
from app.professor.metrics import ProfessorMetricsService
from app.professor.recommendations import (
    DeterministicRecommendations,
    RecommendationGenerator,
    RecommendationService,
)


def install_learning_features(
    app: FastAPI, policy: MetricsPolicy | None = None
) -> None:
    """Install derived-data services using shared host membership and storage.

    No network calls occur during composition. Real reporting requires an explicit
    policy JSON setting; test/demo settings are clearly marked synthetic.
    """
    state = LearningState()
    settings = app.state.settings
    if policy is None and settings.is_demo_or_test():
        policy = MetricsPolicy(
            policy_version="synthetic-demo-v1", minimum_group_size=5, bucket_ms=30_000
        )
    elif policy is None and os.environ.get("LUMINA_METRICS_POLICY_JSON"):
        policy = MetricsPolicy.model_validate_json(
            os.environ["LUMINA_METRICS_POLICY_JSON"]
        )
    metrics = ProfessorMetricsService(
        app.state.store, state, app.state.session_access, settings, policy
    )
    app.state.learning_state = state
    app.state.artifact_exports = ExportService(
        MockArtifactDestination() if settings.is_demo_or_test() else None
    )
    app.state.professor_metrics = metrics
    app.state.delivery_service = DeliveryService(
        app.state.store, state, app.state.session_access
    )
    app.state.recovery_service.configure_privacy(state)
    recommendations: RecommendationGenerator = DeterministicRecommendations()
    delegate = app.state.recovery_generator.delegate
    if delegate.provider == "openai":
        from app.integrations.openai.tools import OpenAIRecommendations

        recommendations = OpenAIRecommendations(delegate.client, delegate.model)
    app.state.recommendation_service = RecommendationService(
        metrics, state, recommendations
    )
    app.include_router(router)
    app.include_router(ai_router)
    app.include_router(artifact_router)
