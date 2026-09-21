import { escapeHtml } from './html_text.mjs';
import { formatLectureTime } from '../services/lecture_view_models.mjs';

/** Overlay view before the student asks for help. */
export type DriftOverlayPromptView = { status: 'prompt' };

/** Every state the drift overlay can render while the student stays in Zoom. */
export type DriftOverlayView = DriftOverlayPromptView | DriftRecoveryState;

/** Copy for the initial drift prompt; phrased as a possible missed-content signal, not a verdict. */
export const DRIFT_PROMPT_COPY = {
  title: 'Drifted?',
  message:
    'Bloom noticed you may have missed part of the lecture. Get a recovery card right here without leaving Zoom.',
  action: 'Get recovery card',
} as const;

const LOADING_MESSAGE = 'Building your recovery card…';

function renderHeader(title: string): string {
  return `
    <div class="overlay-card__header">
      <p class="eyebrow">Bloom</p>
      <button class="overlay-card__dismiss" type="button" data-overlay-dismiss aria-label="Dismiss">×</button>
    </div>
    <h1 id="overlay-title">${escapeHtml(title)}</h1>
  `;
}

function renderCardBody(card: RecoveryCard): string {
  const sources = card.source_timestamps
    .map((source) => `${formatLectureTime(source.start_ms)}–${formatLectureTime(source.end_ms)}`)
    .join(', ');
  return `
    <div class="overlay-recovery" data-overlay-recovery-card="${escapeHtml(card.card_id)}">
      <p class="overlay-recovery__topic">${escapeHtml(card.topic)}</p>
      <p>${escapeHtml(card.what_you_missed)}</p>
      <ul>${card.key_facts.map((fact) => `<li>${escapeHtml(fact)}</li>`).join('')}</ul>
      ${card.example_from_lecture ? `<p>${escapeHtml(card.example_from_lecture)}</p>` : ''}
      <p class="overlay-recovery__follow-up">${escapeHtml(card.follow_up_question)}</p>
      <small>Sources: ${escapeHtml(sources)}</small>
    </div>
  `;
}

/**
 * Renders the drift overlay for one view state.
 *
 * The overlay is a small always-on-top window layered over Zoom, so every state
 * keeps a dismiss control and never requires the main Bloom window.
 *
 * @param view - Prompt, loading, ready (card), or failed state.
 * @returns Escaped overlay markup for `#overlay-app`.
 */
export function renderDriftOverlay(view: DriftOverlayView): string {
  if (view.status === 'prompt') {
    return `
      <section class="overlay-card" aria-labelledby="overlay-title" data-overlay-state="prompt">
        ${renderHeader(DRIFT_PROMPT_COPY.title)}
        <p>${escapeHtml(DRIFT_PROMPT_COPY.message)}</p>
        <div class="overlay-card__actions">
          <button class="primary-button" type="button" data-overlay-recover>${escapeHtml(DRIFT_PROMPT_COPY.action)}</button>
          <button class="secondary-button" type="button" data-overlay-dismiss>Dismiss</button>
        </div>
      </section>
    `;
  }
  if (view.status === 'loading') {
    return `
      <section class="overlay-card overlay-card--expanded" aria-labelledby="overlay-title" aria-busy="true" data-overlay-state="loading">
        ${renderHeader('Recovering…')}
        <p role="status">${escapeHtml(LOADING_MESSAGE)}</p>
        <div class="overlay-card__actions">
          <button class="secondary-button" type="button" data-overlay-dismiss>Dismiss</button>
        </div>
      </section>
    `;
  }
  if (view.status === 'failed') {
    return `
      <section class="overlay-card overlay-card--expanded" aria-labelledby="overlay-title" data-overlay-state="failed">
        ${renderHeader('Recovery card unavailable')}
        <p role="alert" data-overlay-error>${escapeHtml(view.message)}</p>
        <div class="overlay-card__actions">
          <button class="primary-button" type="button" data-overlay-recover>Retry</button>
          <button class="secondary-button" type="button" data-overlay-dismiss>Dismiss</button>
        </div>
      </section>
    `;
  }
  return `
    <section class="overlay-card overlay-card--expanded" aria-labelledby="overlay-title" data-overlay-state="ready">
      ${renderHeader('Here is what you may have missed')}
      ${renderCardBody(view.card)}
      <div class="overlay-card__actions">
        <button class="primary-button" type="button" data-overlay-dismiss>Back to Zoom</button>
        <button class="secondary-button" type="button" data-overlay-open="recovery-summary">Open in Bloom</button>
      </div>
    </section>
  `;
}

/**
 * Validates a recovery state pushed over IPC before the overlay renders it.
 *
 * @param raw - Payload from the `overlay:recovery-state` channel.
 * @returns The typed state, or null when the payload is not a known state.
 */
export function parseDriftRecoveryState(raw: unknown): DriftRecoveryState | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const candidate = raw as Partial<DriftRecoveryState>;
  if (candidate.status === 'loading') return candidate as DriftRecoveryState;
  if (candidate.status === 'failed' && typeof candidate.message === 'string') {
    return candidate as DriftRecoveryState;
  }
  if (candidate.status === 'ready' && typeof candidate.card === 'object' && candidate.card) {
    return candidate as DriftRecoveryState;
  }
  return null;
}
