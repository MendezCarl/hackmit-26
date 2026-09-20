import { AppShell } from '../../components/app_shell.mjs';
import { LectureCard } from '../../components/lecture_card.mjs';
import { LECTURE_LIBRARY } from '../../fixtures/demo_content.mjs';

/**
 * Builds the searchable lecture summary catalog.
 *
 * @returns Lecture library markup populated with synthetic lecture fixtures.
 */
export function LectureLibraryPage(): string {
  return AppShell({
    route: 'lecture-library',
    role: 'student',
    eyebrow: 'BIO 101',
    title: 'Lecture library',
    content: `
      <div class="library-toolbar">
        <label class="search-field"><span aria-hidden="true">⌕</span><span class="sr-only">Search lectures</span><input type="search" placeholder="Search lecture titles" data-library-search /></label>
        <label class="filter-field"><span class="sr-only">Filter by status</span><select data-library-filter><option value="all">All summaries</option><option value="review">Needs review</option><option value="ready">Summary ready</option></select></label>
      </div>
      <section class="lecture-grid" aria-live="polite" data-lecture-grid>
        ${LECTURE_LIBRARY.map((lecture, index) =>
          LectureCard(
            lecture.lectureTitle,
            lecture.lectureDate,
            lecture.durationLabel,
            index === 0 ? 'review' : 'ready',
          ),
        ).join('')}
      </section>
      <p class="empty-state" data-library-empty hidden>No lectures match that search.</p>
    `,
  });
}
