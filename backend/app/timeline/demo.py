"""Synthetic authentication fixture shared by isolated feature demos."""

from typing import Literal

from app.timeline.composition import installed_features
from app.timeline.contracts import FeatureError, Participation, SessionGrant
from app.timeline.dependencies import FeatureServices
from app.timeline.repository import MemorySessionRepository

DEMO_SESSION_ID = "demo-session"
DEMO_LECTURE_ID = "demo-lecture"
DEMO_ORIGIN_MS = 1_720_000_000_000
DEMO_DURATION_MS = 60_000


class DemoSessionAccess:
    """Fixed synthetic actors; never use as production authentication."""

    def __init__(self) -> None:
        """Create five opted-in synthetic students and an initially active lecture."""
        self.is_ended = False
        self.revoked_tokens: set[str] = set()
        self.roster = [
            Participation(
                participant_key=f"student-{index}",
                start_ms=0,
                end_ms=DEMO_DURATION_MS,
                has_aggregate_consent=True,
            )
            for index in range(1, 6)
        ]

    async def authorize(self, token: str, session_id: str) -> SessionGrant:
        """Resolve only documented synthetic tokens; all other credentials are denied."""
        if session_id != DEMO_SESSION_ID:
            raise FeatureError("session_not_found", "Session was not found.", 404)
        if token in self.revoked_tokens:
            raise FeatureError("unauthorized", "Credential is unavailable.", 401)
        role: Literal["student", "professor", "transcriber"]
        if token in {f"demo-student-{index}" for index in range(1, 6)}:
            role = "student"
            actor = token.removeprefix("demo-")
        elif token == "demo-professor":
            role, actor = "professor", "professor"
        elif token == "demo-transcriber":
            role, actor = "transcriber", "transcriber"
        else:
            raise FeatureError("unauthorized", "Credential is unavailable.", 401)
        return SessionGrant(
            session_id=session_id,
            lecture_id=DEMO_LECTURE_ID,
            actor_id=actor,
            participant_key=actor,
            role=role,
            can_signal=role == "student",
            has_signal_consent=role == "student",
            can_transcribe=role == "transcriber",
            can_use_dropbox=role == "student",
            is_ended=self.is_ended,
            duration_ms=DEMO_DURATION_MS,
            clock_origin_epoch_ms=DEMO_ORIGIN_MS,
        )

    async def participants(self, session_id: str) -> list[Participation]:
        """Return detached synthetic consent/attendance records."""
        if session_id != DEMO_SESSION_ID:
            return []
        return [member.model_copy(deep=True) for member in self.roster]


def build_demo_services(
    enabled_features: tuple[str, ...] | None = None,
) -> FeatureServices:
    """Construct only the selected feature fakes; never contact providers."""
    services = FeatureServices(
        access=DemoSessionAccess(),
        repository=MemorySessionRepository(),
        enabled_features=enabled_features,
    )
    for feature in installed_features(enabled_features):
        feature.configure_demo(services)
    return services
