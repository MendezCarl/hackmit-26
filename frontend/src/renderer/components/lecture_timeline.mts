import { ACTIVE_LECTURE, LectureMoment } from '../fixtures/demo_content.mjs';

/**
 * Builds an interactive lecture timeline from synthetic lecture moments.
 *
 * @param moments - Lecture moments with labels and percentage positions.
 * @param selectedMomentId - Moment currently selected in the detail panel.
 * @returns Timeline markup with one button per lecture moment.
 */
export function LectureTimeline(moments: LectureMoment[], selectedMomentId?: string): string {
  const markers = moments
    .map(
      (moment) => `
        <button
          class="timeline-marker timeline-marker--${moment.severity} position-${moment.startPercent} width-${moment.widthPercent} ${selectedMomentId === moment.momentId ? 'is-selected' : ''}"
          type="button"
          data-moment-id="${moment.momentId}"
          aria-label="${moment.startLabel} to ${moment.endLabel}: ${moment.title}"
        ><span>${moment.startLabel}</span></button>`,
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
      <div class="timeline-labels"><span>0:00</span><span>${ACTIVE_LECTURE.durationLabel}</span></div>
    </section>
  `;
}
