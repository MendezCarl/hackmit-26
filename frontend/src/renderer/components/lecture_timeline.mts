import { LectureMoment } from '../fixtures/demo_content.mjs';
import { escapeHtml } from './html_text.mjs';

/**
 * Builds an interactive lecture timeline from synthetic lecture moments.
 *
 * @param moments - Lecture moments with labels and percentage positions.
 * @param selectedMomentId - Moment currently selected in the detail panel.
 * @returns Timeline markup with one button per lecture moment.
 */
export function LectureTimeline(
  moments: LectureMoment[],
  selectedMomentId?: string,
  durationLabel = 'Lecture end',
): string {
  const mergedMoments = Array.from(
    moments.reduce((byPosition, moment) => {
      const existing = byPosition.get(moment.startPercent);
      if (!existing) {
        byPosition.set(moment.startPercent, { ...moment });
      } else {
        existing.title = `${existing.title} · ${moment.title}`;
        existing.evidence = `${existing.evidence} ${moment.evidence}`;
        existing.action = `${existing.action} ${moment.action}`;
        existing.endLabel = moment.endLabel;
        existing.widthPercent = Math.max(existing.widthPercent, moment.widthPercent);
      }
      return byPosition;
    }, new Map<number, LectureMoment>()),
  ).map(([, moment]) => moment);
  const markers = mergedMoments
    .map(
      (moment) => `
        <button
          class="timeline-marker timeline-marker--${escapeHtml(moment.severity)} position-${moment.startPercent} width-${moment.widthPercent} ${selectedMomentId === moment.momentId ? 'is-selected' : ''}"
          type="button"
          data-moment-id="${escapeHtml(moment.momentId)}"
          aria-label="${escapeHtml(moment.startLabel)} to ${escapeHtml(moment.endLabel)}: ${escapeHtml(moment.title)}"
        ><span>${escapeHtml(moment.startLabel)}</span></button>`,
    )
    .join('');

  return `
    <section class="timeline-card" aria-labelledby="timeline-title">
      <div class="section-heading-row">
        <div>
          <p class="eyebrow">Lecture timeline</p>
          <h2 id="timeline-title">Moments worth revisiting</h2>
        </div>
        <div class="timeline-legend" aria-label="Timeline legend">
          <span><i class="legend-swatch legend-swatch--review"></i>Recovery hotspot</span>
          <span><i class="legend-swatch legend-swatch--notice"></i>Delivery note</span>
        </div>
      </div>
      <div class="timeline-track">
        <div class="timeline-baseline"></div>
        ${markers}
      </div>
      <div class="timeline-labels"><span>0:00</span><span>${escapeHtml(durationLabel)}</span></div>
    </section>
  `;
}
