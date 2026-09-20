"""Recovery orchestration: context windows, jobs, caching, and cost recording.

Recovery is personal and authorization-scoped: cache keys include the
requesting user, session, effective interval, transcript revision, model,
prompt version, and output schema version. A cache hit avoids an additional
generation call; it is never counted as provider savings.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.access import (
    SESSION_ROLE_COURSE_PROFESSOR,
    SESSION_ROLE_OWNER,
    SessionAccess,
)
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.models import (
    ContextWindow,
    CostMetrics,
    CreateRecoveryJobRequest,
    JobFailure,
    JobFailureReason,
    JobStatus,
    RecoveryCard,
    RecoveryJob,
)
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.cost.ledger import CostLedger
from app.recovery.cache import InMemoryRecoveryCache, build_cache_key
from app.recovery.generator import RecoveryGenerator
from app.recovery.intervals import build_context_interval
from app.signals.service import SignalService
from app.storage.in_memory import CardRecord, InMemoryStore
from app.transcript.repository import TimelineReader
from app.ws.publisher import EventPublisher

RECOVERY_JOB_STARTED = "recovery_job.started"
RECOVERY_CARD_COMPLETED = "recovery_card.completed"
RECOVERY_CARD_FAILED = "recovery_card.failed"
CACHE_MISS = "miss"
CACHE_HIT = "hit"
FULL_CONTEXT_BASELINE = "full_context_generation_avoided_estimate"

GENERATOR_ERROR_REASONS: dict[str, JobFailureReason] = {
    "provider_refused": JobFailureReason.PROVIDER_REFUSED,
    "provider_timeout": JobFailureReason.PROVIDER_TIMEOUT,
    "provider_malformed_output": JobFailureReason.PROVIDER_MALFORMED_OUTPUT,
}


class RecoveryService:
    """Recovery jobs: bounded retrieval, generation, caching, and cost."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        timeline_reader: TimelineReader,
        generator: RecoveryGenerator,
        signal_service: SignalService,
        cost_ledger: CostLedger,
        event_publisher: EventPublisher,
    ) -> None:
        """Bind the service to shared dependencies.

        Args:
            store: Injected storage connections.
            settings: Application settings with padding clamps.
            session_access: Shared membership resolver.
            timeline_reader: Frozen timeline interface for context retrieval.
            generator: Recovery generator (deterministic mock by default).
            signal_service: Signals feature used for source-event validation.
            cost_ledger: Ledger recording measured or synthetic usage.
            event_publisher: Publisher for session-scoped typed events.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._timeline_reader = timeline_reader
        self._generator = generator
        self._signal_service = signal_service
        self._cost_ledger = cost_ledger
        self._publisher = event_publisher
        self._cache = InMemoryRecoveryCache(store.recovery_cache)

    def _source_event_intervals(
        self, session_id: str, source_event_ids: list[str]
    ) -> list[tuple[int, int]]:
        """Collect the intervals of the source events grounding one job.

        Args:
            session_id: Session whose events are inspected.
            source_event_ids: Signal events referenced by the job.

        Returns:
            Half-open intervals of the referenced events, within this
            session only; windows never merge across sessions.
        """

        wanted = set(source_event_ids)
        return [
            (record.event.start_ms, record.event.end_ms)
            for record in self._signal_service.list_session_events(session_id)
            if record.event.event_id in wanted
        ]

    def _build_context_window(
        self, session_id: str, start_ms: int, end_ms: int
    ) -> ContextWindow:
        """Retrieve and clamp the padded context window for an interval.

        Padding is clamped to the configured maximum and never crosses the
        lecture-clock origin (0 ms). Only the same authorized session's
        timeline is read, so windows never merge across sessions or scopes.

        Args:
            session_id: Session whose timeline is read.
            start_ms: Requested interval start in ms.
            end_ms: Requested interval end in ms.

        Returns:
            The retrieved context window with final chunks.

        Raises:
            AppError: ``provider_failure`` wrapped as a typed missing-context
                signal handled by the caller for job failure recording.
        """

        padding = min(self._settings.context_padding_ms, self._settings.max_context_padding_ms)
        effective_start_ms = max(0, start_ms - padding)
        effective_end_ms = end_ms + padding
        read = self._timeline_reader.read_window(session_id, effective_start_ms, effective_end_ms)
        return ContextWindow(
            session_id=session_id,
            requested_start_ms=start_ms,
            requested_end_ms=end_ms,
            effective_start_ms=effective_start_ms,
            effective_end_ms=effective_end_ms,
            transcript_revision=read.transcript_revision,
            chunk_ids=read.source_ids,
            chunks=read.chunks,
        )

    def _build_cache_key(
        self,
        actor: AuthenticatedActor,
        window: ContextWindow,
    ) -> str:
        """Build the authorization-scoped cache key for one window."""

        return build_cache_key(
            actor.user_id,
            window.session_id,
            window.effective_start_ms,
            window.effective_end_ms,
            window.transcript_revision,
            self._generator.model,
            self._generator.prompt_version,
            self._generator.output_schema_version,
        )

    def create_job(
        self,
        actor: AuthenticatedActor,
        session_id: str,
        request: CreateRecoveryJobRequest,
        idempotency_key: str | None = None,
    ) -> RecoveryJob:
        """Create and execute one recovery job for an authorized student.

        When an ``Idempotency-Key`` is supplied, a retry of the same request
        returns the original job instead of creating a duplicate.

        Args:
            actor: Requesting owner or participant.
            session_id: Session whose content should be recovered.
            request: Validated recovery request with the missed interval.
            idempotency_key: Optional caller-supplied idempotency key,
                scoped to the requesting user and session.

        Returns:
            The completed or failed job.

        Raises:
            AppError: ``forbidden`` for professors and cross-user requests,
                ``validation_failed`` for unknown source events.
        """

        scoped_idempotency_key: str | None = None
        if idempotency_key:
            scoped_idempotency_key = f"{actor.user_id}|{session_id}|{idempotency_key}"
            existing_job_id = self._store.recovery_idempotency.get(
                scoped_idempotency_key
            )
            if existing_job_id is not None:
                existing_job = self._store.recovery_jobs.get(existing_job_id)
                if existing_job is not None:
                    return existing_job

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role == SESSION_ROLE_COURSE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Professors cannot request personal recovery cards.",
            )

        known_event_ids = set(self._signal_service.list_session_event_ids(session_id))
        for event_id in request.source_event_ids:
            if event_id not in known_event_ids:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "Source event was not found in this session.",
                    details={"source_event_id": event_id},
                )

        job = RecoveryJob(
            job_id=f"job_{uuid4().hex}",
            session_id=session_id,
            status=JobStatus.QUEUED,
            requested_start_ms=request.start_ms,
            requested_end_ms=request.end_ms,
            created_at=utc_now_iso(),
        )
        self._store.recovery_jobs[job.job_id] = job
        if scoped_idempotency_key is not None:
            self._store.recovery_idempotency[scoped_idempotency_key] = job.job_id
        self._publisher.publish(
            self._publisher.build_envelope(
                session_id,
                RECOVERY_JOB_STARTED,
                {"job_id": job.job_id},
            )
        )
        return self._execute_job(job, actor, request.source_event_ids)

    def _execute_job(
        self,
        job: RecoveryJob,
        actor: AuthenticatedActor,
        source_event_ids: list[str],
    ) -> RecoveryJob:
        """Execute one job synchronously in the current mock-worker mode.

        Args:
            job: The queued job to execute.
            actor: Requesting user for cache scoping and card ownership.
            source_event_ids: Signal events grounding the card.

        Returns:
            The completed, failed, or cache-hit job.
        """

        job.status = JobStatus.RUNNING
        context_start_ms, context_end_ms = build_context_interval(
            (job.requested_start_ms, job.requested_end_ms),
            self._source_event_intervals(job.session_id, source_event_ids),
        )
        try:
            window = self._build_context_window(
                job.session_id, context_start_ms, context_end_ms
            )
        except AppError:
            return self._fail_job(
                job,
                JobFailureReason.MISSING_TRANSCRIPT_CONTEXT,
                "No final transcript is available near that interval yet; the "
                "card was not generated. Please retry after transcript chunks "
                "arrive or widen the interval.",
            )

        if not window.chunks:
            return self._fail_job(
                job,
                JobFailureReason.MISSING_TRANSCRIPT_CONTEXT,
                "No final transcript is available near that interval yet; the "
                "card was not generated. Please retry after transcript chunks "
                "arrive or widen the interval.",
            )

        cache_key = self._build_cache_key(actor, window)
        cached_card_id = self._cache.get(cache_key)
        if cached_card_id is not None and cached_card_id in self._store.recovery_cards:
            job.status = JobStatus.COMPLETED
            job.card_id = cached_card_id
            job.cache_status = CACHE_HIT
            job.completed_at = utc_now_iso()
            cached_record = self._store.recovery_cards[cached_card_id]
            self._record_cost(
                job,
                cache_hit=True,
                data_label=cached_record.card.model_metadata.data_label,
            )
            self._publisher.publish(
                self._publisher.build_envelope(
                    job.session_id,
                    RECOVERY_CARD_COMPLETED,
                    {"job_id": job.job_id, "card_id": cached_card_id},
                )
            )
            return job

        try:
            card, metadata = self._generator.generate(
                self._store.sessions[job.session_id], window
            )
        except AppError as exc:
            reason = GENERATOR_ERROR_REASONS.get(exc.code.value, JobFailureReason.PROVIDER_REFUSED)
            return self._fail_job(job, reason, exc.message)
        except ValueError:
            return self._fail_job(
                job,
                JobFailureReason.PROVIDER_MALFORMED_OUTPUT,
                "The provider returned an invalid recovery card.",
            )

        card_id = f"card_{uuid4().hex}"
        card = card.model_copy(
            update={
                "card_id": card_id,
                "source_event_ids": list(source_event_ids),
                "created_at": utc_now_iso(),
            }
        )
        self._store.recovery_cards[card_id] = CardRecord(
            card=card, owner_user_id=actor.user_id
        )
        self._cache.set(cache_key, card_id)
        job.status = JobStatus.COMPLETED
        job.card_id = card_id
        job.cache_status = CACHE_MISS
        job.completed_at = utc_now_iso()
        self._record_cost(job, cache_hit=False, metadata=metadata)
        self._publisher.publish(
            self._publisher.build_envelope(
                job.session_id,
                RECOVERY_CARD_COMPLETED,
                {"job_id": job.job_id, "card_id": card_id},
            )
        )
        return job

    def _fail_job(
        self, job: RecoveryJob, reason: JobFailureReason, message: str
    ) -> RecoveryJob:
        """Mark one job failed with a typed, recoverable reason.

        Args:
            job: The running job to fail.
            reason: Stable typed failure reason.
            message: Compassionate human-readable explanation.

        Returns:
            The failed job.
        """

        job.status = JobStatus.FAILED
        job.failure = JobFailure(reason=reason, message=message)
        job.completed_at = utc_now_iso()
        self._publisher.publish(
            self._publisher.build_envelope(
                job.session_id,
                RECOVERY_CARD_FAILED,
                {"job_id": job.job_id, "reason": reason.value},
            )
        )
        return job

    def _record_cost(
        self,
        job: RecoveryJob,
        cache_hit: bool,
        metadata: object = None,
        data_label: str | None = None,
    ) -> None:
        """Record one usage entry with a truthful provenance label.

        Labels distinguish measured provider usage (real token counts from a
        live response) from synthetic mock usage; cache hits inherit the
        provenance of the card they reuse and record zero usage because no
        generation call occurred.

        Args:
            job: The job the usage belongs to.
            cache_hit: Whether generation was skipped via cache reuse.
            metadata: Provider metadata from the generation call.
            data_label: Optional provenance override for cache-hit entries.
        """

        resolved_data_label = data_label
        if resolved_data_label is None:
            resolved_data_label = (
                getattr(metadata, "data_label", None) if metadata is not None else None
            )
        if resolved_data_label is None:
            resolved_data_label = "synthetic"

        input_token_count = (
            getattr(metadata, "input_token_count", None)
            or getattr(metadata, "input_tokens", None)
            if metadata is not None
            else None
        )
        output_token_count = (
            getattr(metadata, "output_token_count", None)
            or getattr(metadata, "output_tokens", None)
            if metadata is not None
            else None
        )
        if input_token_count is not None and output_token_count is not None:
            if getattr(metadata, "input_token_count", None) is not None:
                input_usage = {"input_tokens": input_token_count}
                output_usage = {"output_tokens": output_token_count}
            else:
                input_usage = {"tokens": input_token_count}
                output_usage = {"tokens": output_token_count}
        else:
            input_usage = {
                "characters": (
                    getattr(metadata, "input_character_count", 0)
                    if metadata is not None
                    else 0
                )
            }
            output_usage = {
                "characters": (
                    getattr(metadata, "output_character_count", 0)
                    if metadata is not None
                    else 0
                )
            }
        self._cost_ledger.record(
            CostMetrics(
                job_id=job.job_id,
                session_id=job.session_id,
                provider_mode=self._settings.provider_mode,
                model=self._generator.model,
                input_usage=input_usage,
                output_usage=output_usage,
                cache_status=CACHE_HIT if cache_hit else CACHE_MISS,
                latency_ms=(
                    getattr(metadata, "latency_ms", 0) if metadata is not None else 0
                ),
                baseline_method=FULL_CONTEXT_BASELINE,
                data_label=resolved_data_label,
            )
        )

    def get_job(
        self, actor: AuthenticatedActor, session_id: str, job_id: str
    ) -> RecoveryJob:
        """Return one recovery job for an authorized session member.

        Args:
            actor: Authenticated owner, participant, or course professor.
            session_id: Session the job belongs to.
            job_id: Job to retrieve.

        Returns:
            The stored job.

        Raises:
            AppError: ``not_found`` when the job is not in this session.
        """

        self._session_access.resolve_membership(actor, session_id)
        job = self._store.recovery_jobs.get(job_id)
        if job is None or job.session_id != session_id:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Recovery job was not found in this session.",
                details={"job_id": job_id},
            )
        return job

    def get_card(
        self, actor: AuthenticatedActor, session_id: str, card_id: str
    ) -> RecoveryCard:
        """Return one card to its owner or the session owner only.

        Args:
            actor: Authenticated requester.
            session_id: Session the card belongs to.
            card_id: Card to retrieve.

        Returns:
            The stored recovery card.

        Raises:
            AppError: ``not_found`` or ``forbidden`` for other users' cards.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        record = self._store.recovery_cards.get(card_id)
        if record is None or record.card.session_id != session_id:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Recovery card was not found in this session.",
                details={"card_id": card_id},
            )
        is_card_owner = record.owner_user_id == actor.user_id
        is_session_owner = (
            membership.session_role == SESSION_ROLE_OWNER
        )
        if not (is_card_owner or is_session_owner):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Recovery cards are personal; only their owner or the session "
                "owner can read this card.",
                details={"card_id": card_id},
            )
        return record.card

    def list_cost_metrics(
        self, actor: AuthenticatedActor, session_id: str
    ) -> list[CostMetrics]:
        """Return usage metrics for the session owner.

        Args:
            actor: Authenticated requester; must be the session owner.
            session_id: Session whose usage is reported.

        Returns:
            Recorded usage entries for the session.

        Raises:
            AppError: ``forbidden`` for anyone but the session owner.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role != SESSION_ROLE_OWNER:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only the session owner can read cost metrics.",
            )
        return self._cost_ledger.for_session(session_id)