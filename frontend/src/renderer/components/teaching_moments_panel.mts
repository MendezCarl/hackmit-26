import type { TeachingMomentsState } from '../services/backend_session_state.mjs';
import { formatLectureTime } from '../services/lecture_view_models.mjs';
import { escapeHtml } from './html_text.mjs';

export type TeachingMomentsPanelModel = {
  session: LectureSession;
  state: TeachingMomentsState;
};

const MEDIUM_LABELS: Record<RecommendationMedium, string> = {
  explanation: 'Explanation',
  pace: 'Pace',
  example: 'Example',
  terminology: 'Terminology',
};

const REVIEW_LABELS: Record<RecommendationReviewStatus, string> = {
  reviewed: 'Reviewed',
  dismissed: 'Dismissed',
  resolved: 'Resolved',
};

const REVIEW_ACTIONS: RecommendationReviewStatus[] = ['reviewed', 'resolved', 'dismissed'];

/**
 * Finds the professor's latest review for one moment of the report.
 *
 * @param report - Current teaching-moments report.
 * @param index - Position of the moment inside `report.recommendations`.
 * @returns The stored review or null when the moment is still unreviewed.
 */
export function findTeachingMomentReview(
  report: RecommendationReport,
  index: number,
): RecommendationReview | null {
  return (
    (report.reviews ?? []).find(
      (review) =>
        review.recommendation_index === index &&
        review.report_revision === report.report_revision,
    ) ?? null
  );
}

/**
 * Describes where a report's evidence came from in plain language.
 *
 * @param report - Current teaching-moments report.
 * @returns One sentence for the professor; never implies attention or comprehension.
 */
export function describeEvidenceScope(report: RecommendationReport): string {
  if (report.evidence_scope === 'lecture_transcript') {
    return 'Grounded in your lecture transcript for each anonymous hotspot interval.';
  }
  return 'Based on anonymous hotspot timing only — no lecture transcript was analyzed.';
}

const renderEvidence = (evidence: RecommendationEvidence[]): string => {
  if (evidence.length === 0) return '<p class="teaching-moment__evidence-empty">No transcript quote available.</p>';
  return `<ul class="teaching-moment__evidence">${evidence
    .map(
      (fact) =>
        `<li><q>${escapeHtml(fact.evidence_quote)}</q>${fact.text !== fact.evidence_quote ? `<span>${escapeHtml(fact.text)}</span>` : ''}</li>`,
    )
    .join('')}</ul>`;
};

const renderMoment = (
  sessionId: string,
  report: RecommendationReport,
  recommendation: Recommendation,
  index: number,
): string => {
  const review = findTeachingMomentReview(report, index);
  const badge = review
    ? `<span class="status-badge status-badge--ready" data-teaching-moment-status="${review.status}"><i></i>${REVIEW_LABELS[review.status]}</span>`
    : `<span class="status-badge status-badge--review" data-teaching-moment-status="new"><i></i>New</span>`;
  const topic = recommendation.topic ? escapeHtml(recommendation.topic) : 'Interval without transcript topic';
  const medium = recommendation.medium ? ` · ${MEDIUM_LABELS[recommendation.medium]}` : '';
  const actions = REVIEW_ACTIONS.filter((status) => status !== review?.status)
    .map(
      (status) =>
        `<button class="secondary-button" type="button" data-review-teaching-moment="${escapeHtml(sessionId)}" data-review-index="${index}" data-review-status="${status}">${REVIEW_LABELS[status]}</button>`,
    )
    .join('');
  return `
    <article class="panel teaching-moment${review?.status === 'dismissed' ? ' is-dismissed' : ''}" data-teaching-moment="${index}">
      <header class="teaching-moment__header">
        <div>
          <p class="eyebrow">${formatLectureTime(recommendation.start_ms)}–${formatLectureTime(recommendation.end_ms)}${medium}</p>
          <h3>${topic}</h3>
        </div>
        ${badge}
      </header>
      <p><strong>Observation.</strong> ${escapeHtml(recommendation.observation)}</p>
      ${renderEvidence(recommendation.evidence ?? [])}
      <div class="key-point"><span>Suggested action</span>${escapeHtml(recommendation.suggested_action)}</div>
      <div class="teaching-moment__actions">${actions}</div>
    </article>`;
};

const renderReport = (sessionId: string, report: RecommendationReport): string => {
  const note = report.evidence_note
    ? `<p class="form-message" data-teaching-evidence-note>${escapeHtml(report.evidence_note)}</p>`
    : '';
  if (report.status === 'insufficient_evidence' || report.recommendations.length === 0) {
    return `
      <p class="empty-state" data-teaching-insufficient>Not enough anonymous evidence to suggest teaching moments for this lecture yet.</p>
      ${note}`;
  }
  return `
    <p class="summary-meta" data-teaching-evidence-scope>${escapeHtml(describeEvidenceScope(report))}</p>
    ${note}
    <div class="teaching-moments__list">${report.recommendations
      .map((recommendation, index) => renderMoment(sessionId, report, recommendation, index))
      .join('')}</div>`;
};

/**
 * Renders the professor's "Teaching moments" panel: a consent toggle for AI
 * review of their own lecture transcript, an explicit Analyze action, and the
 * resulting reviewable suggestions. Nothing is generated until Analyze is clicked.
 *
 * @param model - Lecture session and the current teaching-moments state.
 * @returns Panel markup.
 */
export function TeachingMomentsPanel(model: TeachingMomentsPanelModel): string {
  const { session, state } = model;
  const current = state.sessionId === session.session_id ? state : null;
  const isLoading = current?.status === 'loading';
  const report = current?.report ?? null;
  const consentChecked = current?.transcriptConsentGranted ? 'checked' : '';
  const consentNote = current?.consentNote
    ? `<p class="form-message" data-teaching-consent-message aria-live="polite">${escapeHtml(current.consentNote)}</p>`
    : '<p class="form-message" data-teaching-consent-message aria-live="polite"></p>';
  const error = current?.status === 'failed' && current.error
    ? `<p class="empty-state" data-teaching-error>Teaching moments unavailable: ${escapeHtml(current.error)}</p>`
    : current?.error
      ? `<p class="form-message" data-teaching-error>${escapeHtml(current.error)}</p>`
      : '';
  return `
    <section class="section-block teaching-moments" data-teaching-moments>
      <div class="report-heading">
        <div>
          <h2>Teaching moments</h2>
          <p>Reviewable suggestions about what was taught during anonymous hotspots. Observations describe lecture content and timing only, never any student's attention or understanding.</p>
        </div>
        <button class="primary-button" type="button" data-analyze-teaching-moments="${escapeHtml(session.session_id)}" ${isLoading ? 'disabled' : ''}>${isLoading ? 'Analyzing…' : report ? 'Analyze again' : 'Analyze'}</button>
      </div>
      <label class="teaching-moments__consent">
        <input type="checkbox" data-teaching-transcript-consent="${escapeHtml(session.session_id)}" ${consentChecked} />
        Allow AI review of my lecture transcript (bounded excerpts from hotspot intervals only; no speaker labels or student data)
      </label>
      ${consentNote}
      ${error}
      ${isLoading ? '<p class="empty-state">Analyzing lecture hotspots…</p>' : ''}
      ${report ? renderReport(session.session_id, report) : !isLoading ? '<p class="empty-state" data-teaching-idle>Click Analyze to review teaching moments for this lecture.</p>' : ''}
    </section>`;
}
