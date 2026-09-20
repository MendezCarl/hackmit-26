import { AppShell } from '../../components/app_shell.mjs';
import { escapeHtml } from '../../components/html_text.mjs';
import { LectureCard } from '../../components/lecture_card.mjs';
import { LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';

export type LectureLibraryModel = {
  isDemo: boolean;
  profileName?: string;
  role: 'student' | 'educator';
  courses: Course[];
  lectures: Lecture[];
  joinedSessions: LectureSession[];
  routeError?: string | null;
  isLoading?: boolean;
};

const FIXTURE_MODEL: LectureLibraryModel = {
  isDemo: true,
  role: 'student',
  courses: [],
  lectures: [],
  joinedSessions: [],
};

/**
 * Builds the searchable lecture summary catalog.
 *
 * @returns Lecture library markup populated with synthetic lecture fixtures.
 */
export function LectureLibraryPage(model: LectureLibraryModel = FIXTURE_MODEL): string {
  const courseById = new Map(model.courses.map((course) => [course.course_id, course]));
  const realLectures = model.lectures
    .map((lecture) =>
      LectureCard(
        lecture.title,
        courseById.get(lecture.course_id)?.code ?? 'Course',
        'Session available',
        'ready',
      ),
    )
    .join('');
  const joined = model.joinedSessions
    .map((session) =>
      LectureCard(
        session.title,
        courseById.get(session.course_id)?.code ?? session.title,
        session.status,
        'ready',
      ),
    )
    .join('');
  return AppShell({
    route: 'lecture-library',
    role: model.role,
    profileName: model.profileName,
    eyebrow: model.isDemo
      ? 'BIO 101'
      : model.role === 'educator'
        ? 'Educator library'
        : 'Joined sessions',
    title: model.isDemo
      ? 'Lecture library'
      : model.role === 'educator'
        ? 'Your lectures'
        : 'Your joined lectures',
    demoMode: model.isDemo,
    courses: model.courses,
    joinedSessions: model.joinedSessions,
    content: `
      ${model.isLoading ? '<p class="empty-state">Loading from Bloom service…</p>' : ''}
      ${model.routeError ? `<p class="empty-state">Library unavailable: ${escapeHtml(model.routeError)}</p>` : ''}
      <div class="library-toolbar">
        <label class="search-field"><span aria-hidden="true">⌕</span><span class="sr-only">Search lectures</span><input type="search" placeholder="Search lecture titles" data-library-search /></label>
        <label class="filter-field"><span class="sr-only">Filter by status</span><select data-library-filter><option value="all">All summaries</option><option value="review">Needs review</option><option value="ready">Summary ready</option></select></label>
      </div>
      <section class="lecture-grid" aria-live="polite" data-lecture-grid>
        ${
          model.isDemo
            ? LECTURE_LIBRARY.map((lecture, index) =>
                LectureCard(
                  lecture.lectureTitle,
                  lecture.lectureDate,
                  lecture.durationLabel,
                  index === 0 ? 'review' : 'ready',
                ),
              ).join('')
            : model.role === 'educator'
              ? realLectures
              : joined
        }
      </section>
      <p class="empty-state" data-library-empty ${model.isDemo || realLectures || joined ? 'hidden' : ''}>${model.role === 'educator' ? 'No lectures yet. Create a course and lecture to build your library.' : 'No lectures joined yet. Join a lecture from your dashboard.'}</p>
    `,
  });
}
