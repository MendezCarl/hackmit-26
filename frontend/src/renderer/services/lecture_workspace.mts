import {
  addJoinedSession,
  addRecoveryCard,
  addSubmittedEvent,
  getBackendSessionState,
  setActiveSession,
  setBackendCourses,
  setBackendLectures,
  setBackendState,
  setBackendUser,
  setConsent,
  setParticipantCount,
  setProfessorReport,
  setTranscriptChunks,
} from './backend_session_state.mjs';

const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'The local service could not complete that request.';

/** Loads the authenticated profile and account consent. */
export async function loadAccountWorkspace(): Promise<void> {
  const [user, consent] = await Promise.all([
    window.backend.readMe(),
    window.backend.readConsent(),
  ]);
  setBackendUser(user);
  setConsent(consent);
}

/** Loads professor-owned courses and their lectures. */
export async function loadEducatorWorkspace(): Promise<void> {
  const courses = await window.backend.listCourses();
  setBackendCourses(courses);
  await Promise.all(
    courses.map(async (course) => {
      setBackendLectures(course.course_id, await window.backend.listLectures(course.course_id));
    }),
  );
}

/** Loads professor summary and metrics for the active ended session. */
export async function loadProfessorReport(sessionId: string): Promise<void> {
  const [summaryResult, metricsResult] = await Promise.allSettled([
    window.backend.readProfessorSummary(sessionId),
    window.backend.readProfessorMetrics(sessionId),
  ]);
  const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null;
  const metrics = metricsResult.status === 'fulfilled' ? metricsResult.value : null;
  setProfessorReport(
    summary,
    metrics,
    summaryResult.status === 'rejected' ? errorMessage(summaryResult.reason) : null,
    metricsResult.status === 'rejected' ? errorMessage(metricsResult.reason) : null,
  );
}

/** Loads transcript excerpts for the active student session. */
export async function loadTranscriptWorkspace(sessionId: string, endMs: number): Promise<void> {
  const response = await window.backend.readTranscript(sessionId, 0, Math.max(1, endMs));
  setTranscriptChunks(response.chunks);
}

/** Joins and reads one student lecture session. */
export async function joinLectureSession(sessionId: string): Promise<void> {
  const participant = await window.backend.joinSession(sessionId);
  const session = await window.backend.readSession(sessionId);
  addJoinedSession(session);
  setActiveSession(session);
  setParticipantCount(participant.participant_count);
}

/** Checks backend availability without replacing fixture content. */
export async function checkBackendHealth(): Promise<void> {
  try {
    await window.backend.health();
    setBackendState('connected');
  } catch {
    setBackendState('offline');
  }
}

/** Records a personal event after a successful backend ingestion. */
export function recordSubmittedEvent(event: SignalEvent): void {
  addSubmittedEvent(event);
}

/** Stores a completed personal recovery card. */
export function recordRecoveryCard(card: RecoveryCard): void {
  addRecoveryCard(card);
}

/** Returns current state to callers that need to build a route model. */
export function readWorkspaceState(): ReturnType<typeof getBackendSessionState> {
  return getBackendSessionState();
}
