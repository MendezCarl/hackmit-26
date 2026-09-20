import {
  buildRouteHash,
  resolveRoute,
  resolveRouteParams,
  type AppRoute,
} from './app/router.mjs';
import { renderPage } from './app/render_page.mjs';
import { renderSelectedMoment } from './components/moment_detail.mjs';
import { describeZoomRtmsStatus } from './components/zoom_live_transcript_panel.mjs';
import { StudentTranscriptPanel } from './features/recovery-cards/student_summary_page.mjs';
import {
  clearBackendSessionState,
  dismissAvailableSession,
  getBackendSessionState,
  setActiveSession,
  setBackendCourses,
  setBackendLectures,
  setBackendState,
  setBackendUser,
  setConsent,
  setCameraSignalsEnabled,
  setCameraSignalsStatus,
  setExternalTextConsentGranted,
  setExternalTextConsentNote,
  setPendingDriftPrompt,
  setRouteError,
  setRouteLoading,
  setZoomBannerDismissed,
  setZoomRunning,
} from './services/backend_session_state.mjs';
import {
  checkBackendHealth,
  enrollInCourse,
  joinLectureSession,
  joinResolvedSession,
  leaveCourse,
  loadAccountWorkspace,
  loadCourseWorkspace,
  loadEducatorWorkspace,
  loadLectureWorkspace,
  loadProfessorReport,
  loadStudentWorkspace,
  loadTranscriptWorkspace,
  loadZoomRtmsStatus,
  linkZoomMeeting,
  applyOverlayRecoveryCard,
  recordRecoveryCard,
  recordSubmittedEvent,
  refreshAvailableSessions,
  setEnrollmentAutoJoin,
} from './services/lecture_workspace.mjs';
import {
  buildMomentsFromEvents,
  buildMomentsFromMetrics,
  buildMomentsFromSummary,
  formatLectureTime,
  sessionDurationMs,
} from './services/lecture_view_models.mjs';
import {
  bindLiveSessionEvents,
  syncLiveSessionSubscription,
} from './services/live_session_events.mjs';
import {
  startStudentCameraMonitor,
  stopStudentCameraMonitor,
} from './services/student_camera_monitor.mjs';

const appRoot = document.querySelector<HTMLElement>('#app');
if (!appRoot) throw new Error('Bloom requires an #app mount element.');

const formErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'The Bloom service could not complete that request.';

const readFormValues = (form: HTMLFormElement): Record<string, string> =>
  Object.fromEntries(
    Array.from(form.elements)
      .filter(
        (element): element is HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement =>
          'name' in element && 'value' in element && Boolean(element.name),
      )
      .map((element) => [element.name, element.value]),
  );

let sessionClockTimer: number | undefined;
let availableSessionsTimer: number | undefined;
let zoomDesktopBound = false;
let cameraMonitorSessionId: string | null = null;

/** How often the student dashboard asks the backend for newly live lectures. */
const AVAILABLE_SESSIONS_POLL_MS = 20_000;

const isStudentDashboardActive = (): boolean =>
  resolveRoute(window.location.hash) === 'student-dashboard' &&
  getBackendSessionState().user?.role === 'student';

/** Stable fingerprint of the live-lecture prompt state, used to skip no-op repaints. */
const availableSessionsFingerprint = (): string => {
  const state = getBackendSessionState();
  return [
    state.activeSession?.session_id ?? '',
    ...state.availableSessions.map((entry) => `${entry.session.session_id}:${entry.is_joined}`),
  ].join('|');
};

/**
 * Re-checks live lectures for the student and repaints only when the prompt set changed.
 * Auto-join (opt-in per course) may switch the active session, so camera state is
 * reconciled through the normal render path.
 */
const pollAvailableSessions = async (): Promise<void> => {
  if (!isStudentDashboardActive()) return;
  const before = availableSessionsFingerprint();
  try {
    await refreshAvailableSessions();
  } catch {
    return;
  }
  if (before !== availableSessionsFingerprint() && isStudentDashboardActive()) renderApplication();
};

const bindAvailableSessionsPolling = (): void => {
  if (availableSessionsTimer !== undefined) window.clearInterval(availableSessionsTimer);
  availableSessionsTimer = undefined;
  if (!isStudentDashboardActive()) return;
  availableSessionsTimer = window.setInterval(
    () => void pollAvailableSessions(),
    AVAILABLE_SESSIONS_POLL_MS,
  );
};

const resetCameraSignalState = (): void => {
  setCameraSignalsEnabled(false);
  setCameraSignalsStatus('off');
  setPendingDriftPrompt(null);
};

const stopCameraForSessionChange = (session: LectureSession | null): void => {
  const sessionId = session?.session_id ?? null;
  if (
    cameraMonitorSessionId &&
    (cameraMonitorSessionId !== sessionId || session?.status !== 'active')
  ) {
    cameraMonitorSessionId = null;
    resetCameraSignalState();
    void stopStudentCameraMonitor();
  }
};

/**
 * Binds timeline marker selection to the current route's live moments.
 *
 * @param route - Route whose moment view model should be rendered.
 */
const bindTimelineInteractions = (route: AppRoute): void => {
  const buttons = document.querySelectorAll<HTMLButtonElement>('[data-moment-id]');
  const state = getBackendSessionState();
  const selectedEducatorSession = route === 'lecture' ? state.selectedSession : null;
  const duration = selectedEducatorSession
    ? sessionDurationMs(selectedEducatorSession)
    : state.activeSession
      ? sessionDurationMs(state.activeSession)
      : 1;
  const moments =
    route === 'educator-summary' && state.professorMetrics
      ? buildMomentsFromMetrics(state.professorMetrics, duration)
      : route === 'educator-summary' && state.professorSummary
        ? buildMomentsFromSummary(state.professorSummary, duration)
        : route === 'lecture' &&
            selectedEducatorSession &&
            state.professorMetricsBySession[selectedEducatorSession.session_id]
          ? buildMomentsFromMetrics(
              state.professorMetricsBySession[selectedEducatorSession.session_id],
              duration,
            )
          : route === 'lecture' &&
              selectedEducatorSession &&
              state.professorSummariesBySession[selectedEducatorSession.session_id]
            ? buildMomentsFromSummary(
                state.professorSummariesBySession[selectedEducatorSession.session_id],
                duration,
              )
        : route === 'student-summary'
          ? buildMomentsFromEvents(state.submittedEvents, duration)
          : [];
  buttons.forEach((button) =>
    button.addEventListener('click', () => {
      const detail = document.querySelector<HTMLElement>('[data-moment-detail]');
      if (!detail) return;
      buttons.forEach((candidate) => candidate.classList.remove('is-selected'));
      button.classList.add('is-selected');
      detail.outerHTML = renderSelectedMoment(
        button.dataset.momentId ?? '',
        route === 'educator-summary' || route === 'lecture' ? 'educator' : 'student',
        moments,
      );
    }),
  );
};

/**
 * Binds the summary and transcript tab controls in the rendered page.
 */
const bindSummaryTabs = (): void => {
  const buttons = document.querySelectorAll<HTMLButtonElement>('[data-tab]');
  const panels = document.querySelectorAll<HTMLElement>('[data-tab-panel]');
  buttons.forEach((button) =>
    button.addEventListener('click', () => {
      const tab = button.dataset.tab;
      buttons.forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle('is-active', active);
        candidate.setAttribute('aria-selected', String(active));
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.tabPanel !== tab;
      });
    }),
  );
};

/**
 * Binds search and status filtering for rendered lecture cards.
 */
const bindLibraryFilters = (): void => {
  const search = document.querySelector<HTMLInputElement>('[data-library-search]');
  const status = document.querySelector<HTMLSelectElement>('[data-library-filter]');
  const cards = document.querySelectorAll<HTMLElement>('[data-lecture-title]');
  const empty = document.querySelector<HTMLElement>('[data-library-empty]');
  if (!search || !status || !empty) return;
  const apply = (): void => {
    const query = search.value.trim().toLowerCase();
    const selected = status.value;
    let visible = 0;
    cards.forEach((card) => {
      const match =
        (card.dataset.lectureTitle ?? '').includes(query) &&
        (selected === 'all' || card.dataset.lectureStatus === selected);
      card.hidden = !match;
      if (match) visible += 1;
    });
    empty.hidden = visible > 0;
  };
  search.addEventListener('input', apply);
  status.addEventListener('change', apply);
};

/**
 * Binds login and registration form actions to the backend session client.
 */
const bindAuthentication = (): void => {
  const form = document.querySelector<HTMLFormElement>('[data-login-form]');
  const toggle = document.querySelector<HTMLButtonElement>('[data-auth-toggle]');
  if (!form || !toggle) return;
  let registration = false;
  toggle.addEventListener('click', () => {
    registration = !registration;
    form.dataset.authMode = registration ? 'register' : 'login';
    document.querySelectorAll<HTMLElement>('[data-register-field]').forEach((field) => {
      field.hidden = !registration;
      field.querySelector('input,select')?.toggleAttribute('required', registration);
    });
    const eyebrow = document.querySelector<HTMLElement>('[data-auth-eyebrow]');
    const title = document.querySelector<HTMLElement>('[data-auth-title]');
    const submit = document.querySelector<HTMLButtonElement>('[data-auth-submit]');
    if (eyebrow) eyebrow.textContent = registration ? 'New to Bloom' : 'Welcome back';
    if (title) title.textContent = registration ? 'Create your Bloom account' : 'Sign in to Bloom';
    if (submit) submit.textContent = registration ? 'Create account' : 'Sign in';
    toggle.textContent = registration ? 'Sign in instead' : 'Create account';
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const values = readFormValues(form);
    const message = form.querySelector<HTMLElement>('[data-form-message]');
    try {
      const session = registration
        ? await window.backend.register({
            display_name: String(values.display_name),
            email: String(values.email),
            password: String(values.password),
            role: String(values.role) as 'student' | 'professor',
          })
        : await window.backend.login({
            email: String(values.email),
            password: String(values.password),
          });
      setBackendUser(session.user);
      setBackendState('connected');
      window.bloomDesktop.setRole(session.user.role === 'professor' ? 'professor' : 'student');
      window.location.hash = buildRouteHash(
        session.user.role === 'professor' ? 'home' : 'student-dashboard',
      );
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
    }
  });
};

/**
 * Binds student session, consent, event, transcript, and recovery actions.
 */
const bindStudentActions = (): void => {
  const dialog = document.querySelector<HTMLDialogElement>('[data-consent-dialog]');
  document
    .querySelector<HTMLButtonElement>('[data-open-consent]')
    ?.addEventListener('click', () => dialog?.showModal());
  dialog?.querySelector('form')?.addEventListener('submit', async (event) => {
    const submitter = (event as SubmitEvent).submitter as HTMLButtonElement | null;
    if (submitter?.value !== 'enable') return;
    const session = getBackendSessionState().activeSession;
    if (!session) return;
    event.preventDefault();
    try {
      await window.backend.updateAggregationConsent(session.session_id, { is_allowed: true });
      dialog.close();
    } catch (error) {
      const message = dialog.querySelector<HTMLElement>('[data-consent-message]');
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  const joinForm = document.querySelector<HTMLFormElement>('[data-join-session-form]');
  joinForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const joinCode = String(new FormData(joinForm).get('join_code') ?? '').trim();
    const message = joinForm.querySelector<HTMLElement>('[data-join-message]');
    try {
      const previousSessionId = getBackendSessionState().activeSession?.session_id;
      await joinLectureSession(joinCode);
      const joinedSession = getBackendSessionState().activeSession;
      if (previousSessionId !== joinedSession?.session_id) {
        stopCameraForSessionChange(joinedSession);
      }
      renderApplication();
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  document.querySelectorAll<HTMLButtonElement>('[data-join-available-session]').forEach((button) =>
    button.addEventListener('click', async () => {
      const sessionId = button.dataset.joinAvailableSession;
      const entry = getBackendSessionState().availableSessions.find(
        (candidate) => candidate.session.session_id === sessionId,
      );
      if (!entry) return;
      const message = button
        .closest('[data-live-lecture-prompt]')
        ?.querySelector<HTMLElement>('[data-live-lecture-message]');
      button.disabled = true;
      try {
        const previousSessionId = getBackendSessionState().activeSession?.session_id;
        await joinResolvedSession(entry.session);
        if (previousSessionId !== entry.session.session_id) {
          stopCameraForSessionChange(entry.session);
        }
        renderApplication();
      } catch (error) {
        button.disabled = false;
        if (message) message.textContent = formErrorMessage(error);
      }
    }),
  );
  document.querySelectorAll<HTMLButtonElement>('[data-dismiss-available-session]').forEach((button) =>
    button.addEventListener('click', () => {
      const sessionId = button.dataset.dismissAvailableSession;
      if (sessionId) dismissAvailableSession(sessionId);
      renderApplication();
    }),
  );
  const enrollForm = document.querySelector<HTMLFormElement>('[data-enroll-course-form]');
  enrollForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const courseCode = String(new FormData(enrollForm).get('course_code') ?? '').trim();
    const message = enrollForm.querySelector<HTMLElement>('[data-enroll-message]');
    try {
      await enrollInCourse(courseCode);
      renderApplication();
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  document.querySelectorAll<HTMLInputElement>('[data-enrollment-auto-join]').forEach((input) =>
    input.addEventListener('change', async () => {
      const enrollmentId = input.dataset.enrollmentAutoJoin;
      if (!enrollmentId) return;
      try {
        await setEnrollmentAutoJoin(enrollmentId, input.checked);
        await refreshAvailableSessions();
        renderApplication();
      } catch (error) {
        input.checked = !input.checked;
        const message = document.querySelector<HTMLElement>('[data-enroll-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    }),
  );
  document.querySelectorAll<HTMLButtonElement>('[data-leave-course]').forEach((button) =>
    button.addEventListener('click', async () => {
      const enrollmentId = button.dataset.leaveCourse;
      if (!enrollmentId) return;
      try {
        await leaveCourse(enrollmentId);
        renderApplication();
      } catch (error) {
        const message = document.querySelector<HTMLElement>('[data-enroll-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    }),
  );
  const session = getBackendSessionState().activeSession;
  document
    .querySelector<HTMLInputElement>('[data-external-text-consent]')
    ?.addEventListener('change', async (event) => {
      const checkbox = event.currentTarget as HTMLInputElement;
      if (!session) return;
      try {
        const status = await window.backend.readApiStatus();
        if (status.recovery_provider === 'mock') {
          setExternalTextConsentGranted(false);
          setExternalTextConsentNote('Local mock provider — no external text is sent');
          renderApplication();
          return;
        }
        const provider = status.recovery_provider;
        if (provider !== 'openai' && provider !== 'meta_muse') {
          throw new Error(`Unsupported recovery provider: ${provider}`);
        }
        const consent = await window.backend.updateExternalTextConsent(session.session_id, {
          provider,
          is_allowed: checkbox.checked,
        });
        setExternalTextConsentGranted(consent.is_allowed);
        setExternalTextConsentNote(null);
        renderApplication();
      } catch (error) {
        setExternalTextConsentNote(formErrorMessage(error));
        renderApplication();
      }
    });
  document
    .querySelector<HTMLInputElement>('[data-camera-signals]')
    ?.addEventListener('change', (event) => {
      const checkbox = event.currentTarget as HTMLInputElement;
      if (!session) return;
      if (!checkbox.checked) {
        cameraMonitorSessionId = null;
        setCameraSignalsEnabled(false);
        setCameraSignalsStatus('off');
        void stopStudentCameraMonitor().finally(renderApplication);
        return;
      }
      setCameraSignalsEnabled(true);
      setCameraSignalsStatus('watching');
      cameraMonitorSessionId = session.session_id;
      renderApplication();
      void startStudentCameraMonitor({
        session,
        onEvents: (events) => {
          const event = events.at(-1);
          if (!event) return;
          setPendingDriftPrompt(event);
          renderApplication();
          window.bloomDesktop.showDriftPrompt({
            session_id: session.session_id,
            event_id: event.event_id,
            start_ms: event.start_ms,
            end_ms: event.end_ms,
          });
        },
        onError: (message) => {
          cameraMonitorSessionId = null;
          setCameraSignalsEnabled(false);
          setCameraSignalsStatus('error', message);
          renderApplication();
        },
      }).catch(() => {
        cameraMonitorSessionId = null;
        setCameraSignalsEnabled(false);
      });
    });
  document
    .querySelector<HTMLButtonElement>('[data-dismiss-drift-prompt]')
    ?.addEventListener('click', () => {
      setPendingDriftPrompt(null);
      renderApplication();
    });
  document
    .querySelector<HTMLButtonElement>('[data-missed-that]')
    ?.addEventListener('click', async () => {
      if (!session) return;
      const now = Math.max(30_000, Date.now() - Date.parse(session.session_clock_origin));
      const event: SignalEvent = {
        event_id: crypto.randomUUID(),
        session_id: session.session_id,
        event_type: 'possible_missed_window',
        start_ms: now - 30_000,
        end_ms: now,
        confidence: 1,
        signals: ['self_report'],
        user_confirmed: true,
      };
      try {
        await window.backend.ingestEvents(session.session_id, {
          lecture_id: session.lecture_id,
          events: [event],
        });
        recordSubmittedEvent(event);
        if (session.mode === 'zoom') renderApplication();
        else window.location.hash = buildRouteHash('student-summary');
      } catch (error) {
        const message = document.querySelector<HTMLElement>('[data-join-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    });
  const transcriptForm = document.querySelector<HTMLFormElement>('[data-transcript-form]');
  transcriptForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!session) return;
    const values = readFormValues(transcriptForm);
    const text = String(values.text ?? '').trim();
    const now = Math.max(1, Date.now() - Date.parse(session.session_clock_origin));
    const previous = getBackendSessionState().transcriptChunks.at(-1)?.end_ms ?? 0;
    const chunk: TranscriptChunk = {
      chunk_id: crypto.randomUUID(),
      session_id: session.session_id,
      source: 'local_transcription',
      start_ms: previous,
      end_ms: Math.max(previous + 1, now),
      text,
      is_final: true,
      revision: 1,
      speaker_label: 'Professor',
    };
    const message = transcriptForm.querySelector<HTMLElement>('[data-transcript-message]');
    try {
      await window.backend.ingestTranscript(session.session_id, {
        lecture_id: session.lecture_id,
        chunks: [chunk],
      });
      await loadTranscriptWorkspace(session.session_id, chunk.end_ms);
      if (message) message.textContent = 'Transcript added.';
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  document.querySelectorAll<HTMLButtonElement>('[data-request-recovery]').forEach((button) =>
    button.addEventListener('click', async () => {
      const session = getBackendSessionState().activeSession;
      const event = getBackendSessionState().submittedEvents.find(
        (candidate) => candidate.event_id === button.dataset.requestRecovery,
      );
      if (!session || !event) return;
      const message = document.querySelector<HTMLElement>('[data-recovery-message]');
      button.disabled = true;
      try {
        const job = await window.backend.requestRecoveryCard(
          session.session_id,
          { start_ms: event.start_ms, end_ms: event.end_ms, source_event_ids: [event.event_id] },
          crypto.randomUUID(),
        );
        if (job.status === 'failed') {
          throw new Error(job.failure?.message ?? 'Recovery card generation failed.');
        }
        if (!job.card_id) throw new Error('Recovery card is not available yet.');
        recordRecoveryCard(await window.backend.readRecoveryCard(session.session_id, job.card_id));
        setPendingDriftPrompt(null);
        if (resolveRoute(window.location.hash) === 'student-dashboard') {
          window.location.hash = buildRouteHash('student-summary');
        } else {
          renderApplication();
        }
      } catch (error) {
        if (message) message.textContent = formErrorMessage(error);
      } finally {
        button.disabled = false;
      }
    }),
  );
};

/** How long to wait after a live chunk before re-reading the professor's Zoom status. */
const ZOOM_STATUS_REFRESH_DEBOUNCE_MS = 2_000;
let zoomStatusRefreshTimer: number | undefined;

/**
 * Repaints the student transcript tab in place after a live transcript change,
 * preserving whichever tab the student currently has open.
 */
const repaintLiveTranscript = (): void => {
  if (resolveRoute(window.location.hash) !== 'student-summary') return;
  const panel = document.querySelector<HTMLElement>('[data-tab-panel="transcript"]');
  if (!panel) return;
  const state = getBackendSessionState();
  panel.innerHTML = StudentTranscriptPanel({
    isDemo: false,
    session: state.activeSession,
    courses: state.courses,
    joinedSessions: state.joinedSessions,
    submittedEvents: state.submittedEvents,
    recoveryCards: state.recoveryCards,
    transcript: state.transcriptChunks,
    liveEventsConnection: state.liveEventsConnection,
  });
};

/** Re-reads the Zoom link status shown on the professor's active lecture page. */
const refreshProfessorZoomStatus = (): void => {
  const state = getBackendSessionState();
  const sessionId = state.selectedSession?.session_id;
  if (resolveRoute(window.location.hash) !== 'lecture' || !sessionId) return;
  if (state.selectedSession?.status === 'ended') return;
  if (zoomStatusRefreshTimer !== undefined) window.clearTimeout(zoomStatusRefreshTimer);
  zoomStatusRefreshTimer = window.setTimeout(async () => {
    zoomStatusRefreshTimer = undefined;
    await loadZoomRtmsStatus(sessionId);
    const status = getBackendSessionState().zoomRtmsStatusBySession[sessionId] ?? null;
    const line = document.querySelector<HTMLElement>('[data-zoom-rtms-status]');
    if (!line) return;
    line.textContent = describeZoomRtmsStatus(status);
    line.dataset.zoomRtmsStatus = status?.status ?? 'loading';
  }, ZOOM_STATUS_REFRESH_DEBOUNCE_MS);
};

/**
 * Picks the session whose live events the desktop should follow: the joined or
 * started session, or the active lecture a professor is currently viewing.
 */
const resolveLiveSession = (
  state: ReturnType<typeof getBackendSessionState>,
): LectureSession | null => {
  if (state.activeSession) return state.activeSession;
  if (state.user?.role === 'professor' && state.selectedSession?.status === 'active') {
    return state.selectedSession;
  }
  return null;
};

/** Binds local Zoom detection and overlay actions to renderer state. */
const bindZoomDesktop = (): void => {
  if (zoomDesktopBound) return;
  zoomDesktopBound = true;
  bindLiveSessionEvents(
    () => {
      repaintLiveTranscript();
      refreshProfessorZoomStatus();
    },
    repaintLiveTranscript,
    // A full render drops the live subscription and status line for the ended session.
    renderApplication,
  );
  window.bloomDesktop.onZoomDetected(({ running }) => {
    setZoomRunning(running);
    if (running) setZoomBannerDismissed(false);
    renderApplication();
    // A Zoom launch is the strongest hint that a lecture just went live; check right away
    // rather than waiting for the next poll.
    if (running) void pollAvailableSessions();
  });
  window.bloomDesktop.onRecoveryCardCreated((payload) => {
    if (!applyOverlayRecoveryCard(payload)) return;
    renderApplication();
  });
  window.bloomDesktop.onZoomOverlayOpen((payload) => {
    const role = getBackendSessionState().user?.role;
    if (role === 'professor') {
      window.location.hash = buildRouteHash('home');
    } else if (role === 'student' && payload?.view === 'recovery-summary') {
      window.location.hash = buildRouteHash('student-summary');
    } else if (role === 'student') {
      window.location.hash = buildRouteHash('student-dashboard');
      window.setTimeout(() => {
        (
          document.querySelector<HTMLButtonElement>('[data-join-available-session]') ??
          document.querySelector<HTMLInputElement>('[data-join-session-form] input[name="join_code"]')
        )?.focus();
      }, 0);
    }
  });
};

/**
 * Binds educator course, lecture, session, and report actions.
 */
const bindEducatorActions = (route: AppRoute): void => {
  const courseForm = document.querySelector<HTMLFormElement>('[data-course-form]');
  courseForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = readFormValues(courseForm);
    try {
      const request: CreateCourseRequest = {
        title: String(values.title),
      };
      const code = String(values.code).trim();
      if (code) request.code = code;
      const course = await window.backend.createCourse(request);
      setBackendCourses([...getBackendSessionState().courses, course]);
      document.querySelector<HTMLDialogElement>('[data-course-modal]')?.close();
      renderApplication();
    } catch (error) {
      const message = document.querySelector<HTMLElement>('[data-educator-message]');
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  const lectureForm = document.querySelector<HTMLFormElement>('[data-lecture-form]');
  lectureForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = readFormValues(lectureForm);
    try {
      const lecture = await window.backend.createLecture({
        course_id: String(values.course_id),
        title: String(values.title),
      });
      setBackendLectures(lecture.course_id, [
        ...(getBackendSessionState().lecturesByCourse[lecture.course_id] ?? []),
        lecture,
      ]);
      renderApplication();
    } catch (error) {
      const message = document.querySelector<HTMLElement>('[data-educator-message]');
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  document.querySelectorAll<HTMLButtonElement>('[data-start-session]').forEach((button) =>
    button.addEventListener('click', async () => {
      const courseId = button.dataset.courseId;
      const lectureId = button.dataset.startSession;
      const lectureTitle = button.dataset.lectureTitle;
      if (!courseId || !lectureId || !lectureTitle) return;
      try {
        const session = await window.backend.createSession({
          course_id: courseId,
          lecture_id: lectureId,
          title: lectureTitle,
          mode: getBackendSessionState().zoomRunning ? 'zoom' : 'in_person',
        });
        setActiveSession(session);
        renderApplication();
      } catch (error) {
        const message = document.querySelector<HTMLElement>('[data-educator-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    }),
  );
  document.querySelector<HTMLButtonElement>('[data-open-course-modal]')?.addEventListener('click', () => {
    document.querySelector<HTMLDialogElement>('[data-course-modal]')?.showModal();
  });
  document.querySelector<HTMLButtonElement>('[data-close-course-modal]')?.addEventListener('click', () => {
    document.querySelector<HTMLDialogElement>('[data-course-modal]')?.close();
  });
  document.querySelector<HTMLDialogElement>('[data-course-modal]')?.addEventListener('click', (event) => {
    if (event.target === event.currentTarget) (event.currentTarget as HTMLDialogElement).close();
  });
  document.querySelectorAll<HTMLAnchorElement>('.course-group summary a').forEach((anchor) => {
    anchor.addEventListener('click', (event) => event.stopPropagation());
  });
  document.querySelector<HTMLButtonElement>('[data-dismiss-zoom-banner]')?.addEventListener('click', () => {
    setZoomBannerDismissed(true);
    renderApplication();
  });
  const zoomRtmsForm = document.querySelector<HTMLFormElement>('[data-zoom-rtms-form]');
  zoomRtmsForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const sessionId = getBackendSessionState().selectedSession?.session_id;
    const message = document.querySelector<HTMLElement>('[data-zoom-rtms-message]');
    if (!sessionId) return;
    const values = readFormValues(zoomRtmsForm);
    const button = zoomRtmsForm.querySelector<HTMLButtonElement>('button[type="submit"]');
    if (button) button.disabled = true;
    try {
      await linkZoomMeeting(sessionId, String(values.zoom_meeting_id));
      renderApplication();
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
      if (button) button.disabled = false;
    }
  });
  document
    .querySelector<HTMLButtonElement>('[data-end-session]')
    ?.addEventListener('click', async (event) => {
      const button = event.currentTarget as HTMLButtonElement;
      const state = getBackendSessionState();
      const sessionId = button.dataset.endSession ?? state.activeSession?.session_id;
      if (!sessionId) return;
      try {
        await window.backend.endSession(sessionId);
        if (state.activeSession?.session_id === sessionId) {
          cameraMonitorSessionId = null;
          await stopStudentCameraMonitor();
          setActiveSession(null);
        }
        if (route === 'lecture') {
          renderApplication();
          return;
        }
        window.location.hash = buildRouteHash('educator-summary');
      } catch (error) {
        const message = document.querySelector<HTMLElement>('[data-educator-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    });
};

/**
 * Binds account consent and logout controls.
 */
const bindAccountActions = (): void => {
  document
    .querySelector<HTMLInputElement>('[data-analytics-consent]')
    ?.addEventListener('change', async (event) => {
      const input = event.currentTarget as HTMLInputElement;
      try {
        setConsent(await window.backend.updateConsent({ analytics_opt_in: input.checked }));
      } catch (error) {
        const message = document.querySelector<HTMLElement>('[data-consent-message]');
        if (message) message.textContent = formErrorMessage(error);
      }
    });
  document
    .querySelector<HTMLButtonElement>('[data-logout]')
    ?.addEventListener('click', async () => {
      await stopStudentCameraMonitor();
      await window.backend.logout();
      clearBackendSessionState();
      window.bloomDesktop.setRole(null);
      window.location.hash = buildRouteHash('login');
    });
};

/**
 * Loads backend data required by a route and stores it for rendering.
 *
 * @param route - Route whose backend workspace should be loaded.
 */
const loadRouteData = async (route: AppRoute, params: URLSearchParams): Promise<void> => {
  if (
    route === 'educator-dashboard' ||
    route === 'home' ||
    (route === 'lecture-library' && getBackendSessionState().user?.role === 'professor')
  ) {
    await loadEducatorWorkspace();
  }
  if (route === 'course') {
    const courseId = params.get('course_id');
    if (courseId) await loadCourseWorkspace(courseId);
  }
  if (route === 'lecture') {
    const lectureId = params.get('lecture_id');
    if (lectureId) await loadLectureWorkspace(lectureId);
  }
  if (route === 'account') await loadAccountWorkspace();
  if (route === 'student-dashboard' && getBackendSessionState().user?.role === 'student') {
    await loadStudentWorkspace();
  }
  const activeSession = getBackendSessionState().activeSession;
  if (route === 'educator-summary' && activeSession) {
    await loadProfessorReport(activeSession.session_id);
  }
  if (route === 'student-summary' && activeSession) {
    await loadTranscriptWorkspace(activeSession.session_id, sessionDurationMs(activeSession));
  }
};

/**
 * Refreshes the health status shown in the shared navigation.
 */
const updateBackendStatus = async (): Promise<void> => {
  const pill = document.querySelector<HTMLElement>('[data-backend-state]');
  const label = document.querySelector<HTMLElement>('[data-backend-label]');
  if (!pill || !label) return;
  pill.dataset.backendState = 'checking';
  label.textContent = 'Checking Bloom service';
  await checkBackendHealth();
  const connected = getBackendSessionState().backendState === 'connected';
  pill.dataset.backendState = connected ? 'connected' : 'offline';
  label.textContent = connected ? 'Bloom service ready' : 'Bloom service offline · demo mode';
};

/**
 * Updates the active-session elapsed clock until the page is rerendered.
 */
const bindSessionClock = (): void => {
  if (sessionClockTimer !== undefined) window.clearInterval(sessionClockTimer);
  const session = getBackendSessionState().activeSession;
  const clock = document.querySelector<HTMLElement>('[data-session-clock]');
  if (!session || !clock) return;
  const update = (): void => {
    const elapsedMs = Math.max(0, Date.now() - Date.parse(session.session_clock_origin));
    clock.textContent = `Elapsed time: ${formatLectureTime(elapsedMs)}`;
  };
  update();
  sessionClockTimer = window.setInterval(update, 1000);
};

/**
 * Installs all route-specific interactions after page markup is rendered.
 *
 * @param route - Current application route.
 */
const bindRenderedApplication = (route: AppRoute): void => {
  bindTimelineInteractions(route);
  bindSummaryTabs();
  bindLibraryFilters();
  bindAuthentication();
  bindZoomDesktop();
  bindStudentActions();
  bindEducatorActions(route);
  bindAccountActions();
  bindSessionClock();
  bindAvailableSessionsPolling();
  void updateBackendStatus();
};

let renderGeneration = 0;

const renderApplication = (): void => {
  const generation = ++renderGeneration;
  const state = getBackendSessionState();
  const route = resolveRoute(window.location.hash);
  const params = resolveRouteParams(window.location.hash);
  stopCameraForSessionChange(state.activeSession);
  syncLiveSessionSubscription(state.user ? resolveLiveSession(state) : null);
  if (route !== 'login' && !state.user) {
    window.location.hash = buildRouteHash('login');
    return;
  }
  if (route === 'educator-dashboard' && state.user?.role === 'professor') {
    window.location.hash = buildRouteHash('home');
    return;
  }
  setRouteError(null);
  setRouteLoading(route !== 'login');
  appRoot.innerHTML = renderPage(route, getBackendSessionState(), params);
  document.title = `Bloom · ${route
    .split('-')
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')}`;
  bindRenderedApplication(route);
  if (route === 'login') return;
  void loadRouteData(route, params)
    .catch((error: unknown) => {
      setRouteError(formErrorMessage(error));
    })
    .finally(() => {
      // A newer navigation owns the DOM; a late load must not repaint the old route.
      if (generation !== renderGeneration) return;
      setRouteLoading(false);
      const loaded = getBackendSessionState();
      syncLiveSessionSubscription(loaded.user ? resolveLiveSession(loaded) : null);
      appRoot.innerHTML = renderPage(route, loaded, params);
      bindRenderedApplication(route);
    });
};

window.addEventListener('hashchange', renderApplication);
window.addEventListener('beforeunload', () => void stopStudentCameraMonitor());
if (!window.location.hash) window.location.hash = buildRouteHash('login');
else renderApplication();
