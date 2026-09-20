import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { ConsentDialog } from '../../components/consent_dialog.mjs';
import { escapeHtml } from '../../components/html_text.mjs';
import { ZoomRecoveryCue } from '../../components/zoom_recovery_cue.mjs';
import { ACTIVE_LECTURE, LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';

export type StudentDashboardModel = {
  isDemo: boolean;
  user: UserProfile | null;
  courses: Course[];
  activeSession: LectureSession | null;
  joinedSessions: LectureSession[];
  participantCount: number | null;
  submittedEvents: SignalEvent[];
  zoomRunning: boolean;
  zoomBannerDismissed: boolean;
  externalTextConsentGranted: boolean;
  externalTextConsentNote: string | null;
};

const FIXTURE_MODEL: StudentDashboardModel = {
  isDemo: true,
  user: null,
  courses: [],
  activeSession: null,
  joinedSessions: [],
  participantCount: null,
  submittedEvents: [],
  zoomRunning: false,
  zoomBannerDismissed: false,
  externalTextConsentGranted: false,
  externalTextConsentNote: null,
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

function buildRealStudentDashboard(model: StudentDashboardModel): string {
  const session = model.activeSession;
  const joinedSessions = model.joinedSessions;
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
      ${model.zoomRunning && !model.zoomBannerDismissed ? '<section class="panel zoom-banner" role="status"><p>Zoom detected — enter your join code</p><button class="icon-button zoom-banner__dismiss" type="button" data-dismiss-zoom-banner aria-label="Dismiss Zoom reminder">×</button></section>' : ''}
      ${buildJoinForm()}
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
        <form class="section-block login-card form-card" data-transcript-form>
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
            <span><strong>${escapeHtml(joined.title)}</strong><small>${escapeHtml(joined.join_code)} · ${escapeHtml(joined.status)}</small></span>
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
  return `<form class="feature-card login-card form-card" data-join-session-form><p class="eyebrow">Join a lecture</p><label>Join code<input type="text" name="join_code" maxlength="6" autocapitalize="characters" required placeholder="e.g. K7PQ2M" /></label><button class="primary-button" type="submit">Join lecture</button><p class="form-message" data-join-message aria-live="polite"></p></form>`;
}
