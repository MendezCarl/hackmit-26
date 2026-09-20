import {
  buildRouteHash,
  resolveRoute,
  resolveRouteParams,
  type AppRoute,
} from './app/router.mjs';
import { renderPage } from './app/render_page.mjs';
import { renderSelectedMoment } from './components/moment_detail.mjs';
import {
  clearBackendSessionState,
  getBackendSessionState,
  setActiveSession,
  setBackendCourses,
  setBackendLectures,
  setBackendState,
  setBackendUser,
  setConsent,
  setRouteError,
  setRouteLoading,
} from './services/backend_session_state.mjs';
import {
  checkBackendHealth,
  joinLectureSession,
  loadAccountWorkspace,
  loadCourseWorkspace,
  loadEducatorWorkspace,
  loadLectureWorkspace,
  loadProfessorReport,
  loadTranscriptWorkspace,
  recordRecoveryCard,
  recordSubmittedEvent,
} from './services/lecture_workspace.mjs';
import {
  buildMomentsFromEvents,
  buildMomentsFromMetrics,
  buildMomentsFromSummary,
  formatLectureTime,
  sessionDurationMs,
} from './services/lecture_view_models.mjs';

const appRoot = document.querySelector<HTMLElement>('#app');
if (!appRoot) throw new Error('Bloom requires an #app mount element.');

const formErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'The local service could not complete that request.';

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

/**
 * Binds timeline marker selection to the current route's live moments.
 *
 * @param route - Route whose moment view model should be rendered.
 */
const bindTimelineInteractions = (route: AppRoute): void => {
  const buttons = document.querySelectorAll<HTMLButtonElement>('[data-moment-id]');
  const state = getBackendSessionState();
  const duration = state.activeSession ? sessionDurationMs(state.activeSession) : 1;
  const selectedEducatorSession = route === 'lecture' ? state.activeSession : null;
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
      await joinLectureSession(joinCode);
      renderApplication();
    } catch (error) {
      if (message) message.textContent = formErrorMessage(error);
    }
  });
  const session = getBackendSessionState().activeSession;
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
        renderApplication();
      } catch (error) {
        if (message) message.textContent = formErrorMessage(error);
      } finally {
        button.disabled = false;
      }
    }),
  );
};

/**
 * Binds educator course, lecture, session, and report actions.
 */
const bindEducatorActions = (): void => {
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
    button.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const courseId = button.dataset.courseId;
      const lectureId = button.dataset.startSession;
      const lectureTitle = button.dataset.lectureTitle;
      if (!courseId || !lectureId || !lectureTitle) return;
      try {
        const session = await window.backend.createSession({
          course_id: courseId,
          lecture_id: lectureId,
          title: lectureTitle,
          mode: 'in_person',
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
  document
    .querySelector<HTMLButtonElement>('[data-end-session]')
    ?.addEventListener('click', async () => {
      const session = getBackendSessionState().activeSession;
      if (!session) return;
      try {
        setActiveSession(await window.backend.endSession(session.session_id));
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
      await window.backend.logout();
      clearBackendSessionState();
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
  label.textContent = 'Checking local service';
  await checkBackendHealth();
  const connected = getBackendSessionState().backendState === 'connected';
  pill.dataset.backendState = connected ? 'connected' : 'offline';
  label.textContent = connected ? 'Local service ready' : 'Local service offline · demo mode';
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
  bindStudentActions();
  bindEducatorActions();
  bindAccountActions();
  bindSessionClock();
  void updateBackendStatus();
};

const renderApplication = (): void => {
  const state = getBackendSessionState();
  const route = resolveRoute(window.location.hash);
  const params = resolveRouteParams(window.location.hash);
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
      setRouteLoading(false);
      appRoot.innerHTML = renderPage(route, getBackendSessionState(), params);
      bindRenderedApplication(route);
    });
};

window.addEventListener('hashchange', renderApplication);
if (!window.location.hash) window.location.hash = buildRouteHash('login');
else renderApplication();
