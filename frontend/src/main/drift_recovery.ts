import { randomUUID } from 'node:crypto';

/** Drift event details the renderer hands to the main process for in-overlay recovery. */
export type DriftRecoveryRequest = {
  session_id: string;
  event_id: string;
  start_ms: number;
  end_ms: number;
};

/** Overlay-facing lifecycle of one recovery-card request. */
export type DriftRecoveryState =
  | { status: 'loading'; request: DriftRecoveryRequest }
  | { status: 'ready'; request: DriftRecoveryRequest; card: RecoveryCard }
  | { status: 'failed'; request: DriftRecoveryRequest; message: string };

/** Subset of the backend client needed to turn a drift event into a card. */
export type RecoveryCardClient = {
  requestRecoveryCard: (
    sessionId: string,
    request: CreateRecoveryJobRequest,
    idempotencyKey?: string,
  ) => Promise<RecoveryJob>;
  readRecoveryCard: (sessionId: string, cardId: string) => Promise<RecoveryCard>;
};

/** Views the main window can be asked to show when the student leaves the overlay. */
export type OverlayOpenView = 'default' | 'recovery-summary';

/**
 * What the main process must do for one `overlay:action` message.
 *
 * Only `open` brings the main Bloom window forward; `recover` keeps Zoom in the
 * foreground and runs the recovery request inside the overlay.
 */
export type OverlayActionPlan =
  | { kind: 'recover' }
  | { kind: 'open'; view: OverlayOpenView }
  | { kind: 'dismiss' };

const MAX_ID_LENGTH = 128;

/**
 * Maps an untrusted `overlay:action` IPC message to a main-process plan.
 *
 * @param raw - Message sent by the overlay renderer.
 * @returns `recover` for in-overlay recovery, `open` (with the requested view)
 *   when the student explicitly asks for the main window, otherwise `dismiss`.
 */
export function planOverlayAction(raw: unknown): OverlayActionPlan {
  if (typeof raw !== 'object' || raw === null) return { kind: 'dismiss' };
  const { action, view } = raw as Record<string, unknown>;
  if (action === 'recover') return { kind: 'recover' };
  if (action === 'open') {
    return { kind: 'open', view: view === 'recovery-summary' ? 'recovery-summary' : 'default' };
  }
  return { kind: 'dismiss' };
}

/** Message shown when the overlay asks for recovery but no drift event is pending. */
export const NO_PENDING_DRIFT_MESSAGE =
  'Bloom lost track of the moment you drifted. Open Bloom to pick a moment manually.';

/** Message shown when the backend rejects or fails the recovery request. */
export const RECOVERY_FAILED_MESSAGE =
  'Bloom could not build a recovery card right now. Try again in a moment.';

function isBoundedId(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= MAX_ID_LENGTH;
}

function isLectureMs(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

/**
 * Validates a drift request received over IPC from the renderer.
 *
 * The renderer is untrusted from the main process's perspective, so only a
 * plain object with bounded string ids and a well-formed `[start_ms, end_ms)`
 * lecture-time interval is accepted.
 *
 * @param raw - Payload from the `overlay:show-drift` IPC message.
 * @returns The typed request, or null when the payload is malformed.
 */
export function parseDriftRecoveryRequest(raw: unknown): DriftRecoveryRequest | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const candidate = raw as Record<string, unknown>;
  const { session_id, event_id, start_ms, end_ms } = candidate;
  if (!isBoundedId(session_id) || !isBoundedId(event_id)) return null;
  if (!isLectureMs(start_ms) || !isLectureMs(end_ms) || start_ms >= end_ms) return null;
  return { session_id, event_id, start_ms, end_ms };
}

/**
 * Requests a recovery card for a drift window and reads the completed card.
 *
 * @param client - Authenticated main-process backend client; the token never
 *   leaves this process.
 * @param request - Validated drift window to recover.
 * @returns The completed recovery card.
 * @throws Error When the job fails or completes without a card id.
 */
export async function requestDriftRecoveryCard(
  client: RecoveryCardClient,
  request: DriftRecoveryRequest,
): Promise<RecoveryCard> {
  const job = await client.requestRecoveryCard(
    request.session_id,
    {
      start_ms: request.start_ms,
      end_ms: request.end_ms,
      source_event_ids: [request.event_id],
    },
    randomUUID(),
  );
  if (job.status === 'failed') {
    throw new Error(job.failure?.message ?? 'Recovery card generation failed.');
  }
  if (!job.card_id) throw new Error('Recovery card is not available yet.');
  return client.readRecoveryCard(request.session_id, job.card_id);
}

/**
 * Coordinates in-overlay drift recovery so students never have to leave Zoom.
 *
 * The renderer records the latest drift event here; when the overlay asks to
 * recover, the controller publishes `loading`, then `ready` or `failed`, to
 * every subscriber (the overlay window and the hidden main window).
 */
export class DriftRecoveryController {
  private pending: DriftRecoveryRequest | null = null;
  private inFlight: Promise<DriftRecoveryState> | null = null;

  /**
   * @param client - Main-process backend client used to create and read cards.
   * @param publish - Fan-out callback invoked for every state transition.
   */
  constructor(
    private readonly client: RecoveryCardClient,
    private readonly publish: (state: DriftRecoveryState) => void,
  ) {}

  /**
   * Remembers the drift event the overlay will recover on request.
   *
   * @param request - Validated drift window, or null to clear it.
   */
  setPending(request: DriftRecoveryRequest | null): void {
    this.pending = request;
  }

  /** @returns The drift window awaiting a decision, if any. */
  readPending(): DriftRecoveryRequest | null {
    return this.pending;
  }

  /**
   * Recovers the pending drift window, publishing each state transition.
   *
   * Concurrent calls (double-clicks) share one backend request. A failed
   * attempt keeps the pending window so the overlay can offer Retry.
   *
   * @returns The terminal state for this attempt.
   */
  async recover(): Promise<DriftRecoveryState> {
    if (this.inFlight) return this.inFlight;
    const request = this.pending;
    if (!request) {
      const missing: DriftRecoveryState = {
        status: 'failed',
        request: { session_id: '', event_id: '', start_ms: 0, end_ms: 1 },
        message: NO_PENDING_DRIFT_MESSAGE,
      };
      this.publish(missing);
      return missing;
    }
    this.inFlight = this.run(request).finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }

  private async run(request: DriftRecoveryRequest): Promise<DriftRecoveryState> {
    this.publish({ status: 'loading', request });
    try {
      const card = await requestDriftRecoveryCard(this.client, request);
      this.pending = null;
      const ready: DriftRecoveryState = { status: 'ready', request, card };
      this.publish(ready);
      return ready;
    } catch (error) {
      const failed: DriftRecoveryState = {
        status: 'failed',
        request,
        message: error instanceof Error && error.message ? error.message : RECOVERY_FAILED_MESSAGE,
      };
      this.publish(failed);
      return failed;
    }
  }
}
