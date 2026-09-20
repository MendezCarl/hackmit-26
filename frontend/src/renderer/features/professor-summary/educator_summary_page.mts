import { AppShell } from '../../components/app_shell.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { ACTIVE_LECTURE } from '../../fixtures/demo_content.mjs';
import { buildMomentsFromSummary, formatLectureTime, sessionDurationMs } from '../../services/lecture_view_models.mjs';

export type EducatorSummaryModel = { isDemo: boolean; session: LectureSession | null; summary: ProfessorSummary | null; metrics: ProfessorMetrics | null };
const FIXTURE_MODEL: EducatorSummaryModel = { isDemo: true, session: null, summary: null, metrics: null };

/**
 * Builds the detailed anonymous educator lecture report.
 *
 * @returns Educator summary markup with aggregate evidence and delivery feedback.
 */
export function EducatorSummaryPage(model: EducatorSummaryModel = FIXTURE_MODEL): string {
  const summary = model.summary;
  const firstMoment = ACTIVE_LECTURE.moments[0];
  const moments = summary ? buildMomentsFromSummary(summary, model.session ? sessionDurationMs(model.session) : 3_120_000) : ACTIVE_LECTURE.moments;
  const selected = moments[0] ?? firstMoment;
  const suppression = summary?.is_suppressed ? `<p class="empty-state">Fewer than ${summary.minimum_group_size} consenting participants — summary withheld</p>` : '';
  const actions = summary?.suggested_actions?.map((action) => `<li>${action}</li>`).join('') ?? '';

  return AppShell({
    route: 'educator-summary',
    role: 'educator',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
    title: 'Lecture report',
    demoMode: model.isDemo,
    content: `
      ${suppression}<div class="report-heading">
        <div><h2>${ACTIVE_LECTURE.lectureTitle}</h2><p>${summary?.is_suppressed ? 'Anonymous aggregate report withheld below the approved threshold.' : 'Anonymous aggregate report with privacy-safe evidence.'}</p></div>
        <button class="secondary-button" type="button" data-export-report>Export summary</button>
      </div>
      ${LectureTimeline(moments, selected.momentId, model.session ? formatLectureTime(sessionDurationMs(model.session)) : ACTIVE_LECTURE.durationLabel)}
      ${summary?.is_suppressed ? '' : `<section class="report-grid"><div>${MomentDetail(selected, 'educator')}</div><aside class="evidence-card"><p class="eyebrow">Evidence coverage</p><strong>${summary ? `${summary.participant_count} participants` : '68 / 82'}</strong><p>Anonymous participants contributed sufficient data for this lecture.</p><div class="coverage-bar"><i></i></div><small>Individual timelines and identities are never shown.</small></aside></section>`}
      ${actions ? `<section class="section-block"><h2>Suggested actions</h2><ul>${actions}</ul></section>` : ''}
      <section class="section-block delivery-section">
        <div class="delivery-icon" aria-hidden="true">◖</div>
        <div><p class="eyebrow">Delivery quality · 27:40–29:12</p><h2>Possible audio clarity issue</h2><p>Speech-recognition confidence decreased while microphone volume became inconsistent. This is an observable technical condition, not a claim about learning or comprehension.</p></div>
        <div class="key-point"><span>Suggestion</span>Review this interval and consider repeating the explanation next lecture.</div>
      </section>
    `,
  });
}
