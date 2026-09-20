/**
 * Builds the explicit pre-lecture consent dialog.
 *
 * @returns Consent dialog markup that keeps capture disabled until enabled.
 */
export function ConsentDialog(): string {
  return `
    <dialog class="consent-dialog" data-consent-dialog>
      <form method="dialog">
        <div class="dialog-icon"><img src="./assets/bloom-icon.svg" alt="" /></div>
        <p class="eyebrow">Before the lecture</p><h2>Enable Bloom for this session?</h2>
        <p>Bloom will capture system audio and analyze approved signals locally. Raw audio, screenshots, and camera frames stay on this device.</p>
        <ul><li>You can pause or stop at any time.</li><li>Only approved, anonymous aggregates can appear in educator reports.</li><li>Nothing starts until you choose enable.</li></ul>
        <p class="form-message" data-consent-message aria-live="polite"></p>
        <div class="dialog-actions"><button class="secondary-button" value="cancel">Not now</button><button class="primary-button" value="enable">Enable session</button></div>
      </form>
    </dialog>
  `;
}
