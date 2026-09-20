import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { ConsentDialog } from '../../components/consent_dialog.mjs';
import { escapeHtml } from '../../components/html_text.mjs';
import { ZoomRecoveryCue } from '../../components/zoom_recovery_cue.mjs';
import { ACTIVE_LECTURE, LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';
import { formatLectureTime } from '../../services/lecture_view_models.mjs';

export type StudentDashboardModel = {
  isDemo: boolean;
  user: UserProfile | null;
  courses: Course[];
  activeSession: LectureSession | null;
  joinedSessions: LectureSession[];
  enrollments: CourseEnrollment[];
  availableSessions: AvailableLectureSession[];
  dismissedAvailableSessionIds: string[];
  participantCount: number | null;
  submittedEvents: SignalEvent[];
  zoomRunning: boolean;
  zoomBannerDismissed: boolean;
  externalTextConsentGranted: boolean;
  externalTextConsentNote: string | null;
  cameraSignalsEnabled: boolean;
  cameraSignalsStatus: 'off' | 'watching' | 'error';
  cameraSignalsError: string | null;
  pendingDriftPrompt: SignalEvent | null;
};

const FIXTURE_MODEL: StudentDashboardModel = {
  isDemo: true,
  user: null,
  courses: [],
  activeSession: null,
  joinedSessions: [],
  enrollments: [],
  availableSessions: [],
  dismissedAvailableSessionIds: [],
  participantCount: null,
  submittedEvents: [],
  zoomRunning: false,
  zoomBannerDismissed: false,
  externalTextConsentGranted: false,
  externalTextConsentNote: null,
  cameraSignalsEnabled: false,
  cameraSignalsStatus: 'off',
  cameraSignalsError: null,
  pendingDriftPrompt: null,
};

/**
 * Builds the student landing page and explicit lecture-consent entry point.
 *
 * @param model - Backend-backed or fixture page data.
 * @returns Student dashboard markup.
 */
export function StudentDashboardPage(model: StudentDashboardModel = FIXTURE_MODEL): string {
  if (!model.isDemo) return buildRealStudentDashboard(model);

  return AppShell({
    route: 'student-dashboard',
    role: 'student',
    eyebrow: 'Good afternoon, Alex',
    title: 'Pick up where learning left off.',
    demoMode: true,
    content: `
      ${model.zoomRunning && !model.zoomBannerDismissed ? '<section class="panel zoom-banner" role="status"><p>Zoom detected — enter your join code</p><button class="icon-button zoom-banner__dismiss" type="button" data-dismiss-zoom-banner aria-label="Dismiss Zoom reminder">×</button></section>' : ''}
      ${buildJoinForm()}
      <section class="welcome-grid">
        <article class="feature-card feature-card--primary">
          <div>
            <span class="status-badge"><i></i>Ready on this device</span>
            <h2>Your next lecture starts at 2:00 PM</h2>
            <p>Bloom can mark possible missed-content moments while keeping raw system audio and camera frames local.</p>
          </div>
          <button class="primary-button" type="button" data-open-consent>Enable for next lecture</button>
        </article>
        <article class="feature-card">
          <p class="eyebrow">Latest recovery</p>
          <h2>${escapeHtml(ACTIVE_LECTURE.lectureTitle)}</h2>
          <p>Three moments are ready to review from ${escapeHtml(ACTIVE_LECTURE.lectureDate)}.</p>
          <a class="text-link" href="${buildRouteHash('student-summary')}">Open lecture summary <span>→</span></a>
        </article>
      </section>
      <section class="section-block">
        <div class="section-heading-row">
          <div><p class="eyebrow">Your week</p><h2>Recent lectures</h2></div>
          <a class="text-link" href="${buildRouteHash('lecture-library')}">View library</a>
        </div>
        <div class="lecture-row-list">
          ${LECTURE_LIBRARY.slice(0, 3)
            .map(
              (lecture, index) => `
                <a class="lecture-row" href="${buildRouteHash('student-summary')}">
                  <span class="lecture-row__date"><strong>${escapeHtml(lecture.lectureDate.split(' ')[1].replace(',', ''))}</strong>SEP</span>
                  <span><strong>${escapeHtml(lecture.lectureTitle)}</strong><small>${escapeHtml(lecture.courseCode)} · ${escapeHtml(lecture.durationLabel)}</small></span>
                  <span class="lecture-row__status">${index === 0 ? '3 review moments' : 'Summary ready'}</span>
                  <span aria-hidden="true">→</span>
                </a>`,
            )
            .join('')}
        </div>
      </section>
      ${ConsentDialog()}
    `,
  });
}

/**
 * Selects live sessions that still deserve a one-click prompt.
 *
 * @param model - Student dashboard data.
 * @returns Available sessions not yet joined, dismissed, or currently active.
 */
export function selectPromptableSessions(
  model: Pick<StudentDashboardModel, 'availableSessions' | 'dismissedAvailableSessionIds' | 'activeSession'>,
): AvailableLectureSession[] {
  const dismissed = new Set(model.dismissedAvailableSessionIds ?? []);
  return (model.availableSessions ?? []).filter(
    (entry) =>
      !entry.is_joined &&
      !dismissed.has(entry.session.session_id) &&
      entry.session.session_id !== model.activeSession?.session_id,
  );
}

function buildRealStudentDashboard(model: StudentDashboardModel): string {
  const session = model.activeSession;
  const joinedSessions = model.joinedSessions;
  const enrollments = model.enrollments ?? [];
  const promptable = selectPromptableSessions(model);
  const courseCodeById = new Map(enrollments.map((entry) => [entry.course_id, entry.course_code]));
  const latestPossibleMissedEvent = session
    ? (model.submittedEvents
        .filter(
          (event) =>
            event.session_id === session.session_id && event.event_type === 'possible_missed_window',
        )
        .at(-1) ?? null)
    : null;
  return AppShell({
    route: 'student-dashboard',
    role: 'student',
    eyebrow: model.user ? `Good afternoon, ${model.user.display_name}` : 'Student workspace',
    title: session?.title ?? 'Your lecture space',
    demoMode: false,
    profileName: model.user?.display_name ?? '?',
    courses: model.courses,
    joinedSessions,
    content: `
      ${promptable.map((entry) => buildLiveLecturePrompt(entry, courseCodeById)).join('')}
      ${
        model.zoomRunning && !model.zoomBannerDismissed && !promptable.length && !session
          ? `<section class="panel zoom-banner" role="status"><p>${
              enrollments.length
                ? 'Zoom detected — none of your courses is live yet. Enter a join code if your professor shared one.'
                : 'Zoom detected — enter your join code, or enroll in a course below so Bloom can find lectures for you'
            }</p><button class="icon-button zoom-banner__dismiss" type="button" data-dismiss-zoom-banner aria-label="Dismiss Zoom reminder">×</button></section>`
          : ''
      }
      ${buildJoinForm()}
      ${buildEnrollmentPanel(enrollments)}
      ${
        session
          ? `
        <article class="feature-card feature-card--primary">
          <span class="status-badge"><i></i>${escapeHtml(session.status)}</span>
          <h2>${escapeHtml(session.title)}</h2>
          <p>Join code: <strong>${escapeHtml(session.join_code)}</strong></p>
          <p data-session-clock>Elapsed time unavailable until the session clock loads.</p>
          <p>${model.participantCount ?? 0} participant(s) joined.</p>
          <button class="primary-button" type="button" data-missed-that>I missed that</button>
        </article>
        <section class="panel recovery-consent">
          <label>
            <input type="checkbox" data-external-text-consent ${model.externalTextConsentGranted ? 'checked' : ''} />
            Allow bounded transcript text to be sent to the AI provider for recovery cards
          </label>
          <p class="form-message" data-external-text-consent-message aria-live="polite">${model.externalTextConsentNote ? escapeHtml(model.externalTextConsentNote) : ''}</p>
        </section>
        <section class="panel camera-signals">
          <label>
            <input type="checkbox" data-camera-signals ${model.cameraSignalsEnabled ? 'checked' : ''} />
            Detect drift with my camera (runs on this device; frames never leave your computer)
          </label>
          <p data-camera-signals-status aria-live="polite">${
            model.cameraSignalsStatus === 'watching'
              ? 'Watching locally…'
              : model.cameraSignalsError ?? 'Camera off'
          }</p>
        </section>
        ${
          model.pendingDriftPrompt
            ? `<section class="panel drift-prompt" role="status">
          <p>Looks like you may have drifted around ${formatLectureTime(model.pendingDriftPrompt.start_ms)}. Want a recovery card for that stretch?</p>
          <button class="primary-button" type="button" data-request-recovery="${escapeHtml(model.pendingDriftPrompt.event_id)}">Get recovery card</button>
          <button class="secondary-button" type="button" data-dismiss-drift-prompt>Dismiss</button>
          <p class="form-message" data-recovery-message aria-live="polite"></p>
        </section>`
            : ''
        }
        <form class="section-block login-card form-card student-form-card" data-transcript-form>
          <label>Local transcript<textarea name="text" required></textarea></label>
          <button class="secondary-button" type="submit">Add transcript</button>
          <p class="form-message" data-transcript-message></p>
        </form>
        <button class="secondary-button" type="button" data-open-consent>Enable for next lecture</button>
        ${ConsentDialog()}
      `
          : ''
        }
        ${session?.mode === 'zoom' ? ZoomRecoveryCue({ event: latestPossibleMissedEvent }) : ''}
      <section class="section-block">
        <div class="section-heading-row">
          <div><p class="eyebrow">Current run</p><h2>Your sessions</h2></div>
          <a class="text-link" href="${buildRouteHash('lecture-library')}">View library</a>
        </div>
        ${
          joinedSessions.length
            ? `<div class="lecture-row-list">${joinedSessions
                .map(
                  (joined) => `
          <a class="lecture-row lecture-row--backend" href="${buildRouteHash('student-summary')}">
            <span class="lecture-row__content"><strong>${escapeHtml(joined.title)}</strong><small class="lecture-row__meta">Join code <code>${escapeHtml(joined.join_code)}</code><span class="status-badge status-badge--ready">${escapeHtml(joined.status)}</span></small></span>
            <span aria-hidden="true">→</span>
          </a>`,
                )
                .join('')}</div>`
            : '<p class="empty-state">No lectures joined yet</p>'
        }
      </section>
    `,
  });
}

function buildJoinForm(): string {
  return `<form class="feature-card login-card form-card student-form-card" data-join-session-form><p class="eyebrow">Have a code?</p><label>Join code<input type="text" name="join_code" maxlength="6" autocapitalize="characters" required placeholder="e.g. K7PQ2M" /></label><button class="primary-button" type="submit">Join lecture</button><p class="form-message" data-join-message aria-live="polite"></p></form>`;
}

function buildLiveLecturePrompt(
  entry: AvailableLectureSession,
  courseCodeById: Map<string, string>,
): string {
  const { session } = entry;
  const courseCode = courseCodeById.get(session.course_id);
  const headline = courseCode
    ? `${escapeHtml(courseCode)} lecture just started`
    : 'Your lecture just started';
  const matchNote =
    entry.matched_by === 'zoom_meeting'
      ? 'Matched to the Zoom meeting open on this device.'
      : 'Detected from a course you enrolled in.';
  return `<section class="panel live-lecture-prompt" role="status" data-live-lecture-prompt="${escapeHtml(session.session_id)}">
    <div>
      <p class="eyebrow">${headline}</p>
      <h2>${escapeHtml(session.title)}</h2>
      <p>${matchNote} Starting recovery keeps camera frames and audio on this device and counts you in anonymous class aggregates.</p>
    </div>
    <div class="zoom-banner__actions">
      <button class="primary-button" type="button" data-join-available-session="${escapeHtml(session.session_id)}">Start recovery</button>
      <button class="secondary-button" type="button" data-dismiss-available-session="${escapeHtml(session.session_id)}">Not now</button>
    </div>
    <p class="form-message" data-live-lecture-message aria-live="polite"></p>
  </section>`;
}

function buildEnrollmentPanel(enrollments: CourseEnrollment[]): string {
  const rows = enrollments.length
    ? `<ul class="enrollment-list">${enrollments
        .map(
          (entry) => `<li class="enrollment-row" data-enrollment="${escapeHtml(entry.enrollment_id)}">
        <span class="enrollment-row__content"><strong>${escapeHtml(entry.course_code)}</strong><small>${escapeHtml(entry.course_title)}</small></span>
        <label class="enrollment-row__toggle"><input type="checkbox" data-enrollment-auto-join="${escapeHtml(entry.enrollment_id)}" ${entry.is_auto_join_enabled ? 'checked' : ''} /> Join lectures automatically</label>
        <button class="icon-button" type="button" data-leave-course="${escapeHtml(entry.enrollment_id)}" aria-label="Leave ${escapeHtml(entry.course_code)}">×</button>
      </li>`,
        )
        .join('')}</ul>`
    : '<p class="empty-state">No courses yet — enroll once and Bloom will prompt you when a lecture goes live.</p>';
  return `<section class="section-block enrollment-panel">
    <div class="section-heading-row"><div><p class="eyebrow">Your courses</p><h2>Lectures Bloom watches for</h2></div></div>
    ${rows}
    <form class="form-card student-form-card" data-enroll-course-form><label>Course code<input type="text" name="course_code" maxlength="16" autocapitalize="characters" required placeholder="e.g. CS101" /></label><button class="secondary-button" type="submit">Enroll</button><p class="form-message" data-enroll-message aria-live="polite"></p></form>
  </section>`;
}
