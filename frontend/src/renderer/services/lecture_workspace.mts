import {
  addJoinedSession,
  addRecoveryCard,
  addSubmittedEvent,
  getBackendSessionState,
  setActiveSession,
  setAvailableSessions,
  setBackendCourses,
  setBackendLectures,
  setBackendSessions,
  setBackendState,
  setBackendUser,
  setConsent,
  setEnrollments,
  setParticipantCount,
  setProfessorReport,
  setProfessorReportForSession,
  setSelectedSession,
  setTranscriptChunks,
  setZoomRtmsStatus,
} from './backend_session_state.mjs';

const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'The Bloom service could not complete that request.';

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
  if (latest) {
    await Promise.all([
      loadProfessorReport(latest.session_id),
      latest.status === 'active' ? loadZoomRtmsStatus(latest.session_id) : Promise.resolve(),
    ]);
  }
}

/**
 * Reads the Zoom realtime transcript status for one session.
 *
 * Failures are swallowed into a `failed` status so a Zoom outage never blocks
 * the surrounding lecture page from rendering.
 *
 * @param sessionId - Session whose Zoom link should be read.
 */
export async function loadZoomRtmsStatus(sessionId: string): Promise<void> {
  try {
    setZoomRtmsStatus(await window.backend.readZoomStatus(sessionId));
  } catch (error) {
    setZoomRtmsStatus({ session_id: sessionId, status: 'failed', last_error: errorMessage(error) });
  }
}

/**
 * Binds a Zoom meeting to a session so its RTMS transcript feeds the lecture.
 *
 * After linking, the session is re-read so the stored `zoom_join_url` (derived
 * server-side from a pasted link) reaches the professor's Join button.
 *
 * @param sessionId - Session owned by the current professor.
 * @param request - Zoom join link and/or meeting number from the meeting invite.
 * @returns The status returned by the backend after linking.
 * @throws Error When the backend rejects the link (not owner, Zoom not configured,
 *   invalid join URL, ...).
 */
export async function linkZoomMeeting(
  sessionId: string,
  request: StartZoomRtmsRequest,
): Promise<ZoomRtmsStatus> {
  const status = await window.backend.startZoomRtms(sessionId, request);
  setZoomRtmsStatus(status);
  const session = await window.backend.readSession(sessionId);
  const state = getBackendSessionState();
  if (state.selectedSession?.session_id === sessionId) setSelectedSession(session);
  if (state.activeSession?.session_id === sessionId) setActiveSession(session);
  return status;
}

/**
 * Finds the validated Zoom join URL for a session known to the renderer.
 *
 * @param sessionId - Session the student or professor wants to join.
 * @returns The join URL, or null when the session is unknown or has no link.
 */
export function findZoomJoinUrl(sessionId: string): string | null {
  const state = getBackendSessionState();
  const candidates: (LectureSession | null | undefined)[] = [
    state.activeSession,
    state.selectedSession,
    ...state.availableSessions.map((entry) => entry.session),
    ...state.joinedSessions,
  ];
  const match = candidates.find((session) => session?.session_id === sessionId);
  return match?.zoom_join_url ?? null;
}

/**
 * Asks the Electron main process to open a session's Zoom meeting.
 *
 * The renderer never opens URLs itself; the main process re-validates the Zoom
 * host allowlist and prefers the desktop client deep link.
 *
 * @param sessionId - Session whose join link should be opened.
 * @returns Where the meeting opened, or `rejected` when no valid link exists.
 */
export async function openZoomMeeting(sessionId: string): Promise<ZoomJoinOutcome> {
  const joinUrl = findZoomJoinUrl(sessionId);
  if (!joinUrl) return 'rejected';
  return window.bloomDesktop.openZoomJoinLink(joinUrl);
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
  await joinResolvedSession(session);
}

/**
 * Registers the student in an already-resolved live session (one-click join).
 *
 * Side effects: marks the session active, records the participant count, and
 * refreshes enrollments because the backend auto-enrolls on first join.
 *
 * @param session - Active session matched by enrollment or Zoom meeting.
 */
export async function joinResolvedSession(session: LectureSession): Promise<void> {
  const participant = await window.backend.joinSession(session.session_id);
  addJoinedSession(session);
  setActiveSession(session);
  setParticipantCount(participant.participant_count);
  await Promise.allSettled([loadEnrollments(), refreshAvailableSessions()]);
}

/** Loads the student's course enrollments. */
export async function loadEnrollments(): Promise<void> {
  setEnrollments(await window.backend.listEnrollments());
}

/**
 * Enrolls the student in a course by its code so future lectures are detected.
 *
 * @param courseCode - Raw course code entered by the student.
 * @throws BackendRequestError when the code is unknown or the actor is not a student.
 */
export async function enrollInCourse(courseCode: string): Promise<void> {
  await window.backend.enrollInCourse({ course_code: courseCode.trim() });
  await Promise.all([loadEnrollments(), refreshAvailableSessions()]);
}

/** Sets whether a course's live lectures are joined without a prompt. */
export async function setEnrollmentAutoJoin(
  enrollmentId: string,
  isAutoJoinEnabled: boolean,
): Promise<void> {
  await window.backend.updateEnrollment(enrollmentId, { is_auto_join_enabled: isAutoJoinEnabled });
  await loadEnrollments();
}

/** Removes a course enrollment so its lectures stop being detected. */
export async function leaveCourse(enrollmentId: string): Promise<void> {
  await window.backend.leaveCourse(enrollmentId);
  await Promise.all([loadEnrollments(), refreshAvailableSessions()]);
}

/**
 * Reports whether the locally active session is still running on the backend.
 *
 * The local copy of the active session never learns that the professor ended
 * it, so auto-join re-reads its status before switching lectures. A failed read
 * counts as live so a flaky network never yanks a student out of a lecture.
 *
 * @returns False when there is no active session or the backend reports it ended.
 */
async function isActiveSessionStillLive(): Promise<boolean> {
  const active = getBackendSessionState().activeSession;
  if (!active) return false;
  try {
    const refreshed = await window.backend.readSession(active.session_id);
    if (refreshed.status === 'active') return true;
    setActiveSession(refreshed);
    return false;
  } catch {
    return true;
  }
}

/**
 * Refreshes live sessions the student can join without a code and auto-joins
 * any whose enrollment opted into zero-click joining. An active session that
 * the professor has since ended does not block auto-joining the next lecture.
 *
 * @param zoomMeetingId - Locally detected Zoom meeting id, when the platform exposes one.
 * @returns The refreshed available sessions.
 */
export async function refreshAvailableSessions(
  zoomMeetingId: string | null = null,
): Promise<AvailableLectureSession[]> {
  const available = await window.backend.listAvailableSessions(zoomMeetingId);
  setAvailableSessions(available);
  const autoJoin = available.find((entry) => entry.is_auto_join_enabled && !entry.is_joined);
  if (autoJoin && !(await isActiveSessionStillLive())) {
    const participant = await window.backend.joinSession(autoJoin.session.session_id);
    addJoinedSession(autoJoin.session);
    setActiveSession(autoJoin.session);
    setParticipantCount(participant.participant_count);
    setAvailableSessions(
      available.map((entry) =>
        entry.session.session_id === autoJoin.session.session_id
          ? { ...entry, is_joined: true }
          : entry,
      ),
    );
  }
  return getBackendSessionState().availableSessions;
}

/** Loads enrollments and live sessions for the student dashboard. */
export async function loadStudentWorkspace(): Promise<void> {
  await Promise.all([loadEnrollments(), refreshAvailableSessions()]);
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
