import { escapeHtml } from './html_text.mjs';
/**
 * Builds a labeled account-setting row with a toggle.
 *
 * @param label - Human-readable setting name.
 * @param description - Plain-language behavior and privacy description.
 * @param isEnabled - Whether the setting starts enabled.
 * @param isLocked - Whether the user may change the setting.
 * @returns Account setting row markup.
 */
export function SettingRow(
  label: string,
  description: string,
  isEnabled: boolean,
  isLocked = false,
): string {
  return `
    <div class="setting-row"><div><strong>${escapeHtml(label)}</strong><p>${escapeHtml(description)}</p></div><label class="toggle ${isLocked ? 'is-locked' : ''}"><span class="sr-only">${escapeHtml(label)}</span><input type="checkbox" ${isEnabled ? 'checked' : ''} ${isLocked ? 'disabled' : ''}/><i></i></label></div>
  `;
}
