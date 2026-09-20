export type StudentSignalLabel = 'phone_visible' | 'student_left_frame';

export interface FrameObservation {
  personScore: number;
  phoneScore: number;
}

export interface StudentSignalPolicy {
  samplingMs: number;
  minimumDurationMs: number;
  maximumSampleGapMs: number;
  personThreshold: number;
  phoneThreshold: number;
}

export const DEFAULT_STUDENT_SIGNAL_POLICY: StudentSignalPolicy = {
  samplingMs: 334,
  minimumDurationMs: 5000,
  maximumSampleGapMs: 2000,
  personThreshold: 0.5,
  phoneThreshold: 0.5,
};

export interface StudentSignalTrackerOptions {
  sessionId: string;
  policy?: StudentSignalPolicy;
}

type Candidate = {
  beginMs: number;
  count: number;
  totalConfidence: number;
};

function clampConfidence(value: number): number {
  return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
}

/**
 * Converts sustained local frame observations into bounded recovery signals.
 *
 * @param options - Session identity and optional temporal policy.
 */
export class StudentSignalTracker {
  private readonly sessionId: string;

  private readonly policy: StudentSignalPolicy;

  private readonly candidates = new Map<StudentSignalLabel, Candidate>();

  private previousMs: number | null = null;

  public constructor({
    sessionId,
    policy = DEFAULT_STUDENT_SIGNAL_POLICY,
  }: StudentSignalTrackerOptions) {
    this.sessionId = sessionId;
    this.policy = policy;
  }

  /**
   * Adds one derived observation and closes any condition that ended.
   *
   * @param observation - Scores produced by local frame analysis.
   * @param lectureTimeMs - Monotonic lecture-relative timestamp.
   * @returns Newly closed sustained signal events.
   * @throws Error If timestamps are invalid or not strictly increasing.
   */
  public observe(observation: FrameObservation, lectureTimeMs: number): SignalEvent[] {
    this.validateTimestamp(lectureTimeMs);
    if (
      this.previousMs !== null &&
      lectureTimeMs - this.previousMs < this.policy.samplingMs
    ) {
      return [];
    }
    if (
      this.previousMs !== null &&
      lectureTimeMs - this.previousMs > this.policy.maximumSampleGapMs
    ) {
      this.candidates.clear();
    }
    this.previousMs = lectureTimeMs;

    const flags: Array<[StudentSignalLabel, boolean, number]> = [
      [
        'student_left_frame',
        observation.personScore < this.policy.personThreshold,
        0.5,
      ],
      [
        'phone_visible',
        observation.phoneScore >= this.policy.phoneThreshold,
        observation.phoneScore,
      ],
    ];
    const events: SignalEvent[] = [];
    for (const [label, isPositive, contribution] of flags) {
      if (isPositive) {
        const candidate = this.candidates.get(label) ?? {
          beginMs: lectureTimeMs,
          count: 0,
          totalConfidence: 0,
        };
        candidate.count += 1;
        candidate.totalConfidence += contribution;
        this.candidates.set(label, candidate);
      } else {
        const candidate = this.candidates.get(label);
        if (candidate) {
          this.candidates.delete(label);
          const event = this.closeCandidate(label, candidate, lectureTimeMs);
          if (event) events.push(event);
        }
      }
    }
    return events;
  }

  /**
   * Closes open candidates at the end of local observation.
   *
   * @param lectureTimeMs - Lecture-relative timestamp at which observation stopped.
   * @returns Sustained events that were open at the final sample.
   * @throws Error If the flush timestamp is not strictly after the last sample.
   */
  public flush(lectureTimeMs: number): SignalEvent[] {
    this.validateTimestamp(lectureTimeMs);
    const events = [...this.candidates].flatMap(([label, candidate]) => {
      const event = this.closeCandidate(label, candidate, lectureTimeMs);
      return event ? [event] : [];
    });
    this.candidates.clear();
    this.previousMs = lectureTimeMs;
    return events;
  }

  /**
   * Clears candidates after camera loss without emitting an inferred event.
   */
  public unavailable(): void {
    this.candidates.clear();
    this.previousMs = null;
  }

  private validateTimestamp(lectureTimeMs: number): void {
    if (
      !Number.isFinite(lectureTimeMs) ||
      lectureTimeMs < 0 ||
      (this.previousMs !== null && lectureTimeMs <= this.previousMs)
    ) {
      throw new Error('Lecture timestamps must increase');
    }
  }

  private closeCandidate(
    label: StudentSignalLabel,
    candidate: Candidate,
    endMs: number,
  ): SignalEvent | null {
    if (endMs - candidate.beginMs < this.policy.minimumDurationMs || candidate.count === 0) {
      return null;
    }
    return {
      event_id: crypto.randomUUID(),
      session_id: this.sessionId,
      event_type: label,
      start_ms: candidate.beginMs,
      end_ms: endMs,
      confidence: clampConfidence(candidate.totalConfidence / candidate.count),
      signals: [label],
      client_generated_at: new Date().toISOString(),
    };
  }
}
