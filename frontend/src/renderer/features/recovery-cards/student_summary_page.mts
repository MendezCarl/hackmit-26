import { AppShell } from '../../components/app_shell.mjs';
import { LectureTimeline } from '../../components/lecture_timeline.mjs';
import { MomentDetail } from '../../components/moment_detail.mjs';
import { ACTIVE_LECTURE, TRANSCRIPT_EXCERPTS } from '../../fixtures/demo_content.mjs';
import {
  buildMomentsFromEvents,
  buildTranscriptExcerpts,
  formatLectureTime,
  sessionDurationMs,
} from '../../services/lecture_view_models.mjs';

export type StudentSummaryModel = {
  isDemo: boolean;
  session: LectureSession | null;
  submittedEvents: SignalEvent[];
  recoveryCards: RecoveryCard[];
  transcript: TranscriptChunk[];
  routeError?: string | null;
  isLoading?: boolean;
};
const FIXTURE_MODEL: StudentSummaryModel = {
  isDemo: true,
  session: null,
  submittedEvents: [],
  recoveryCards: [],
  transcript: [],
};

/**
 * Builds the student lecture-recovery summary and transcript tabs.
 *
 * @returns Student summary markup populated with synthetic lecture fixtures.
 */
export function StudentSummaryPage(model: StudentSummaryModel = FIXTURE_MODEL): string {
  if (!model.isDemo) return buildRealStudentSummary(model);

  const moments = ACTIVE_LECTURE.moments;
  const firstMoment = moments[0];
  const transcript = TRANSCRIPT_EXCERPTS;
  const card = model.recoveryCards[0];

  return AppShell({
    route: 'student-summary',
    role: 'student',
    eyebrow: `${ACTIVE_LECTURE.courseCode} · ${ACTIVE_LECTURE.lectureDate}`,
    title: ACTIVE_LECTURE.lectureTitle,
    demoMode: model.isDemo,
    content: `
      <div class="summary-meta"><span>${ACTIVE_LECTURE.durationLabel}</span><span>${moments.length} recovery moments</span><span>Processed locally</span></div>
      ${LectureTimeline(moments, firstMoment.momentId)}
      ${card ? `<article class="moment-detail"><p class="eyebrow">Recovery card · ${card.model_metadata.provider_mode} · ${card.model_metadata.data_label}</p><h3>${card.topic}</h3><p>${card.what_you_missed}</p><ul>${card.key_facts.map((fact) => `<li>${fact}</li>`).join('')}</ul><p>${card.example_from_lecture ?? ''}</p><p>${card.follow_up_question}</p><small>Sources: ${card.source_timestamps.map((source) => `${formatLectureTime(source.start_ms)}–${formatLectureTime(source.end_ms)}`).join(', ')}</small></article>` : ''}
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
            ${transcript
              .map(
                (excerpt) => `
                <div class="transcript-line">
                  <span>${excerpt.timeLabel}</span>
                  <p><strong>${excerpt.speaker}</strong>${excerpt.text}</p>
                </div>`,
              )
              .join('')}
          </div>
        </div>
      </section>
    `,
  });
}

function buildRealStudentSummary(model: StudentSummaryModel): string {
  const session = model.session;
  const moments = session
    ? buildMomentsFromEvents(model.submittedEvents, sessionDurationMs(session))
    : [];
  const transcript = buildTranscriptExcerpts(model.transcript);
  const firstMoment = moments[0];
  return AppShell({
    route: 'student-summary',
    role: 'student',
    eyebrow: session ? `Session ${session.course_id}` : 'Student summary',
    title: session?.title ?? 'Lecture summary',
    demoMode: false,
    content: `
      ${model.isLoading ? '<p class="empty-state">Loading from local service…</p>' : ''}
      ${model.routeError ? `<p class="empty-state">Summary unavailable: ${model.routeError}</p>` : ''}
      <div class="summary-meta"><span>${session ? formatLectureTime(sessionDurationMs(session)) : 'No session clock'}</span><span>${moments.length} recovery moments</span><span>Processed locally</span></div>
      ${moments.length && firstMoment ? LectureTimeline(moments, firstMoment.momentId) : '<p class="empty-state">Mark a moment with “I missed that” during a lecture</p>'}
      ${model.submittedEvents.length ? `<div class="moment-actions">${model.submittedEvents.map((event) => `<button class="secondary-button" type="button" data-request-recovery="${event.event_id}">Request recovery card for ${formatLectureTime(event.start_ms)}</button>`).join('')}</div>` : ''}
      ${model.recoveryCards
        .map(
          (card) => `
        <article class="moment-detail">
          <p class="eyebrow">Recovery card · ${card.model_metadata.provider_mode} · ${card.model_metadata.data_label}</p>
          <h3>${card.topic}</h3>
          <p>${card.what_you_missed}</p>
          <ul>${card.key_facts.map((fact) => `<li>${fact}</li>`).join('')}</ul>
          <p>${card.example_from_lecture ?? ''}</p>
          <p>${card.follow_up_question}</p>
          <small>Sources: ${card.source_timestamps.map((source) => `${formatLectureTime(source.start_ms)}–${formatLectureTime(source.end_ms)}`).join(', ')}</small>
        </article>`,
        )
        .join('')}
      <section class="tab-card" data-summary-tabs>
        <div class="tab-list" role="tablist" aria-label="Lecture content">
          <button class="tab-button is-active" type="button" role="tab" aria-selected="true" data-tab="summary">AI summary</button>
          <button class="tab-button" type="button" role="tab" aria-selected="false" data-tab="transcript">Transcript</button>
        </div>
        <div data-tab-panel="summary">
          ${firstMoment ? MomentDetail(firstMoment, 'student') : '<p class="empty-state">No recovery moments have been submitted.</p>'}
        </div>
        <div data-tab-panel="transcript" hidden>
          ${
            transcript.length
              ? `<div class="transcript-list">${transcript
                  .map(
                    (excerpt) => `
            <div class="transcript-line"><span>${excerpt.timeLabel}</span><p><strong>${excerpt.speaker}</strong>${excerpt.text}</p></div>`,
                  )
                  .join('')}</div>`
              : '<p class="empty-state">No transcript chunks are available for this session.</p>'
          }
        </div>
      </section>
    `,
  });
}
