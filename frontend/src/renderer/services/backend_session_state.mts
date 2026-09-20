/** In-memory renderer state for the current authenticated Bloom run. */

export type BackendSessionState = {
  user: UserProfile | null;
  courses: Course[];
  lecturesByCourse: Record<string, Lecture[]>;
  sessions: LectureSession[];
  sessionsByLecture: Record<string, LectureSession[]>;
  activeSession: LectureSession | null;
  selectedSession: LectureSession | null;
  zoomRunning: boolean;
  zoomBannerDismissed: boolean;
  joinedSessions: LectureSession[];
  enrollments: CourseEnrollment[];
  availableSessions: AvailableLectureSession[];
  dismissedAvailableSessionIds: string[];
  participantCount: number | null;
  submittedEvents: SignalEvent[];
  transcriptChunks: TranscriptChunk[];
  zoomRtmsStatusBySession: Record<string, ZoomRtmsStatus>;
  liveEventsConnection: SessionEventsConnectionPayload | null;
  recoveryCards: RecoveryCard[];
  professorSummary: ProfessorSummary | null;
  professorMetrics: ProfessorMetrics | null;
  professorSummariesBySession: Record<string, ProfessorSummary>;
  professorMetricsBySession: Record<string, ProfessorMetrics>;
  professorSummaryError: string | null;
  professorMetricsError: string | null;
  externalTextConsentGranted: boolean;
  externalTextConsentNote: string | null;
  cameraSignalsEnabled: boolean;
  cameraSignalsStatus: 'off' | 'watching' | 'error';
  cameraSignalsError: string | null;
  pendingDriftPrompt: SignalEvent | null;
  consent: ConsentSettings | null;
  backendState: 'checking' | 'connected' | 'offline';
  routeError: string | null;
  routeLoading: boolean;
};

const state: BackendSessionState = {
  user: null,
  courses: [],
  lecturesByCourse: {},
  sessions: [],
  sessionsByLecture: {},
  activeSession: null,
  selectedSession: null,
  zoomRunning: false,
  zoomBannerDismissed: false,
  joinedSessions: [],
  enrollments: [],
  availableSessions: [],
  dismissedAvailableSessionIds: [],
  participantCount: null,
  submittedEvents: [],
  transcriptChunks: [],
  zoomRtmsStatusBySession: {},
  liveEventsConnection: null,
  recoveryCards: [],
  professorSummary: null,
  professorMetrics: null,
  professorSummariesBySession: {},
  professorMetricsBySession: {},
  professorSummaryError: null,
  professorMetricsError: null,
  externalTextConsentGranted: false,
  externalTextConsentNote: null,
  cameraSignalsEnabled: false,
  cameraSignalsStatus: 'off',
  cameraSignalsError: null,
  pendingDriftPrompt: null,
  consent: null,
  backendState: 'checking',
  routeError: null,
  routeLoading: false,
};

/** Returns the live in-memory renderer state. */
export function getBackendSessionState(): BackendSessionState {
  return state;
}

/** Replaces the authenticated user without persisting credentials or profile data. */
export function setBackendUser(user: UserProfile | null): void {
  state.user = user;
}

/** Stores courses returned by the backend. */
export function setBackendCourses(courses: Course[]): void {
  state.courses = courses;
}

/** Stores lectures grouped by course identifier. */
export function setBackendLectures(courseId: string, lectures: Lecture[]): void {
  state.lecturesByCourse[courseId] = lectures;
}

/** Stores owned sessions and indexes them by lecture identifier. */
export function setBackendSessions(sessions: LectureSession[]): void {
  state.sessions = sessions;
  state.sessionsByLecture = sessions.reduce<Record<string, LectureSession[]>>(
    (byLecture, session) => {
      (byLecture[session.lecture_id] ??= []).push(session);
      return byLecture;
    },
    {},
  );
}

/** Stores the current lecture session. */
export function setActiveSession(session: LectureSession | null): void {
  state.activeSession = session;
  if (!session) {
    state.cameraSignalsEnabled = false;
    state.cameraSignalsStatus = 'off';
    state.cameraSignalsError = null;
    state.pendingDriftPrompt = null;
  }
}

/** Stores the session selected by an educator lecture route. */
export function setSelectedSession(session: LectureSession | null): void {
  state.selectedSession = session;
}

/**
 * Stores whether the local Zoom process is currently detected.
 *
 * @param zoomRunning - Whether a local Zoom process is running.
 * @returns Nothing.
 */
export function setZoomRunning(zoomRunning: boolean): void {
  state.zoomRunning = zoomRunning;
}

/**
 * Controls whether the current Zoom reminder is visible.
 *
 * @param dismissed - Whether the reminder should be hidden.
 * @returns Nothing.
 */
export function setZoomBannerDismissed(dismissed: boolean): void {
  state.zoomBannerDismissed = dismissed;
}

/** Adds a joined session to the current renderer run. */
export function addJoinedSession(session: LectureSession): void {
  if (!state.joinedSessions.some((candidate) => candidate.session_id === session.session_id)) {
    state.joinedSessions.push(session);
  }
  state.activeSession = session;
}

/** Stores the student's course enrollments, newest first. */
export function setEnrollments(enrollments: CourseEnrollment[]): void {
  state.enrollments = enrollments;
}

/** Stores live sessions the student can join with one click. */
export function setAvailableSessions(sessions: AvailableLectureSession[]): void {
  state.availableSessions = sessions;
  const liveIds = new Set(sessions.map((entry) => entry.session.session_id));
  state.dismissedAvailableSessionIds = state.dismissedAvailableSessionIds.filter((id) =>
    liveIds.has(id),
  );
}

/** Hides one live-lecture prompt until that session ends. */
export function dismissAvailableSession(sessionId: string): void {
  if (!state.dismissedAvailableSessionIds.includes(sessionId)) {
    state.dismissedAvailableSessionIds.push(sessionId);
  }
}

/** Updates the current participant count. */
export function setParticipantCount(participantCount: number | null): void {
  state.participantCount = participantCount;
}

/** Adds one submitted event to the current renderer run. */
export function addSubmittedEvent(event: SignalEvent): void {
  state.submittedEvents.push(event);
}

/** Stores transcript chunks read for the active lecture. */
export function setTranscriptChunks(chunks: TranscriptChunk[]): void {
  state.transcriptChunks = chunks;
}

/**
 * Merges one live transcript chunk into the ordered transcript.
 *
 * Mirrors the backend revision rules: a chunk with the same `chunk_id` replaces
 * the stored copy only when its revision is equal or higher, and the result
 * stays sorted by `start_ms`.
 *
 * @param chunk - Chunk delivered by a `transcript.chunk.created` event.
 * @returns True when the transcript changed.
 */
export function upsertTranscriptChunk(chunk: TranscriptChunk): boolean {
  const existingIndex = state.transcriptChunks.findIndex(
    (candidate) => candidate.chunk_id === chunk.chunk_id,
  );
  if (existingIndex >= 0) {
    const existing = state.transcriptChunks[existingIndex];
    if ((existing.revision ?? 1) > (chunk.revision ?? 1)) return false;
    state.transcriptChunks[existingIndex] = chunk;
  } else {
    state.transcriptChunks.push(chunk);
  }
  state.transcriptChunks.sort((left, right) => left.start_ms - right.start_ms);
  return true;
}

/** Stores the Zoom realtime transcript status for one session. */
export function setZoomRtmsStatus(status: ZoomRtmsStatus): void {
  state.zoomRtmsStatusBySession[status.session_id] = status;
}

/** Records the latest connection state of the live session event stream. */
export function setLiveEventsConnection(payload: SessionEventsConnectionPayload | null): void {
  state.liveEventsConnection = payload;
}

/** Adds one private recovery card to the current renderer run. */
export function addRecoveryCard(card: RecoveryCard): void {
  state.recoveryCards.push(card);
}

/** Stores the latest professor summary and metrics. */
export function setProfessorReport(
  summary: ProfessorSummary | null,
  metrics: ProfessorMetrics | null,
  summaryError: string | null = null,
  metricsError: string | null = null,
): void {
  state.professorSummary = summary;
  state.professorMetrics = metrics;
  state.professorSummaryError = summaryError;
  state.professorMetricsError = metricsError;
}

/** Stores one session's professor report for aggregate educator views. */
export function setProfessorReportForSession(
  sessionId: string,
  summary: ProfessorSummary | null,
  metrics: ProfessorMetrics | null,
): void {
  if (summary) state.professorSummariesBySession[sessionId] = summary;
  if (metrics) state.professorMetricsBySession[sessionId] = metrics;
}

/** Stores the current session's provider-specific external-text consent. */
export function setExternalTextConsentGranted(granted: boolean): void {
  state.externalTextConsentGranted = granted;
}

/** Stores an explanatory message for the external-text consent control. */
export function setExternalTextConsentNote(note: string | null): void {
  state.externalTextConsentNote = note;
}

/** Stores whether local camera drift detection is enabled. */
export function setCameraSignalsEnabled(enabled: boolean): void {
  state.cameraSignalsEnabled = enabled;
}

/** Stores the local camera monitor status and optional error. */
export function setCameraSignalsStatus(
  status: BackendSessionState['cameraSignalsStatus'],
  error: string | null = null,
): void {
  state.cameraSignalsStatus = status;
  state.cameraSignalsError = error;
}

/** Stores the latest local drift event awaiting a recovery-card choice. */
export function setPendingDriftPrompt(event: SignalEvent | null): void {
  state.pendingDriftPrompt = event;
}

/** Stores the account's consent settings. */
export function setConsent(consent: ConsentSettings | null): void {
  state.consent = consent;
}

/** Marks whether the backend service is reachable. */
export function setBackendState(backendState: BackendSessionState['backendState']): void {
  state.backendState = backendState;
}

/** Stores a route-scoped backend error for honest rendering. */
export function setRouteError(routeError: string | null): void {
  state.routeError = routeError;
}

/** Marks a route load as active or finished. */
export function setRouteLoading(routeLoading: boolean): void {
  state.routeLoading = routeLoading;
}

/** Clears authenticated, session-scoped state after logout. */
export function clearBackendSessionState(): void {
  state.user = null;
  state.courses = [];
  state.lecturesByCourse = {};
  state.sessions = [];
  state.sessionsByLecture = {};
  state.activeSession = null;
  state.selectedSession = null;
  state.zoomRunning = false;
  state.zoomBannerDismissed = false;
  state.joinedSessions = [];
  state.enrollments = [];
  state.availableSessions = [];
  state.dismissedAvailableSessionIds = [];
  state.participantCount = null;
  state.submittedEvents = [];
  state.transcriptChunks = [];
  state.zoomRtmsStatusBySession = {};
  state.liveEventsConnection = null;
  state.recoveryCards = [];
  state.professorSummary = null;
  state.professorMetrics = null;
  state.professorSummariesBySession = {};
  state.professorMetricsBySession = {};
  state.professorSummaryError = null;
  state.professorMetricsError = null;
  state.externalTextConsentGranted = false;
  state.externalTextConsentNote = null;
  state.cameraSignalsEnabled = false;
  state.cameraSignalsStatus = 'off';
  state.cameraSignalsError = null;
  state.pendingDriftPrompt = null;
  state.consent = null;
  state.backendState = 'checking';
  state.routeError = null;
  state.routeLoading = false;
}
