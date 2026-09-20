import {
  getBackendSessionState,
  recordTeachingMomentReview,
  setTeachingMoments,
  type TeachingMomentsState,
} from './backend_session_state.mjs';

/** Provider the backend uses for live teaching-moment analysis. */
export const TEACHING_MOMENTS_PROVIDER: ExternalTextProvider = 'openai';

export const MOCK_PROVIDER_NOTE =
  'Local mock provider — your lecture transcript is analyzed on this Bloom service and never sent externally.';

const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : 'The Bloom service could not complete that request.';

/**
 * Generates teaching moments for one lecture. Called only from the professor's
 * explicit Analyze action; the backend decides whether transcript excerpts are
 * used based on the consent recorded via {@link setTeachingTranscriptConsent}.
 *
 * @param sessionId - Lecture session to analyze.
 * @returns Resolves once the report or its error is stored in renderer state.
 */
export async function analyzeTeachingMoments(sessionId: string): Promise<void> {
  setTeachingMoments(sessionId, { status: 'loading', error: null });
  try {
    const report = await window.backend.generateProfessorRecommendations(sessionId);
    setTeachingMoments(sessionId, { status: 'ready', report, error: null });
  } catch (error) {
    setTeachingMoments(sessionId, { status: 'failed', error: errorMessage(error) });
  }
}

/**
 * Records the professor's decision about sending bounded lecture-transcript
 * excerpts to the live analysis provider. With the mock provider nothing leaves
 * the Bloom service, so the toggle is explained rather than forwarded.
 *
 * @param sessionId - Lecture session the consent applies to.
 * @param isAllowed - Whether transcript excerpts may be sent to the live provider.
 * @returns Resolves once the consent result or its error is stored in renderer state.
 */
export async function setTeachingTranscriptConsent(
  sessionId: string,
  isAllowed: boolean,
): Promise<void> {
  try {
    const status = await window.backend.readApiStatus();
    if (status.recovery_provider === 'mock') {
      setTeachingMoments(sessionId, {
        transcriptConsentGranted: false,
        consentNote: MOCK_PROVIDER_NOTE,
      });
      return;
    }
    const consent = await window.backend.updateExternalTextConsent(sessionId, {
      provider: TEACHING_MOMENTS_PROVIDER,
      is_allowed: isAllowed,
    });
    setTeachingMoments(sessionId, {
      transcriptConsentGranted: consent.is_allowed,
      consentNote: null,
    });
  } catch (error) {
    setTeachingMoments(sessionId, { consentNote: errorMessage(error) });
  }
}

/**
 * Sends a review decision for one teaching moment of the current report.
 *
 * @param sessionId - Lecture session the report belongs to.
 * @param recommendationIndex - Position of the moment inside the current report.
 * @param status - Review outcome chosen by the professor.
 * @returns Resolves once the review (or its error) is reflected in renderer state.
 */
export async function reviewTeachingMoment(
  sessionId: string,
  recommendationIndex: number,
  status: RecommendationReviewStatus,
): Promise<void> {
  const current = readTeachingMoments();
  if (current.sessionId !== sessionId || !current.report) return;
  try {
    const review = await window.backend.reviewProfessorRecommendation(sessionId, {
      report_revision: current.report.report_revision,
      recommendation_index: recommendationIndex,
      status,
    });
    recordTeachingMomentReview(sessionId, review);
    setTeachingMoments(sessionId, { error: null });
  } catch (error) {
    setTeachingMoments(sessionId, { error: errorMessage(error) });
  }
}

/** Returns the current teaching-moments state for rendering. */
export function readTeachingMoments(): TeachingMomentsState {
  return getBackendSessionState().teachingMoments;
}
