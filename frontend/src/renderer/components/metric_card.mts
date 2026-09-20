/**
 * Builds a compact metric card for an educator dashboard.
 *
 * @param label - Plain-language metric name.
 * @param value - Primary formatted value.
 * @param detail - Denominator, definition, or supporting context.
 * @param tone - Visual tone that distinguishes neutral information from review items.
 * @returns Metric card markup.
 */
export function MetricCard(
  label: string,
  value: string,
  detail: string,
  tone: 'teal' | 'gold' | 'sage' | 'slate',
): string {
  return `
    <article class="metric-card metric-card--${tone}">
      <p>${label}</p>
      <strong>${value}</strong>
      <small>${detail}</small>
    </article>
  `;
}
