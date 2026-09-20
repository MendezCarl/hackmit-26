import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { ConsentDialog } from '../../components/consent_dialog.mjs';
import { ACTIVE_LECTURE, LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';

export type StudentDashboardModel = {
  isDemo: boolean;
  user: UserProfile | null;
  activeSession: LectureSession | null;
  participantCount: number | null;
};

const FIXTURE_MODEL: StudentDashboardModel = { isDemo: true, user: null, activeSession: null, participantCount: null };

/**
 * Builds the student landing page and explicit lecture-consent entry point.
 *
 * @returns Student dashboard markup populated with synthetic lecture fixtures.
 */
export function StudentDashboardPage(model: StudentDashboardModel = FIXTURE_MODEL): string {
  const session = model.activeSession;
  return AppShell({
    route: 'student-dashboard',
    role: 'student',
    eyebrow: model.user ? `Good afternoon, ${model.user.display_name}` : 'Good afternoon, Alex',
    title: session ? session.title : 'Pick up where learning left off.',
    demoMode: model.isDemo,
    content: `
      <form class="feature-card" data-join-session-form><p class="eyebrow">Join a lecture</p><label>Session ID<input name="session_id" required placeholder="Paste the join code" /></label><button class="primary-button" type="submit">Join lecture</button><p class="form-message" data-join-message aria-live="polite"></p></form>
      ${session ? `<article class="feature-card feature-card--primary"><span class="status-badge"><i></i>${session.status}</span><h2>${session.title}</h2><p>Join code: <strong>${session.session_id}</strong></p><p data-session-clock>Session clock is active.</p><button class="primary-button" type="button" data-missed-that>I missed that</button><p>${model.participantCount ?? 0} participant(s) joined.</p></article>` : ''}
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
          <h2>${ACTIVE_LECTURE.lectureTitle}</h2>
          <p>Three moments are ready to review from ${ACTIVE_LECTURE.lectureDate}.</p>
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
                  <span class="lecture-row__date"><strong>${lecture.lectureDate.split(' ')[1].replace(',', '')}</strong>SEP</span>
                  <span><strong>${lecture.lectureTitle}</strong><small>${lecture.courseCode} · ${lecture.durationLabel}</small></span>
                  <span class="lecture-row__status">${index === 0 ? '3 review moments' : 'Summary ready'}</span>
                  <span aria-hidden="true">→</span>
                </a>`,
            )
            .join('')}
        </div>
      </section>
      ${session ? '<form class="section-block" data-transcript-form><label>Local transcript<textarea name="text" required></textarea></label><button class="secondary-button" type="submit">Add transcript</button><p class="form-message" data-transcript-message></p></form>' : ''}${ConsentDialog()}
    `,
  });
}
