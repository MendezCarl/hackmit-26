import { AppShell } from '../../components/app_shell.mjs';
import { LectureCard } from '../../components/lecture_card.mjs';
import { LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';

export type LectureLibraryModel = {
  isDemo: boolean;
  role: 'student' | 'educator';
  courses: Course[];
  lectures: Lecture[];
  joinedSessions: LectureSession[];
};

const FIXTURE_MODEL: LectureLibraryModel = { isDemo: true, role: 'student', courses: [], lectures: [], joinedSessions: [] };

/**
 * Builds the searchable lecture summary catalog.
 *
 * @returns Lecture library markup populated with synthetic lecture fixtures.
 */
export function LectureLibraryPage(model: LectureLibraryModel = FIXTURE_MODEL): string {
  const realLectures = model.lectures.map((lecture) => LectureCard(lecture.title, 'Backend lecture', 'Session available', 'ready')).join('');
  const joined = model.joinedSessions.map((session) => LectureCard(session.title, session.status, 'Current run', 'ready')).join('');
  return AppShell({
    route: 'lecture-library',
    role: model.role,
    eyebrow: 'BIO 101',
    title: 'Lecture library',
    demoMode: model.isDemo,
    content: `
      <div class="library-toolbar">
        <label class="search-field"><span aria-hidden="true">⌕</span><span class="sr-only">Search lectures</span><input type="search" placeholder="Search lecture titles" data-library-search /></label>
        <label class="filter-field"><span class="sr-only">Filter by status</span><select data-library-filter><option value="all">All summaries</option><option value="review">Needs review</option><option value="ready">Summary ready</option></select></label>
      </div>
      <section class="lecture-grid" aria-live="polite" data-lecture-grid>
        ${(model.isDemo ? LECTURE_LIBRARY.map((lecture, index) =>
          LectureCard(
            lecture.lectureTitle,
            lecture.lectureDate,
            lecture.durationLabel,
            index === 0 ? 'review' : 'ready',
          ),
        ).join('') : model.role === 'educator' ? realLectures : joined)}
      </section>
      <p class="empty-state" data-library-empty ${model.isDemo || realLectures || joined ? 'hidden' : ''}>No lectures yet. Join a lecture or ask your professor for a session code.</p>
    `,
  });
}
