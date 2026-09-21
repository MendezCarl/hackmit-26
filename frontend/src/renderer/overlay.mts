import {
  parseDriftRecoveryState,
  renderDriftOverlay,
  type DriftOverlayView,
} from './components/drift_overlay_card.mjs';
import { escapeHtml } from './components/html_text.mjs';

const role = window.bloomDesktop.getOverlayRole();
const variant = new URLSearchParams(window.location.search).get('variant');

const app = document.querySelector<HTMLElement>('#overlay-app');
if (!app) throw new Error('Bloom overlay requires an #overlay-app mount element.');
const mount: HTMLElement = app;

function bindOverlayActions(): void {
  mount.querySelectorAll<HTMLButtonElement>('[data-overlay-open]').forEach((button) => {
    button.addEventListener('click', () =>
      window.bloomDesktop.overlayAction({
        action: 'open',
        view: button.dataset.overlayOpen === 'recovery-summary' ? 'recovery-summary' : 'default',
      }),
    );
  });
  mount.querySelectorAll<HTMLButtonElement>('[data-overlay-recover]').forEach((button) => {
    button.addEventListener('click', () => {
      button.disabled = true;
      window.bloomDesktop.overlayAction({ action: 'recover' });
    });
  });
  mount.querySelectorAll<HTMLButtonElement>('[data-overlay-dismiss]').forEach((button) => {
    button.addEventListener('click', () => window.bloomDesktop.overlayAction({ action: 'dismiss' }));
  });
}

function renderDriftVariant(view: DriftOverlayView): void {
  mount.innerHTML = renderDriftOverlay(view);
  bindOverlayActions();
}

if (variant === 'drift') {
  renderDriftVariant({ status: 'prompt' });
  window.bloomDesktop.onDriftRecoveryState((rawState) => {
    const state = parseDriftRecoveryState(rawState);
    if (state) renderDriftVariant(state);
  });
} else {
  const copy =
    role === 'professor'
      ? {
          title: 'Zoom detected',
          message: 'Zoom is open. Start your Bloom lecture session so students can follow along.',
          action: 'Start session',
        }
      : role === 'student'
        ? {
            title: 'Zoom detected',
            message: 'Zoom is open. Join your lecture in Bloom to get recovery cards.',
            action: 'Join lecture',
          }
        : {
            title: 'Zoom detected',
            message: 'Open Bloom to sign in.',
            action: 'Open Bloom',
          };

  mount.innerHTML = `
    <section class="overlay-card" aria-labelledby="overlay-title" data-overlay-state="zoom">
      <div class="overlay-card__header">
        <p class="eyebrow">Bloom</p>
        <button class="overlay-card__dismiss" type="button" data-overlay-dismiss aria-label="Dismiss">×</button>
      </div>
      <h1 id="overlay-title">${escapeHtml(copy.title)}</h1>
      <p>${escapeHtml(copy.message)}</p>
      <div class="overlay-card__actions">
        <button class="primary-button" type="button" data-overlay-open="default">${escapeHtml(copy.action)}</button>
        <button class="secondary-button" type="button" data-overlay-dismiss>Dismiss</button>
      </div>
    </section>
  `;
  bindOverlayActions();
}
