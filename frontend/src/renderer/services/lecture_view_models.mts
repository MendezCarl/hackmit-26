import type { LectureMoment } from '../fixtures/demo_content.mjs';

/** Formats lecture-relative milliseconds as a zero-padded minute/second label. */
export function formatLectureTime(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`;
}

const buildMoment = (
  startMs: number,
  endMs: number,
  title: string,
  summary: string,
  evidence: string,
  action: string,
  sessionDurationMs: number,
): LectureMoment => ({
  momentId: `${startMs}-${endMs}`,
  startLabel: formatLectureTime(startMs),
  endLabel: formatLectureTime(endMs),
  startPercent: sessionDurationMs > 0 ? Math.round((startMs / sessionDurationMs) * 100) : 0,
  widthPercent:
    sessionDurationMs > 0
      ? Math.max(2, Math.round(((endMs - startMs) / sessionDurationMs) * 100))
      : 2,
  title,
  summary,
  evidence,
  action,
  severity: 'review',
});

/** Maps submitted personal signals to student recovery moments. */
export function buildMomentsFromEvents(
  events: SignalEvent[],
  sessionDurationMs: number,
): LectureMoment[] {
  return events.map((event) =>
    buildMoment(
      event.start_ms,
      event.end_ms,
      'Possible missed-content moment',
      'You marked this interval as worth revisiting.',
      'Personal recovery signal',
      'Request a grounded recovery card for this interval.',
      sessionDurationMs,
    ),
  );
}

/** Maps an anonymous professor summary to recovery-safe aggregate moments. */
export function buildMomentsFromSummary(
  summary: ProfessorSummary,
  sessionDurationMs: number,
): LectureMoment[] {
  return (summary.highest_signal_intervals ?? []).map((interval) =>
    buildMoment(
      interval.start_ms,
      interval.end_ms,
      'Possible missed-content moment',
      'Anonymous aggregate evidence identifies an interval worth reviewing.',
      `${interval.event_count} anonymous recovery signals`,
      'Review this interval and consider an optional recap.',
      sessionDurationMs,
    ),
  );
}

/**
 * Maps policy-gated professor metrics to privacy-safe timeline moments.
 *
 * Buckets that round to the same rendered timeline position are merged so
 * their evidence and suggested actions remain readable in one marker.
 *
 * @param metrics - Aggregated metrics returned by the professor report API.
 * @param sessionDurationMs - Total lecture duration in milliseconds.
 * @returns Privacy-safe timeline moments deduplicated by marker position.
 */
export function buildMomentsFromMetrics(
  metrics: ProfessorMetrics,
  sessionDurationMs: number,
): LectureMoment[] {
  const moments = metrics.buckets.map((bucket) => {
    const ratio = bucket.possible_missed?.ratio;
    const hasHotspot = bucket.is_hotspot === true && ratio !== undefined;
    const title = hasHotspot
      ? 'Possible missed-content moment'
      : bucket.status === 'suppressed'
        ? 'Aggregate interval suppressed'
        : 'Insufficient evidence';
    const evidence = hasHotspot
      ? `${Math.round(ratio * 100)}% possible missed-content signals`
      : bucket.status === 'suppressed'
        ? 'This interval is withheld by the aggregation policy.'
        : 'This interval did not meet the evidence threshold.';
    return buildMoment(
      bucket.start_ms,
      bucket.end_ms,
      title,
      evidence,
      evidence,
      bucket.suggested_action ?? 'No action suggested for this interval.',
      sessionDurationMs,
    );
  });

  return Array.from(
    moments.reduce((byPosition, moment) => {
      const existing = byPosition.get(moment.startPercent);
      if (!existing) {
        byPosition.set(moment.startPercent, moment);
        return byPosition;
      }
      existing.title = `${existing.title} · ${moment.title}`;
      existing.summary = `${existing.summary} ${moment.summary}`;
      existing.evidence = `${existing.evidence} ${moment.evidence}`;
      existing.action = `${existing.action} ${moment.action}`;
      existing.endLabel = moment.endLabel;
      existing.widthPercent = Math.max(existing.widthPercent, moment.widthPercent);
      return byPosition;
    }, new Map<number, LectureMoment>()),
  ).map(([, moment]) => moment);
}

/** Maps one private recovery card to the existing lecture moment view. */
export function buildMomentFromRecoveryCard(
  card: RecoveryCard,
  sessionDurationMs: number,
): LectureMoment {
  const source = card.source_timestamps[0] ?? { start_ms: 0, end_ms: 1 };
  return buildMoment(
    source.start_ms,
    source.end_ms,
    card.topic,
    card.what_you_missed,
    card.key_facts.join(' '),
    card.follow_up_question,
    sessionDurationMs,
  );
}

/** Maps transcript chunks to the existing transcript excerpt view. */
export function buildTranscriptExcerpts(
  chunks: TranscriptChunk[],
): Array<{ timeLabel: string; speaker: string; text: string }> {
  return chunks.map((chunk) => ({
    timeLabel: formatLectureTime(chunk.start_ms),
    speaker: chunk.speaker_label ?? 'Professor',
    text: chunk.text,
  }));
}

/** Computes elapsed lecture duration from the shared session clock. */
export function sessionDurationMs(
  session: LectureSession,
  nowIso = new Date().toISOString(),
): number {
  const end = session.ended_at ?? nowIso;
  return Math.max(0, Date.parse(end) - Date.parse(session.session_clock_origin));
}
