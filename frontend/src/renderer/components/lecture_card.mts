import { buildRouteHash } from '../app/router.mjs';

/**
 * Builds a lecture summary card for the searchable lecture library.
 *
 * @param title - Lecture title.
 * @param date - Human-readable lecture date.
 * @param duration - Human-readable lecture duration.
 * @param status - Review state used by the library filter.
 * @returns Lecture card markup.
 */
export function LectureCard(
  title: string,
  date: string,
  duration: string,
  status: 'review' | 'ready',
): string {
  return `
    <article class="lecture-card" data-lecture-title="${title.toLowerCase()}" data-lecture-status="${status}">
      <div class="lecture-card__art" aria-hidden="true"><span>${status === 'review' ? '3' : '✓'}</span></div>
      <div class="lecture-card__body"><span class="status-badge status-badge--${status}">${status === 'review' ? 'Needs review' : 'Summary ready'}</span><h2>${title}</h2><p>${date} · ${duration}</p><a href="${buildRouteHash('student-summary')}">Open summary <span>→</span></a></div>
    </article>
  `;
}
