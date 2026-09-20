const assert = require('node:assert/strict');
const test = require('node:test');

const SESSION = {
  session_id: 'session-1',
  lecture_id: 'lecture-1',
  owner_id: 'professor-1',
  course_id: 'course-1',
  title: 'Cellular respiration',
  join_code: 'K7PQ2M',
  mode: 'zoom',
  status: 'active',
  started_at: '2026-01-01T00:00:00.000Z',
  session_clock_origin: '2026-01-01T00:00:00.000Z',
};

const DRIFT_REQUEST = {
  session_id: 'session-1',
  event_id: 'event-1',
  start_ms: 60_000,
  end_ms: 90_000,
};

const CARD = {
  card_id: 'card-1',
  session_id: 'session-1',
  source_event_ids: ['event-1'],
  topic: 'Glycolysis <b>overview</b>',
  what_you_missed: 'The professor explained how glucose is split.',
  key_facts: ['Two ATP invested', 'Four ATP produced'],
  example_from_lecture: null,
  source_timestamps: [{ start_ms: 60_000, end_ms: 90_000 }],
  follow_up_question: 'Where does the net ATP gain come from?',
  model_metadata: {
    provider: 'mock',
    model: 'deterministic',
    provider_mode: 'mock',
    data_label: 'synthetic',
    prompt_version: '1',
    output_schema_version: '1',
    input_character_count: 10,
    output_character_count: 10,
    latency_ms: 1,
  },
  created_at: '2026-01-01T00:01:30.000Z',
};

const buildFakeClient = ({ jobStatus = 'completed', cardId = 'card-1', failRead = false } = {}) => {
  const calls = [];
  return {
    calls,
    requestRecoveryCard: async (sessionId, request, idempotencyKey) => {
      calls.push(['requestRecoveryCard', sessionId, request, typeof idempotencyKey]);
      return {
        job_id: 'job-1',
        session_id: sessionId,
        status: jobStatus,
        requested_start_ms: request.start_ms,
        requested_end_ms: request.end_ms,
        card_id: jobStatus === 'completed' ? cardId : null,
        failure: jobStatus === 'failed' ? { reason: 'no_transcript', message: 'No transcript for that window.' } : null,
        created_at: '2026-01-01T00:01:00.000Z',
      };
    },
    readRecoveryCard: async (sessionId, readCardId) => {
      calls.push(['readRecoveryCard', sessionId, readCardId]);
      if (failRead) throw new Error('backend offline');
      return { ...CARD, card_id: readCardId };
    },
  };
};

test('parseDriftRecoveryRequest accepts a well-formed drift window and rejects malformed IPC input', async () => {
  const { parseDriftRecoveryRequest } = await import('../../dist/main/drift_recovery.js');
  assert.deepEqual(parseDriftRecoveryRequest({ ...DRIFT_REQUEST, extra: 'ignored' }), DRIFT_REQUEST);
  for (const raw of [
    null,
    undefined,
    'session-1',
    { ...DRIFT_REQUEST, session_id: '' },
    { ...DRIFT_REQUEST, event_id: 'x'.repeat(129) },
    { ...DRIFT_REQUEST, start_ms: -1 },
    { ...DRIFT_REQUEST, start_ms: 90_000 },
    { ...DRIFT_REQUEST, end_ms: 1.5 },
    { ...DRIFT_REQUEST, end_ms: '90000' },
  ]) {
    assert.equal(parseDriftRecoveryRequest(raw), null, String(JSON.stringify(raw)).slice(0, 60));
  }
});

test('planOverlayAction only opens the main window for an explicit open action', async () => {
  const { planOverlayAction } = await import('../../dist/main/drift_recovery.js');
  assert.deepEqual(planOverlayAction({ action: 'recover' }), { kind: 'recover' });
  assert.deepEqual(planOverlayAction({ action: 'open', view: 'recovery-summary' }), {
    kind: 'open',
    view: 'recovery-summary',
  });
  assert.deepEqual(planOverlayAction({ action: 'open', view: 'settings' }), { kind: 'open', view: 'default' });
  assert.deepEqual(planOverlayAction({ action: 'dismiss' }), { kind: 'dismiss' });
  assert.deepEqual(planOverlayAction(null), { kind: 'dismiss' });
  assert.deepEqual(planOverlayAction('open'), { kind: 'dismiss' });
});

test('DriftRecoveryController publishes loading then ready and calls the backend from the main process', async () => {
  const { DriftRecoveryController } = await import('../../dist/main/drift_recovery.js');
  const client = buildFakeClient();
  const published = [];
  const controller = new DriftRecoveryController(client, (state) => published.push(state));
  controller.setPending(DRIFT_REQUEST);

  const [first, second] = await Promise.all([controller.recover(), controller.recover()]);
  assert.equal(first, second, 'concurrent recover calls share one request');
  assert.deepEqual(
    client.calls,
    [
      [
        'requestRecoveryCard',
        'session-1',
        { start_ms: 60_000, end_ms: 90_000, source_event_ids: ['event-1'] },
        'string',
      ],
      ['readRecoveryCard', 'session-1', 'card-1'],
    ],
    'exactly one job request and one card read',
  );
  assert.deepEqual(
    published.map((state) => state.status),
    ['loading', 'ready'],
  );
  assert.equal(published[1].card.card_id, 'card-1');
  assert.deepEqual(published[1].request, DRIFT_REQUEST);
  assert.equal(controller.readPending(), null, 'a delivered card clears the pending window');
});

test('DriftRecoveryController publishes failed states and keeps the window pending for retry', async () => {
  const { DriftRecoveryController, NO_PENDING_DRIFT_MESSAGE } = await import(
    '../../dist/main/drift_recovery.js'
  );

  const failedJob = buildFakeClient({ jobStatus: 'failed' });
  const jobStates = [];
  const jobController = new DriftRecoveryController(failedJob, (state) => jobStates.push(state));
  jobController.setPending(DRIFT_REQUEST);
  const failed = await jobController.recover();
  assert.equal(failed.status, 'failed');
  assert.equal(failed.message, 'No transcript for that window.');
  assert.deepEqual(jobStates.map((state) => state.status), ['loading', 'failed']);
  assert.deepEqual(jobController.readPending(), DRIFT_REQUEST, 'retry can reuse the window');
  assert.equal(failedJob.calls.filter(([name]) => name === 'readRecoveryCard').length, 0);

  const failedRead = buildFakeClient({ failRead: true });
  const readController = new DriftRecoveryController(failedRead, () => {});
  readController.setPending(DRIFT_REQUEST);
  const readFailure = await readController.recover();
  assert.equal(readFailure.status, 'failed');
  assert.equal(readFailure.message, 'backend offline');

  const retry = await new DriftRecoveryController(buildFakeClient(), () => {}).recover();
  assert.equal(retry.status, 'failed');
  assert.equal(retry.message, NO_PENDING_DRIFT_MESSAGE);
});

test('renderDriftOverlay renders prompt, loading, card, and retry states with escaped text', async () => {
  const { renderDriftOverlay, DRIFT_PROMPT_COPY } = await import(
    '../../dist/renderer/components/drift_overlay_card.mjs'
  );

  const prompt = renderDriftOverlay({ status: 'prompt' });
  assert.match(prompt, /data-overlay-state="prompt"/);
  assert.match(prompt, /data-overlay-recover/);
  assert.match(prompt, new RegExp(DRIFT_PROMPT_COPY.action));
  assert.doesNotMatch(prompt, /data-overlay-open/, 'the prompt never offers to leave Zoom');

  const loading = renderDriftOverlay({ status: 'loading', request: DRIFT_REQUEST });
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /data-overlay-dismiss/);
  assert.doesNotMatch(loading, /data-overlay-recover/);

  const ready = renderDriftOverlay({ status: 'ready', request: DRIFT_REQUEST, card: CARD });
  assert.match(ready, /data-overlay-state="ready"/);
  assert.match(ready, /data-overlay-recovery-card="card-1"/);
  assert.match(ready, /Glycolysis &lt;b&gt;overview&lt;\/b&gt;/);
  assert.doesNotMatch(ready, /<b>overview<\/b>/);
  assert.match(ready, /Two ATP invested/);
  assert.match(ready, /Sources: 01:00–01:30/);
  assert.match(ready, /data-overlay-open="recovery-summary"/, 'Open in Bloom is an explicit secondary action');
  assert.match(ready, /data-overlay-dismiss/);

  const failed = renderDriftOverlay({
    status: 'failed',
    request: DRIFT_REQUEST,
    message: 'Try <again>',
  });
  assert.match(failed, /data-overlay-state="failed"/);
  assert.match(failed, /role="alert" data-overlay-error>Try &lt;again&gt;</);
  assert.match(failed, /data-overlay-recover>Retry</);
});

test('parseDriftRecoveryState only accepts known recovery states', async () => {
  const { parseDriftRecoveryState } = await import(
    '../../dist/renderer/components/drift_overlay_card.mjs'
  );
  assert.equal(parseDriftRecoveryState({ status: 'loading', request: DRIFT_REQUEST }).status, 'loading');
  assert.equal(parseDriftRecoveryState({ status: 'ready', request: DRIFT_REQUEST, card: CARD }).status, 'ready');
  assert.equal(parseDriftRecoveryState({ status: 'failed', request: DRIFT_REQUEST, message: 'x' }).status, 'failed');
  assert.equal(parseDriftRecoveryState({ status: 'ready', request: DRIFT_REQUEST }), null);
  assert.equal(parseDriftRecoveryState({ status: 'failed', request: DRIFT_REQUEST }), null);
  assert.equal(parseDriftRecoveryState({ status: 'prompt' }), null);
  assert.equal(parseDriftRecoveryState(null), null);
});

test('applyOverlayRecoveryCard syncs the hidden main window with the overlay result', async () => {
  globalThis.window = { backend: {}, bloomDesktop: { setRole() {} } };
  const workspace = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  state.clearBackendSessionState();
  state.setActiveSession(SESSION);
  state.setPendingDriftPrompt({
    event_id: 'event-1',
    session_id: 'session-1',
    event_type: 'possible_missed_window',
    start_ms: 60_000,
    end_ms: 90_000,
    confidence: 0.8,
  });

  const payload = { session_id: 'session-1', event_id: 'event-1', card: CARD };
  assert.equal(workspace.applyOverlayRecoveryCard(payload), true);
  assert.deepEqual(state.getBackendSessionState().recoveryCards.map((card) => card.card_id), ['card-1']);
  assert.equal(state.getBackendSessionState().pendingDriftPrompt, null);

  assert.equal(workspace.applyOverlayRecoveryCard(payload), false, 'replays are ignored');
  assert.equal(state.getBackendSessionState().recoveryCards.length, 1);

  assert.equal(
    workspace.applyOverlayRecoveryCard({ ...payload, session_id: 'session-2', card: { ...CARD, card_id: 'card-2' } }),
    false,
    'cards for other sessions never touch state',
  );
  assert.equal(state.getBackendSessionState().recoveryCards.length, 1);
});
