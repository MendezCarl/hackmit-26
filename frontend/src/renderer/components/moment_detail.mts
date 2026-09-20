import { LectureMoment } from '../fixtures/demo_content.mjs';
import { escapeHtml } from './html_text.mjs';

/**
 * Builds a selected lecture moment for student or educator context.
 *
 * @param moment - Lecture moment to display.
 * @param audience - Audience controlling recovery or aggregate language.
 * @returns Moment detail markup.
 */
export function MomentDetail(moment: LectureMoment, audience: 'student' | 'educator'): string {
  if (audience === 'student') {
    return `
      <article class="moment-detail" data-moment-detail>
        <div class="moment-detail__time">${escapeHtml(moment.startLabel)}–${escapeHtml(moment.endLabel)}</div>
        <div>
          <p class="eyebrow">Recovery note</p>
          <h3>${escapeHtml(moment.title)}</h3>
          <p>${escapeHtml(moment.summary)}</p>
          <div class="key-point"><span>Key idea</span>${escapeHtml(moment.action)}</div>
        </div>
      </article>
    `;
  }

  return `
    <article class="moment-detail" data-moment-detail>
      <div class="moment-detail__time">${escapeHtml(moment.startLabel)}–${escapeHtml(moment.endLabel)}</div>
      <div>
        <p class="eyebrow">Anonymous aggregate</p>
        <h3>${escapeHtml(moment.title)}</h3>
        <p>${escapeHtml(moment.evidence)}</p>
        <div class="key-point"><span>Suggested action</span>${escapeHtml(moment.action)}</div>
      </div>
    </article>
  `;
}

/**
 * Finds and renders a lecture moment selected by its stable identifier.
 *
 * @param momentId - Stable synthetic moment identifier.
 * @param audience - Audience controlling recovery or aggregate language.
 * @returns Moment detail markup, falling back to the first lecture moment.
 */
export function renderSelectedMoment(
  momentId: string,
  audience: 'student' | 'educator',
  moments: LectureMoment[] = [],
): string {
  const moment = moments.find((candidate) => candidate.momentId === momentId) ?? moments[0];

  return moment
    ? MomentDetail(moment, audience)
    : '<p class="empty-state">No moments are available for this session.</p>';
}
