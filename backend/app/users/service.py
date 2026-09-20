"""User-account service: registration, login, profiles, and consent.

Identity and roles always come from verified JWTs after login; registration
is the only place a role is chosen. Password hashes never leave this module.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor, issue_access_token
from app.config import Settings
from app.contracts.models import (
    AuthSession,
    ConsentSettings,
    LoginRequest,
    RegisterUserRequest,
    UpdateConsentRequest,
    UserProfile,
)
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import InMemoryStore, UserRecord


class UserService:
    """Registration, login, profile reads, and consent updates."""

    def __init__(self, store: InMemoryStore, settings: Settings) -> None:
        """Bind the service to shared storage and settings.

        Args:
            store: Injected storage connections.
            settings: Application settings with the JWT secret.
        """

        self._store = store
        self._settings = settings

    def _find_by_email(self, email: str) -> UserRecord | None:
        """Return the record for one email address, if registered.

        Args:
            email: Lowercased account email.

        Returns:
            The stored record, or ``None`` when unregistered.
        """

        for record in self._store.users.values():
            if record.email == email:
                return record
        return None

    def _profile(self, record: UserRecord) -> UserProfile:
        """Build the public profile for one record.

        Args:
            record: Stored account record.

        Returns:
            The profile without the password hash.
        """

        return UserProfile(
            user_id=record.user_id,
            email=record.email,
            role=record.role,
            display_name=record.display_name,
            created_at=record.created_at,
        )

    def _issue_session(self, record: UserRecord) -> AuthSession:
        """Issue an access token for one account.

        Args:
            record: Stored account record.

        Returns:
            The auth session with a fresh JWT.
        """

        actor = AuthenticatedActor(
            user_id=record.user_id,
            role=record.role,
            display_name=record.display_name,
        )
        return AuthSession(
            user=self._profile(record),
            access_token=issue_access_token(self._settings, actor),
        )

    def register(self, request: RegisterUserRequest) -> AuthSession:
        """Register one new account and issue its first access token.

        Args:
            request: Validated registration payload.

        Returns:
            The created profile and its access token.

        Raises:
            AppError: ``duplicate`` when the email is already registered.
        """

        if self._find_by_email(request.email) is not None:
            raise AppError(
                ErrorCode.DUPLICATE,
                "An account with this email already exists.",
                details={"email": request.email},
            )
        record = UserRecord(
            user_id=f"user_{uuid4().hex}",
            email=request.email,
            password_hash=hash_password(request.password),
            role=request.role,
            display_name=request.display_name,
            created_at=utc_now_iso(),
            consent=ConsentSettings(),
        )
        self._store.users[record.user_id] = record
        return self._issue_session(record)

    def login(self, request: LoginRequest) -> AuthSession:
        """Verify credentials and issue an access token.

        Args:
            request: Validated login payload.

        Returns:
            The profile and a fresh access token.

        Raises:
            AppError: ``unauthorized`` for unknown accounts or wrong passwords.
        """

        record = self._find_by_email(request.email)
        if record is None or not verify_password(request.password, record.password_hash):
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Email or password is incorrect.",
            )
        return self._issue_session(record)

    def _require_record(self, actor: AuthenticatedActor) -> UserRecord:
        """Return the stored record for the actor or fail typed.

        Args:
            actor: Authenticated actor from a verified JWT.

        Returns:
            The stored account record.

        Raises:
            AppError: ``not_found`` when the account no longer exists.
        """

        record = self._store.users.get(actor.user_id)
        if record is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Account was not found.",
                details={"user_id": actor.user_id},
            )
        return record

    def read_profile(self, actor: AuthenticatedActor) -> UserProfile:
        """Return the stored profile for the authenticated actor.

        Args:
            actor: Authenticated actor from a verified JWT.

        Returns:
            The account's public profile.
        """

        return self._profile(self._require_record(actor))

    def read_consent(self, actor: AuthenticatedActor) -> ConsentSettings:
        """Return the stored consent settings for the actor.

        Args:
            actor: Authenticated actor from a verified JWT.

        Returns:
            The account's consent settings.
        """

        return self._require_record(actor).consent

    def update_consent(
        self, actor: AuthenticatedActor, request: UpdateConsentRequest
    ) -> ConsentSettings:
        """Store one consent choice for the actor.

        Args:
            actor: Authenticated actor from a verified JWT.
            request: New consent value.

        Returns:
            The updated consent settings.
        """

        record = self._require_record(actor)
        record.consent = ConsentSettings(
            analytics_opt_in=request.analytics_opt_in,
            updated_at=utc_now_iso(),
        )
        return record.consent

    def is_registered_professor(self, user_id: str) -> bool:
        """Return whether the user is a registered professor account.

        Args:
            user_id: Account to inspect.

        Returns:
            ``True`` when the account exists with the professor role.
        """

        record = self._store.users.get(user_id)
        return record is not None and record.role == ROLE_PROFESSOR
