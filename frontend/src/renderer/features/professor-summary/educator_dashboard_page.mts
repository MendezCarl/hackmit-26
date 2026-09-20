import { buildRouteHash } from '../../app/router.mjs';
import { AppShell } from '../../components/app_shell.mjs';
import { MetricCard } from '../../components/metric_card.mjs';
import { ACTIVE_LECTURE } from '../../fixtures/demo_content.mjs';

export type EducatorDashboardModel = { isDemo: boolean; courses: Course[]; lecturesByCourse: Record<string, Lecture[]>; activeSession: LectureSession | null };
const FIXTURE_MODEL: EducatorDashboardModel = { isDemo: true, courses: [], lecturesByCourse: {}, activeSession: null };

/**
 * Builds the educator course-insights dashboard.
 *
 * @returns Educator dashboard markup with anonymous synthetic metrics.
 */
export function EducatorDashboardPage(model: EducatorDashboardModel = FIXTURE_MODEL): string {
  const courses = model.courses;
  const lectures = courses.flatMap((course) => model.lecturesByCourse[course.course_id] ?? []);
  return AppShell({
    route: 'educator-dashboard',
    role: 'educator',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · Post-lecture overview`,
    title: 'Teach forward with clearer evidence.',
    demoMode: model.isDemo,
    content: `
      <section class="section-block"><form data-course-form><p class="eyebrow">Course setup</p><label>Course code<input name="code" required /></label><label>Course title<input name="title" required /></label><button class="secondary-button" type="submit">Create course</button></form><form data-lecture-form><label>Course<select name="course_id" required>${courses.map((course) => `<option value="${course.course_id}">${course.code} · ${course.title}</option>`).join('')}</select></label><label>Lecture title<input name="title" required /></label><button class="secondary-button" type="submit">Create lecture</button></form><p class="form-message" data-educator-message></p></section>
      ${model.activeSession ? `<article class="feature-card feature-card--primary"><p class="eyebrow">Active session</p><h2>${model.activeSession.title}</h2><p>Join code: <strong>${model.activeSession.session_id}</strong></p><button class="danger-button" type="button" data-end-session>End session</button></article>` : ''}
      <section class="metrics-grid" aria-label="Lecture metrics">
        ${MetricCard('Lecture continuity', '78%', '41 of 52 valid intervals had no hotspot', 'teal')}
        ${MetricCard('Evidence coverage', '83%', '68 of 82 opted-in participants', 'sage')}
        ${MetricCard('Recovery hotspots', '3', 'Anonymous intervals worth reviewing', 'gold')}
        ${MetricCard('Delivery notes', '1', 'Possible audio clarity issue', 'slate')}
      </section>
      <section class="dashboard-grid">
        <article class="chart-card chart-card--wide">
          <div class="section-heading-row"><div><p class="eyebrow">Across the lecture</p><h2>Lecture continuity</h2></div><span class="chart-caption">5-minute windows</span></div>
          <svg class="line-chart" viewBox="0 0 720 220" role="img" aria-labelledby="continuity-chart-title continuity-chart-desc">
            <title id="continuity-chart-title">Lecture continuity over time</title>
            <desc id="continuity-chart-desc">Continuity is lower around minutes thirteen, twenty-eight, and forty-two.</desc>
            <g class="chart-grid-lines" stroke="#d9d9d2" stroke-width="1"><line x1="50" y1="30" x2="690" y2="30"/><line x1="50" y1="95" x2="690" y2="95"/><line x1="50" y1="160" x2="690" y2="160"/></g>
            <path class="chart-area" fill="#8fc0a9" fill-opacity="0.22" d="M50,54 L114,63 L178,139 L242,78 L306,68 L370,147 L434,87 L498,72 L562,153 L626,89 L690,65 L690,190 L50,190 Z"/>
            <polyline class="chart-line" fill="none" stroke="#557f71" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" points="50,54 114,63 178,139 242,78 306,68 370,147 434,87 498,72 562,153 626,89 690,65"/>
            <g class="chart-axis-labels" fill="#696d7d"><text x="45" y="210">0</text><text x="170" y="210">10</text><text x="300" y="210">20</text><text x="430" y="210">30</text><text x="555" y="210">40</text><text x="680" y="210">50 min</text></g>
          </svg>
        </article>
        <article class="chart-card">
          <p class="eyebrow">Concept checks</p><h2>Valid response accuracy</h2>
          <div class="bar-list">
            <div><span>Glycolysis</span><strong>81%</strong><i class="bar-width-81"></i></div>
            <div><span>Electron transport</span><strong>68%</strong><i class="bar-width-68"></i></div>
            <div><span>ATP synthase</span><strong>61%</strong><i class="bar-width-61"></i></div>
          </div>
        </article>
      </section>
      <section class="section-block">
        <div class="section-heading-row"><div><p class="eyebrow">Next step</p><h2>Moments to review</h2></div><a class="text-link" href="${buildRouteHash('educator-summary')}">Open full report →</a></div>
        <div class="review-table" role="table" aria-label="Moments to review">
          <div class="review-table__header" role="row"><span>Time</span><span>Topic</span><span>Aggregate evidence</span><span>Suggested action</span></div>
          ${ACTIVE_LECTURE.moments.map((moment) => `<a class="review-table__row" role="row" href="${buildRouteHash('educator-summary')}"><span>${moment.startLabel}</span><strong>${moment.title}</strong><span>${moment.evidence}</span><span>${moment.action}</span></a>`).join('')}
        </div>
      </section>
      <section class="section-block"><h2>Lectures</h2><div class="lecture-row-list">${lectures.map((lecture) => `<div class="lecture-row"><span><strong>${lecture.title}</strong><small>${lecture.course_id}</small></span><button class="primary-button" type="button" data-start-session="${lecture.lecture_id}" data-course-id="${lecture.course_id}" data-lecture-title="${lecture.title}">Start session</button></div>`).join('')}</div></section>
    `,
  });
}
