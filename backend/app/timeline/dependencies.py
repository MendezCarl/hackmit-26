"""Common authorization with explicitly installed, optional feature services."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

from app.timeline.contracts import FeatureError, Identifier, SessionAccess, SessionGrant
from app.timeline.ports import (
    DropboxPort,
    ProfessorPort,
    SignalPort,
    TimelinePort,
    TranscriptPort,
)
from app.timeline.repository import SessionRepository


@dataclass
class FeatureServices:
    """Shared host dependencies; absent features fail closed rather than importing siblings."""

    access: SessionAccess
    repository: SessionRepository
    enabled_features: tuple[str, ...] | None = None
    _signals: SignalPort | None = None
    _transcripts: TranscriptPort | None = None
    _timeline: TimelinePort | None = None
    _professor: ProfessorPort | None = None
    _dropbox: DropboxPort | None = None

    @property
    def signals(self) -> SignalPort:
        """Return the installed signals service or raise a safe unavailable error."""
        if self._signals is None:
            raise FeatureError(
                "feature_unavailable", "This feature is not configured.", 503
            )
        return self._signals

    @signals.setter
    def signals(self, service: SignalPort) -> None:
        """Install the typed signals service during application composition."""
        self._signals = service

    @property
    def transcripts(self) -> TranscriptPort:
        """Return the installed transcripts service or raise a safe unavailable error."""
        if self._transcripts is None:
            raise FeatureError(
                "feature_unavailable", "This feature is not configured.", 503
            )
        return self._transcripts

    @transcripts.setter
    def transcripts(self, service: TranscriptPort) -> None:
        """Install the typed transcripts service during application composition."""
        self._transcripts = service

    @property
    def timeline(self) -> TimelinePort:
        """Return the installed timeline service or raise a safe unavailable error."""
        if self._timeline is None:
            raise FeatureError(
                "feature_unavailable", "This feature is not configured.", 503
            )
        return self._timeline

    @timeline.setter
    def timeline(self, service: TimelinePort) -> None:
        """Install the typed timeline service during application composition."""
        self._timeline = service

    @property
    def professor(self) -> ProfessorPort:
        """Return the installed professor service or raise a safe unavailable error."""
        if self._professor is None:
            raise FeatureError(
                "feature_unavailable", "This feature is not configured.", 503
            )
        return self._professor

    @professor.setter
    def professor(self, service: ProfessorPort) -> None:
        """Install the typed professor service during application composition."""
        self._professor = service

    @property
    def dropbox(self) -> DropboxPort:
        """Return the installed dropbox service or raise a safe unavailable error."""
        if self._dropbox is None:
            raise FeatureError(
                "feature_unavailable", "This feature is not configured.", 503
            )
        return self._dropbox

    @dropbox.setter
    def dropbox(self, service: DropboxPort) -> None:
        """Install the typed dropbox service during application composition."""
        self._dropbox = service


def get_services(connection: HTTPConnection) -> FeatureServices:
    """Return the explicitly registered per-app service bundle; fail closed if absent."""
    services = getattr(connection.app.state, "lecture_feature_services", None)
    if not isinstance(services, FeatureServices):
        raise FeatureError(
            "features_unconfigured", "Feature dependencies are not configured.", 503
        )
    return services


Services = Annotated[FeatureServices, Depends(get_services)]
bearer = HTTPBearer(
    auto_error=False,
    description="Host-issued bearer token; session membership and consent are checked on every request.",
)


async def authorized_session(
    session_id: Identifier,
    services: Services,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessionGrant:
    """Authenticate through the host and validate session binding; never trust body roles."""
    if credentials is None:
        raise FeatureError("unauthorized", "A bearer token is required.", 401)
    grant = await services.access.authorize(credentials.credentials, session_id)
    if grant.session_id != session_id:
        raise FeatureError("forbidden", "Session access was denied.", 403)
    return grant


AuthorizedSession = Annotated[SessionGrant, Depends(authorized_session)]
