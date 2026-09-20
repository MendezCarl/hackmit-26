import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { escapeHtml } from '../../components/html_text.mjs';

export type CoursePageModel = {
  isDemo: boolean;
  profileName?: string;
  course: Course | null;
  lectures: Lecture[];
  sessionsByLecture: Record<string, LectureSession[]>;
  activeSession: LectureSession | null;
  routeError?: string | null;
};

const FIXTURE_MODEL: CoursePageModel = {
  isDemo: true,
  course: null,
  lectures: [],
  sessionsByLecture: {},
  activeSession: null,
};

function formatDate(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? 'Unknown date'
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Builds an educator course page with lecture creation and session history.
 *
 * @param model - Selected course and its lecture/session records.
 * @returns Course detail page markup.
 */
export function CoursePage(model: CoursePageModel = FIXTURE_MODEL): string {
  if (!model.course && !model.isDemo) {
    return AppShell({
      route: 'course',
      role: 'educator',
      title: 'Course not found',
      demoMode: false,
      content: '<section class="panel"><p class="empty-state">That course could not be found.</p></section>',
    });
  }
  const course = model.course ?? {
    course_id: 'demo-course',
    owner_id: 'demo-owner',
    title: 'Foundations of Biology',
    code: 'BIO 101',
    created_at: '2026-01-01T00:00:00.000Z',
  };
  const lectures = model.isDemo
    ? [
        {
          lecture_id: 'demo-lecture',
          course_id: course.course_id,
          owner_id: course.owner_id,
          title: 'Cellular respiration',
          created_at: course.created_at,
        },
      ]
    : model.lectures;
  return AppShell({
    route: 'course',
    role: 'educator',
    profileName: model.profileName,
    eyebrow: course.code,
    title: course.title,
    demoMode: model.isDemo,
    courses: [course],
    lecturesByCourse: { [course.course_id]: lectures },
    currentCourseId: course.course_id,
    content: `
      <section class="panel">
        <div class="panel__header"><h2>Create lecture</h2></div>
        <form class="inline-form" data-lecture-form>
          <input type="hidden" name="course_id" value="${escapeHtml(course.course_id)}" />
          <label class="sr-only" for="lecture-title">Lecture title</label>
          <input id="lecture-title" type="text" name="title" placeholder="Lecture title" required />
          <button class="primary-button" type="submit">Create lecture</button>
        </form>
        <p class="form-message" data-educator-message></p>
      </section>
      <section class="panel">
        <div class="panel__header"><h2>Lecture log</h2></div>
        ${
          lectures.length
            ? `<div class="table-list">${lectures
                .map(
                  (lecture) => `
                    <a class="table-row lecture-log-row" href="${buildRouteHash('lecture', { lecture_id: lecture.lecture_id })}">
                      <span><strong>${escapeHtml(lecture.title)}</strong></span>
                      <span>${escapeHtml(formatDate(lecture.created_at))}</span>
                      <span>${(model.sessionsByLecture[lecture.lecture_id] ?? []).length} sessions</span>
                      <button class="secondary-button" type="button" data-start-session="${escapeHtml(lecture.lecture_id)}" data-course-id="${escapeHtml(course.course_id)}" data-lecture-title="${escapeHtml(lecture.title)}">Start session</button>
                    </a>`,
                )
                .join('')}</div>`
            : '<p class="empty-state">No lectures yet</p>'
        }
      </section>
    `,
  });
}
