import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { MetricCard } from '../../components/metric_card.mjs';
import { escapeHtml } from '../../components/html_text.mjs';

export type HomeModel = {
  isDemo: boolean;
  profileName?: string;
  courses: Course[];
  lecturesByCourse: Record<string, Lecture[]>;
  sessions: LectureSession[];
  professorMetricsBySession: Record<string, ProfessorMetrics>;
  professorSummariesBySession: Record<string, ProfessorSummary>;
  activeSession: LectureSession | null;
  routeError?: string | null;
  isLoading?: boolean;
};

const FIXTURE_MODEL: HomeModel = {
  isDemo: true,
  courses: [],
  lecturesByCourse: {},
  sessions: [],
  professorMetricsBySession: {},
  professorSummariesBySession: {},
  activeSession: null,
};

function formatDate(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? 'Unknown date'
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function buildMetrics(
  metricsBySession: Record<string, ProfessorMetrics>,
  summariesBySession: Record<string, ProfessorSummary>,
): string {
  const metrics = Object.values(metricsBySession);
  const summaries = Object.values(summariesBySession);
  if (!metrics.length && !summaries.length) {
    return '<p class="empty-state">No lecture data yet</p>';
  }
  const continuity = metrics
    .map((metric) => metric.continuity?.ratio)
    .filter((ratio): ratio is number => ratio !== undefined);
  const continuityValue = continuity.length
    ? `${Math.round((continuity.reduce((sum, ratio) => sum + ratio, 0) / continuity.length) * 100)}%`
    : 'Withheld';
  const hotspotCount = metrics.reduce(
    (count, metric) => count + metric.buckets.filter((bucket) => bucket.is_hotspot).length,
    0,
  );
  const deliveryNotes = metrics.reduce(
    (count, metric) => count + metric.delivery_findings.length,
    0,
  );
  const participantSummaries = summaries.filter((summary) => !summary.is_suppressed);
  const participants = participantSummaries.length
    ? String(participantSummaries.reduce((sum, summary) => sum + summary.participant_count, 0))
    : 'Withheld';
  return [
    MetricCard('Lecture continuity', continuityValue, 'Mean across available lecture reports', 'teal'),
    MetricCard('Recovery hotspots', String(hotspotCount), 'Anonymous intervals worth reviewing', 'gold'),
    MetricCard('Delivery notes', String(deliveryNotes), 'Possible delivery conditions to review', 'slate'),
    MetricCard('Participants', participants, 'Aggregate consenting participant count', 'sage'),
  ].join('');
}

/**
 * Builds the educator home dashboard with aggregate lecture evidence.
 *
 * @param model - Courses, recent sessions, and privacy-safe report data.
 * @returns Home dashboard markup.
 */
export function HomePage(model: HomeModel = FIXTURE_MODEL): string {
  if (model.isDemo) {
    return AppShell({
      route: 'home',
      role: 'educator',
      profileName: model.profileName,
      eyebrow: 'Educator workspace',
      title: 'Home',
      demoMode: true,
      content: `
        <section class="metrics-grid" aria-label="Lecture metrics">
          ${MetricCard('Lecture continuity', '78%', 'Mean across recent lectures', 'teal')}
          ${MetricCard('Recovery hotspots', '3', 'Anonymous intervals worth reviewing', 'gold')}
          ${MetricCard('Delivery notes', '1', 'Possible delivery conditions to review', 'slate')}
          ${MetricCard('Participants', '68', 'Aggregate consenting participant count', 'sage')}
        </section>
        <section class="panel"><div class="panel__header"><h2>Recent lectures</h2></div><p class="empty-state">No lecture data yet</p></section>
        <section class="panel"><div class="panel__header"><h2>Courses</h2><button class="icon-button" type="button" data-open-course-modal aria-label="Add course">+</button></div><p class="empty-state">No courses yet</p></section>
        ${courseModal()}
      `,
    });
  }

  const courseById = new Map(model.courses.map((course) => [course.course_id, course]));
  const recentSessions = model.sessions.slice(0, 5);
  return AppShell({
    route: 'home',
    role: 'educator',
    profileName: model.profileName,
    eyebrow: 'Educator workspace',
    title: 'Home',
    demoMode: false,
    courses: model.courses,
    lecturesByCourse: model.lecturesByCourse,
    content: `
      ${model.isLoading ? '<p class="empty-state">Loading lecture data…</p>' : ''}
      ${model.routeError ? `<p class="empty-state">${escapeHtml(model.routeError)}</p>` : ''}
      <section class="metrics-grid" aria-label="Lecture metrics">${buildMetrics(model.professorMetricsBySession, model.professorSummariesBySession)}</section>
      <section class="panel">
        <div class="panel__header"><h2>Recent lectures</h2></div>
        ${
          recentSessions.length
            ? `<div class="table-list">${recentSessions
                .map(
                  (session) => `
                    <div class="table-row">
                      <a class="table-row__link" href="${buildRouteHash('lecture', { lecture_id: session.lecture_id })}">
                        <span><strong>${escapeHtml(session.title)}</strong><small>${escapeHtml(courseById.get(session.course_id)?.code ?? 'Course')}</small></span>
                        <span>${escapeHtml(formatDate(session.started_at))}</span>
                        <span class="status-badge">${escapeHtml(session.status)}</span>
                      </a>
                    </div>`,
                )
                .join('')}</div>`
            : '<p class="empty-state">No lecture data yet</p>'
        }
      </section>
      <section class="panel">
        <div class="panel__header"><h2>Courses</h2><button class="icon-button" type="button" data-open-course-modal aria-label="Add course">+</button></div>
        ${
          model.courses.length
            ? `<div class="table-list">${model.courses
                .map(
                  (course) => `
                    <div class="table-row">
                      <a class="table-row__link" href="${buildRouteHash('course', { course_id: course.course_id })}">
                        <span><strong>${escapeHtml(course.code)}</strong></span>
                        <span>${escapeHtml(course.title)}</span>
                        <span>${(model.lecturesByCourse[course.course_id] ?? []).length} lectures</span>
                        <span>${escapeHtml(formatDate(course.created_at))}</span>
                      </a>
                    </div>`,
                )
                .join('')}</div>`
            : '<p class="empty-state">No courses yet</p>'
        }
      </section>
      ${courseModal()}
    `,
  });
}

function courseModal(): string {
  return `
    <dialog class="modal" data-course-modal>
      <form class="login-card form-card" data-course-form method="dialog">
        <p class="eyebrow">Course setup</p>
        <h2>Add course</h2>
        <label>Course title<input type="text" name="title" required /></label>
        <label>Course code<input type="text" name="code" maxlength="16" placeholder="Optional" /></label>
        <p class="form-message" data-educator-message></p>
        <div class="modal__actions"><button class="secondary-button" type="button" data-close-course-modal>Cancel</button><button class="primary-button" type="submit">Create course</button></div>
      </form>
    </dialog>
  `;
}
