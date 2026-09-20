import { AppShell } from '../../components/app_shell.mjs';
import { escapeHtml } from '../../components/html_text.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MetricCard } from '../../components/metric_card.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { TeachingMomentsPanel } from '../../components/teaching_moments_panel.mjs';
import { ZoomLiveTranscriptPanel } from '../../components/zoom_live_transcript_panel.mjs';
import { ACTIVE_LECTURE } from '../../fixtures/demo_content.mjs';
import type { TeachingMomentsState } from '../../services/backend_session_state.mjs';
import {
  buildMomentsFromMetrics,
  buildMomentsFromSummary,
  formatLectureTime,
  sessionDurationMs,
} from '../../services/lecture_view_models.mjs';

export type LectureSummaryPageModel = {
  isDemo: boolean;
  profileName?: string;
  lecture: Lecture | null;
  course: Course | null;
  session: LectureSession | null;
  allCourses: Course[];
  allLecturesByCourse: Record<string, Lecture[]>;
  summary: ProfessorSummary | null;
  metrics: ProfessorMetrics | null;
  zoomStatus?: ZoomRtmsStatus | null;
  teachingMoments?: TeachingMomentsState | null;
  routeError?: string | null;
};

const FIXTURE_MODEL: LectureSummaryPageModel = {
  isDemo: true,
  lecture: null,
  course: null,
  session: null,
  allCourses: [],
  allLecturesByCourse: {},
  summary: null,
  metrics: null,
};

/**
 * Builds a lecture-specific anonymous report and timeline.
 *
 * @param model - Selected lecture, latest session, and aggregate report.
 * @returns Lecture summary page markup.
 */
export function LectureSummaryPage(model: LectureSummaryPageModel = FIXTURE_MODEL): string {
  if (model.isDemo) {
    return AppShell({
      route: 'lecture',
      role: 'educator',
      profileName: model.profileName,
      eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
      title: ACTIVE_LECTURE.lectureTitle,
      demoMode: true,
      content: `
        <section class="metrics-grid">${MetricCard('Lecture continuity', '78%', 'Mean across this lecture', 'teal')}${MetricCard('Recovery hotspots', '3', 'Anonymous intervals worth reviewing', 'gold')}${MetricCard('Delivery notes', '1', 'Possible delivery conditions to review', 'slate')}${MetricCard('Participants', '68', 'Aggregate consenting participant count', 'sage')}</section>
        ${LectureTimeline(ACTIVE_LECTURE.moments, ACTIVE_LECTURE.moments[0]?.momentId, ACTIVE_LECTURE.durationLabel)}
        <section class="report-grid"><div>${MomentDetail(ACTIVE_LECTURE.moments[0], 'educator')}</div></section>
      `,
    });
  }
  if (!model.lecture || !model.course) {
    return AppShell({
      route: 'lecture',
      role: 'educator',
      title: 'Lecture not found',
      demoMode: false,
      content: '<section class="panel"><p class="empty-state">That lecture could not be found.</p></section>',
    });
  }
  if (!model.session) {
    return AppShell({
      route: 'lecture',
      role: 'educator',
      profileName: model.profileName,
      eyebrow: model.course.code,
      title: model.lecture.title,
      demoMode: false,
      courses: model.allCourses,
      lecturesByCourse: model.allLecturesByCourse,
      currentCourseId: model.course.course_id,
      currentLectureId: model.lecture.lecture_id,
      content: `
        <section class="panel"><p class="empty-state">No sessions yet for this lecture</p><button class="primary-button" type="button" data-start-session="${escapeHtml(model.lecture.lecture_id)}" data-course-id="${escapeHtml(model.course.course_id)}" data-lecture-title="${escapeHtml(model.lecture.title)}">Start session</button></section>
      `,
    });
  }
  const duration = sessionDurationMs(model.session);
  const moments = model.metrics
    ? buildMomentsFromMetrics(model.metrics, duration)
    : model.summary
      ? buildMomentsFromSummary(model.summary, duration)
      : [];
  const selected = moments[0];
  const continuity = model.metrics?.continuity
    ? `${Math.round(model.metrics.continuity.ratio * 100)}%`
    : 'Withheld';
  const hotspotCount =
    model.metrics?.buckets.filter((bucket) => bucket.is_hotspot === true).length ?? 0;
  const findingCount = model.metrics?.delivery_findings.length ?? 0;
  const participantValue = model.summary?.is_suppressed
    ? 'Withheld'
    : String(model.summary?.participant_count ?? 'Withheld');
  const actions = model.summary?.suggested_actions?.map((action) => `<li>${escapeHtml(action)}</li>`).join('');
  const teachingMoments = model.teachingMoments
    ? TeachingMomentsPanel({ session: model.session, state: model.teachingMoments })
    : '';
  return AppShell({
    route: 'lecture',
    role: 'educator',
    profileName: model.profileName,
    eyebrow: model.course.code,
    title: model.lecture.title,
    demoMode: false,
    courses: model.allCourses,
    lecturesByCourse: model.allLecturesByCourse,
    currentCourseId: model.course.course_id,
    currentLectureId: model.lecture.lecture_id,
    content: `
      <section class="metrics-grid">${MetricCard('Lecture continuity', continuity, 'Mean across this lecture', 'teal')}${MetricCard('Recovery hotspots', String(hotspotCount), 'Anonymous intervals worth reviewing', 'gold')}${MetricCard('Delivery notes', String(findingCount), 'Possible delivery conditions to review', 'slate')}${MetricCard('Participants', participantValue, 'Aggregate consenting participant count', 'sage')}</section>
      ${model.summary?.is_suppressed ? `<p class="empty-state">Fewer than ${model.summary.minimum_group_size} consenting participants — summary withheld</p>` : ''}
      ${model.session.status === 'active' ? `<section class="panel session-banner"><strong>Session is active</strong><span>Join code: ${escapeHtml(model.session.join_code)}</span><button class="danger-button" type="button" data-end-session="${escapeHtml(model.session.session_id)}">End session</button></section>${ZoomLiveTranscriptPanel({ session: model.session, status: model.zoomStatus ?? null })}` : ''}
      ${selected ? `${LectureTimeline(moments, selected.momentId, formatLectureTime(duration))}<section class="report-grid"><div>${MomentDetail(selected, 'educator')}</div></section>` : '<section class="panel"><p class="empty-state">No report intervals are available for this session.</p></section>'}
      ${actions ? `<section class="panel"><h2>Suggested actions</h2><ul>${actions}</ul></section>` : ''}
      ${teachingMoments}
      ${(model.metrics?.delivery_findings ?? []).map((finding) => `<section class="panel delivery-section"><div><p class="eyebrow">Delivery note · ${formatLectureTime(finding.start_ms)}–${formatLectureTime(finding.end_ms)}</p><h2>${escapeHtml(finding.signal_type)}</h2><p>Confidence ${Math.round(finding.confidence * 100)}%.</p></div><div class="key-point"><span>Suggestion</span>${escapeHtml(finding.suggested_action)}</div></section>`).join('')}
    `,
  });
}
