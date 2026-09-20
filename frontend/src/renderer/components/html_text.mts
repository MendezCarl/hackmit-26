/**
 * Escapes text before it is inserted into renderer-generated HTML.
 *
 * @param value - Untrusted text from a backend response or user input.
 * @returns HTML-safe text with special characters encoded.
 */
export function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character] ?? character,
  );
}
