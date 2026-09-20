import { buildRouteHash } from '../app/router.mjs';
import { escapeHtml } from './html_text.mjs';
import { formatLectureTime } from '../services/lecture_view_models.mjs';

export type ZoomRecoveryCueModel = {
  event: SignalEvent | null;
  summaryHref?: string;
};

/**
 * Renders a compact Zoom-session recovery cue for a local missed-content signal.
 *
 * @param model - Latest local signal and optional summary route for follow-up.
 * @returns Fixed-position cue markup, or an empty string when no signal exists.
 */
export function ZoomRecoveryCue(model: ZoomRecoveryCueModel): string {
  if (!model.event) return '';

  const startLabel = formatLectureTime(model.event.start_ms);
  const endLabel = formatLectureTime(model.event.end_ms);
  const summaryHref = model.summaryHref ?? buildRouteHash('student-summary');

  return `
    <details class="zoom-recovery-cue" data-zoom-recovery-cue>
      <summary aria-label="Open possible missed-content cue">
        <span aria-hidden="true"></span>
      </summary>
      <div class="zoom-recovery-cue__card" role="note" aria-label="Possible missed-content signal">
        <p class="eyebrow">Local signal</p>
        <h3>Possible missed moment</h3>
        <ul>
          <li>${escapeHtml(startLabel)}-${escapeHtml(endLabel)}</li>
          <li>Marked for review, not scored.</li>
          <li>Raw media stays on this device.</li>
        </ul>
        <a class="text-link" href="${escapeHtml(summaryHref)}">Open recap</a>
      </div>
    </details>
  `;
}
