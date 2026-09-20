import { AppShell } from '../../components/app_shell.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { ACTIVE_LECTURE } from '../../fixtures/demo_content.mjs';

/**
 * Builds the detailed anonymous educator lecture report.
 *
 * @returns Educator summary markup with aggregate evidence and delivery feedback.
 */
export function EducatorSummaryPage(): string {
  const firstMoment = ACTIVE_LECTURE.moments[0];

  return AppShell({
    route: 'educator-summary',
    role: 'educator',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
    title: 'Lecture report',
    content: `
      <div class="report-heading">
        <div><h2>${ACTIVE_LECTURE.lectureTitle}</h2><p>Anonymous aggregate report · 68 of 82 opted-in participants contributed sufficient data.</p></div>
        <button class="secondary-button" type="button" data-export-report>Export summary</button>
      </div>
      ${LectureTimeline(ACTIVE_LECTURE.moments, firstMoment.momentId)}
      <section class="report-grid">
        <div>
          ${MomentDetail(firstMoment, 'educator')}
        </div>
        <aside class="evidence-card">
          <p class="eyebrow">Evidence coverage</p><strong>68 / 82</strong><p>83% of opted-in participants contributed sufficient data for this lecture.</p>
          <div class="coverage-bar"><i></i></div>
          <small>Individual timelines and identities are never shown.</small>
        </aside>
      </section>
      <section class="section-block delivery-section">
        <div class="delivery-icon" aria-hidden="true">◖</div>
        <div><p class="eyebrow">Delivery quality · 27:40–29:12</p><h2>Possible audio clarity issue</h2><p>Speech-recognition confidence decreased while microphone volume became inconsistent. This is an observable technical condition, not a claim about student attention.</p></div>
        <div class="key-point"><span>Suggestion</span>Review this interval and consider repeating the explanation next lecture.</div>
      </section>
    `,
  });
}
