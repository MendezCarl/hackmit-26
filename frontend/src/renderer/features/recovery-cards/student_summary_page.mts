import { AppShell } from '../../components/app_shell.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { ACTIVE_LECTURE, TRANSCRIPT_EXCERPTS } from '../../fixtures/demo_content.mjs';

/**
 * Builds the student lecture-recovery summary and transcript tabs.
 *
 * @returns Student summary markup populated with synthetic lecture fixtures.
 */
export function StudentSummaryPage(): string {
  const firstMoment = ACTIVE_LECTURE.moments[0];

  return AppShell({
    route: 'student-summary',
    role: 'student',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
    title: ACTIVE_LECTURE.lectureTitle,
    content: `
      <div class="summary-meta"><span>${ACTIVE_LECTURE.durationLabel}</span><span>3 recovery moments</span><span>Processed locally</span></div>
      ${LectureTimeline(ACTIVE_LECTURE.moments, firstMoment.momentId)}
      <section class="tab-card" data-summary-tabs>
        <div class="tab-list" role="tablist" aria-label="Lecture content">
          <button class="tab-button is-active" type="button" role="tab" aria-selected="true" data-tab="summary">AI summary</button>
          <button class="tab-button" type="button" role="tab" aria-selected="false" data-tab="transcript">Transcript</button>
        </div>
        <div data-tab-panel="summary">
          ${MomentDetail(firstMoment, 'student')}
        </div>
        <div data-tab-panel="transcript" hidden>
          <div class="transcript-list">
            ${TRANSCRIPT_EXCERPTS.map(
              (excerpt) => `
                <div class="transcript-line">
                  <span>${excerpt.timeLabel}</span>
                  <p><strong>${excerpt.speaker}</strong>${excerpt.text}</p>
                </div>`,
            ).join('')}
          </div>
        </div>
      </section>
    `,
  });
}
