import { AppShell } from '../../components/app_shell.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { ACTIVE_LECTURE } from '../../fixtures/demo_content.mjs';
import {
  buildMomentsFromMetrics,
  buildMomentsFromSummary,
  formatLectureTime,
  sessionDurationMs,
} from '../../services/lecture_view_models.mjs';

export type EducatorSummaryModel = {
  isDemo: boolean;
  session: LectureSession | null;
  summary: ProfessorSummary | null;
  metrics: ProfessorMetrics | null;
  summaryError?: string | null;
  metricsError?: string | null;
  routeError?: string | null;
  isLoading?: boolean;
};
const FIXTURE_MODEL: EducatorSummaryModel = {
  isDemo: true,
  session: null,
  summary: null,
  metrics: null,
};

/**
 * Builds the detailed anonymous educator lecture report.
 *
 * @returns Educator summary markup with aggregate evidence and delivery feedback.
 */
export function EducatorSummaryPage(model: EducatorSummaryModel = FIXTURE_MODEL): string {
  if (!model.isDemo) return buildRealEducatorSummary(model);

  const firstMoment = ACTIVE_LECTURE.moments[0];
  const moments = ACTIVE_LECTURE.moments;

  return AppShell({
    route: 'educator-summary',
    role: 'educator',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
    title: 'Lecture report',
    demoMode: model.isDemo,
    content: `
      <div class="report-heading">
        <div><h2>${ACTIVE_LECTURE.lectureTitle}</h2><p>Anonymous aggregate report with privacy-safe evidence.</p></div>
        <button class="secondary-button" type="button" data-export-report>Export summary</button>
      </div>
      ${LectureTimeline(moments, firstMoment.momentId, ACTIVE_LECTURE.durationLabel)}
      <section class="report-grid"><div>${MomentDetail(firstMoment, 'educator')}</div><aside class="evidence-card"><p class="eyebrow">Evidence coverage</p><strong>68 / 82</strong><p>Anonymous participants contributed sufficient data for this lecture.</p><div class="coverage-bar"><i></i></div><small>Individual timelines and identities are never shown.</small></aside></section>
      <section class="section-block delivery-section">
        <div class="delivery-icon" aria-hidden="true">◖</div>
        <div><p class="eyebrow">Delivery quality · 27:40–29:12</p><h2>Possible audio clarity issue</h2><p>Speech-recognition confidence decreased while microphone volume became inconsistent. This is an observable technical condition, not a claim about learning or comprehension.</p></div>
        <div class="key-point"><span>Suggestion</span>Review this interval and consider repeating the explanation next lecture.</div>
      </section>
    `,
  });
}

function buildRealEducatorSummary(model: EducatorSummaryModel): string {
  const session = model.session;
  const duration = session ? sessionDurationMs(session) : 1;
  const summary = model.summary;
  const metrics = model.metrics;
  const moments = metrics
    ? buildMomentsFromMetrics(metrics, duration)
    : summary
      ? buildMomentsFromSummary(summary, duration)
      : [];
  const selected = moments[0];
  const suppression = summary?.is_suppressed
    ? `<p class="empty-state">Fewer than ${summary.minimum_group_size} consenting participants — summary withheld</p>`
    : '';
  const errors = [
    model.summaryError ? `Summary unavailable: ${model.summaryError}` : '',
    model.metricsError ? `Metrics unavailable: ${model.metricsError}` : '',
    model.routeError ? `Report unavailable: ${model.routeError}` : '',
  ].filter(Boolean);
  const deliveryFindings = metrics?.delivery_findings ?? [];
  const actions = summary?.suggested_actions?.map((action) => `<li>${action}</li>`).join('') ?? '';
  const continuity = metrics?.continuity
    ? `<p class="summary-meta">Continuity: ${Math.round(metrics.continuity.ratio * 100)}%</p>`
    : '';

  return AppShell({
    route: 'educator-summary',
    role: 'educator',
    eyebrow: session ? `Session ${session.course_id}` : 'Educator report',
    title: session?.title ?? 'Lecture report',
    demoMode: false,
    content: `
      ${model.isLoading ? '<p class="empty-state">Loading from local service…</p>' : ''}
      ${errors.map((error) => `<p class="empty-state">${error}</p>`).join('')}
      ${suppression}
      ${metrics ? `<p class="summary-meta">Metrics status: ${metrics.status}</p>${continuity}` : ''}
      ${selected ? `${LectureTimeline(moments, selected.momentId, formatLectureTime(duration))}<section class="report-grid"><div>${MomentDetail(selected, 'educator')}</div><aside class="evidence-card"><p class="eyebrow">Anonymous participants</p><strong>${summary?.participant_count ?? 'Withheld'}</strong><p>Identity-safe aggregates only.</p></aside></section>` : '<p class="empty-state">No report intervals are available for this session.</p>'}
      ${actions ? `<section class="section-block"><h2>Suggested actions</h2><ul>${actions}</ul></section>` : ''}
      ${deliveryFindings.map((finding) => `<section class="section-block delivery-section"><div class="delivery-icon" aria-hidden="true">◖</div><div><p class="eyebrow">Delivery quality · ${formatLectureTime(finding.start_ms)}–${formatLectureTime(finding.end_ms)}</p><h2>${finding.signal_type}</h2><p>Confidence ${Math.round(finding.confidence * 100)}%.</p></div><div class="key-point"><span>Suggestion</span>${finding.suggested_action}</div></section>`).join('')}
    `,
  });
}
