"""Integration-owned router composition; feature handlers stay in their modules."""

from fastapi import APIRouter

from app.delivery.routes import router as delivery_router
from app.professor.metrics_routes import router as metrics_router
from app.professor.recommendation_routes import router as recommendation_router
from app.recovery.consent_routes import router as consent_router

router = APIRouter()
for feature_router in (
    metrics_router,
    recommendation_router,
    delivery_router,
    consent_router,
):
    router.include_router(feature_router)
