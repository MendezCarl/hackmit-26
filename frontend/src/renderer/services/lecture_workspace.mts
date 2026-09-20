import {
  addJoinedSession,
  addRecoveryCard,
  addSubmittedEvent,
  getBackendSessionState,
  setActiveSession,
  setBackendCourses,
  setBackendLectures,
  setBackendSessions,
  setBackendState,
  setBackendUser,
  setConsent,
  setParticipantCount,
  setProfessorReport,
  setProfessorReportForSession,
  setSelectedSession,
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
  window.bloomDesktop.setRole(user.role === 'professor' ? 'professor' : 'student');
  setConsent(consent);
}

/** Loads professor-owned courses and their lectures. */
export async function loadEducatorWorkspace(): Promise<void> {
  const [courses, sessions] = await Promise.all([
    window.backend.listCourses(),
    window.backend.listSessions(),
  ]);
  setBackendCourses(courses);
  await Promise.all(
    courses.map(async (course) => {
      setBackendLectures(course.course_id, await window.backend.listLectures(course.course_id));
    }),
  );
  setBackendSessions(sessions);
  await Promise.all(sessions.slice(0, 5).map((session) => loadProfessorReport(session.session_id)));
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
  setProfessorReportForSession(sessionId, summary, metrics);
}

/** Loads one course's lectures and sessions for its detail page. */
export async function loadCourseWorkspace(courseId: string): Promise<void> {
  const courses = getBackendSessionState().courses;
  if (!courses.some((course) => course.course_id === courseId)) {
    setBackendCourses(await window.backend.listCourses());
  }
  const [lectures, sessions] = await Promise.all([
    window.backend.listLectures(courseId),
    window.backend.listSessions({ course_id: courseId }),
  ]);
  setBackendLectures(courseId, lectures);
  setBackendSessions(sessions);
}

/** Loads one lecture's sessions and latest available professor report. */
export async function loadLectureWorkspace(lectureId: string): Promise<void> {
  const sessions = await window.backend.listSessions({ lecture_id: lectureId });
  setBackendSessions(sessions);
  let courses = getBackendSessionState().courses;
  if (!courses.length) {
    courses = await window.backend.listCourses();
    setBackendCourses(courses);
  }
  if (!Object.values(getBackendSessionState().lecturesByCourse).flat().some((lecture) => lecture.lecture_id === lectureId)) {
    await Promise.all(
      courses.map(async (course) => {
        setBackendLectures(course.course_id, await window.backend.listLectures(course.course_id));
      }),
    );
  }
  const latest = sessions[0] ?? null;
  setSelectedSession(latest);
  if (latest) await loadProfessorReport(latest.session_id);
}

/** Loads transcript excerpts for the active student session. */
export async function loadTranscriptWorkspace(sessionId: string, endMs: number): Promise<void> {
  const response = await window.backend.readTranscript(sessionId, 0, Math.max(1, endMs));
  setTranscriptChunks(response.chunks);
}

/** Resolves a human-entered code and joins its student lecture session.
 *
 * @param joinCode - Raw code entered by the student.
 */
export async function joinLectureSession(joinCode: string): Promise<void> {
  const session = await window.backend.resolveJoinCode(joinCode);
  const participant = await window.backend.joinSession(session.session_id);
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
