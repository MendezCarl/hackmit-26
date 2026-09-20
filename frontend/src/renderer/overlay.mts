import { escapeHtml } from './components/html_text.mjs';

const role = window.bloomDesktop.getOverlayRole();
const copy =
  role === 'professor'
    ? {
        message: 'Zoom is open. Start your Bloom lecture session so students can follow along.',
        action: 'Start session',
      }
    : role === 'student'
      ? {
          message: 'Zoom is open. Join your lecture in Bloom to get recovery cards.',
          action: 'Join lecture',
        }
      : {
          message: 'Open Bloom to sign in.',
          action: 'Open Bloom',
        };

const app = document.querySelector<HTMLElement>('#overlay-app');
if (!app) throw new Error('Bloom overlay requires an #overlay-app mount element.');

app.innerHTML = `
  <section class="overlay-card" aria-labelledby="overlay-title">
    <div class="overlay-card__header">
      <p class="eyebrow">Bloom</p>
      <button class="overlay-card__dismiss" type="button" data-overlay-dismiss aria-label="Dismiss">×</button>
    </div>
    <h1 id="overlay-title">Zoom detected</h1>
    <p>${escapeHtml(copy.message)}</p>
    <div class="overlay-card__actions">
      <button class="primary-button" type="button" data-overlay-open>${escapeHtml(copy.action)}</button>
      <button class="secondary-button" type="button" data-overlay-dismiss>Dismiss</button>
    </div>
  </section>
`;

document.querySelectorAll<HTMLButtonElement>('[data-overlay-open]').forEach((button) => {
  button.addEventListener('click', () => window.bloomDesktop.overlayAction('open'));
});
document.querySelectorAll<HTMLButtonElement>('[data-overlay-dismiss]').forEach((button) => {
  button.addEventListener('click', () => window.bloomDesktop.overlayAction('dismiss'));
});
