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
  zoom_meeting_id: '123456789',
};

const buildChunk = (overrides = {}) => ({
  chunk_id: 'zoom_rtms:stream-1:1000:2000',
  session_id: 'session-1',
  start_ms: 1000,
  end_ms: 2000,
  text: 'Glycolysis splits glucose.',
  speaker_label: 'Professor',
  source: 'zoom_rtms',
  is_final: true,
  revision: 1,
  ...overrides,
});

const buildEnvelope = (payload, overrides = {}) => ({
  event_id: 'event-1',
  event_type: 'transcript.chunk.created',
  schema_version: '1.0.0',
  session_id: 'session-1',
  occurred_at: '2026-01-01T00:00:02.000Z',
  sequence_number: 1,
  payload,
  ...overrides,
});

const installFakeDesktop = () => {
  const subscriptions = [];
  globalThis.window = {
    backend: {},
    bloomDesktop: {
      subscribeSessionEvents: (sessionId) => subscriptions.push(sessionId),
      onSessionEvent: () => () => {},
      onSessionEventsConnection: () => () => {},
    },
  };
  return subscriptions;
};

test('BackendClient maps Zoom RTMS operations and keeps the token out of the renderer URL', async () => {
  const { BackendClient } = await import('../../dist/main/backend_client.js');
  const requests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), method: init.method, body: init.body });
    if (String(url).endsWith('/auth/login')) {
      return new Response(
        JSON.stringify({ user: { user_id: 'u1' }, access_token: 'secret-token' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response(JSON.stringify({ session_id: 'session 1', status: 'awaiting_stream' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  try {
    const client = new BackendClient('https://bloom.example');
    assert.equal(client.buildSessionEventsUrl('session 1'), null);
    await client.login({ email: 'a@b.c', password: 'pw' });
    await client.startZoomRtms('session 1', { zoom_meeting_id: '123456789' });
    await client.readZoomStatus('session 1');
    assert.deepEqual(
      requests.slice(1).map(({ method, url }) => [method, url]),
      [
        ['POST', 'https://bloom.example/api/v1/sessions/session%201/zoom/rtms/start'],
        ['GET', 'https://bloom.example/api/v1/sessions/session%201/zoom/status'],
      ],
    );
    assert.equal(requests[1].body, JSON.stringify({ zoom_meeting_id: '123456789' }));
    const url = new URL(client.buildSessionEventsUrl('session 1'));
    assert.equal(url.protocol, 'wss:');
    assert.equal(url.pathname, '/ws/v1/sessions/session%201');
    assert.equal(url.searchParams.get('token'), 'secret-token');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('parseSessionEventEnvelope rejects frames missing envelope fields', async () => {
  const { parseSessionEventEnvelope } = await import('../../dist/main/session_events.js');
  const envelope = buildEnvelope(buildChunk());
  assert.deepEqual(parseSessionEventEnvelope(envelope), envelope);
  assert.equal(parseSessionEventEnvelope(null), null);
  assert.equal(parseSessionEventEnvelope('transcript'), null);
  assert.equal(parseSessionEventEnvelope({ ...envelope, sequence_number: '1' }), null);
  assert.equal(parseSessionEventEnvelope({ ...envelope, payload: null }), null);
});

test('applySessionEvent merges live Zoom chunks, honours revisions, and ignores other sessions', async () => {
  installFakeDesktop();
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  const live = await import('../../dist/renderer/services/live_session_events.mjs');
  state.clearBackendSessionState();
  state.setActiveSession(SESSION);
  state.setTranscriptChunks([buildChunk({ chunk_id: 'local-1', start_ms: 5000, end_ms: 6000, source: 'local_transcription' })]);

  assert.equal(live.applySessionEvent(buildEnvelope(buildChunk())), true);
  assert.deepEqual(
    state.getBackendSessionState().transcriptChunks.map((chunk) => chunk.chunk_id),
    ['zoom_rtms:stream-1:1000:2000', 'local-1'],
  );

  // Replay of the same chunk is a no-op for the transcript order and count.
  live.applySessionEvent(buildEnvelope(buildChunk()));
  assert.equal(state.getBackendSessionState().transcriptChunks.length, 2);

  // A higher revision replaces the text; a lower one is ignored.
  assert.equal(
    live.applySessionEvent(buildEnvelope(buildChunk({ revision: 2, text: 'Glycolysis splits glucose in two.' }))),
    true,
  );
  assert.equal(
    live.applySessionEvent(buildEnvelope(buildChunk({ revision: 1, text: 'stale' }))),
    false,
  );
  assert.equal(
    state.getBackendSessionState().transcriptChunks[0].text,
    'Glycolysis splits glucose in two.',
  );

  // Events for another session or with a non-transcript type never touch state.
  assert.equal(
    live.applySessionEvent(buildEnvelope(buildChunk({ session_id: 'session-2' }), { session_id: 'session-2' })),
    false,
  );
  assert.equal(
    live.applySessionEvent(buildEnvelope({ user_id: 'u1' }, { event_type: 'session.connected' })),
    false,
  );
  assert.equal(live.applySessionEvent(buildEnvelope({ chunk_id: 'x' })), false);
  assert.equal(state.getBackendSessionState().transcriptChunks.length, 2);
});

test('syncLiveSessionSubscription follows the active session and closes on end', async () => {
  const subscriptions = installFakeDesktop();
  const live = await import('../../dist/renderer/services/live_session_events.mjs');
  live.syncLiveSessionSubscription(null);
  live.syncLiveSessionSubscription(SESSION);
  live.syncLiveSessionSubscription(SESSION);
  live.syncLiveSessionSubscription({ ...SESSION, status: 'ended' });
  assert.deepEqual(subscriptions, ['session-1', null]);
});

test('lecture page shows the Zoom link panel only for an active session', async () => {
  const { LectureSummaryPage } = await import(
    '../../dist/renderer/features/lecture-summary/lecture_summary_page.mjs'
  );
  const baseModel = {
    isDemo: false,
    lecture: { lecture_id: 'lecture-1', course_id: 'course-1', title: 'Cellular respiration', created_at: '2026-01-01T00:00:00.000Z' },
    course: { course_id: 'course-1', code: 'BIO101', title: 'Biology', created_at: '2026-01-01T00:00:00.000Z' },
    allCourses: [],
    allLecturesByCourse: {},
    summary: null,
    metrics: null,
  };
  const activePage = LectureSummaryPage({
    ...baseModel,
    session: SESSION,
    zoomStatus: { session_id: 'session-1', status: 'streaming', zoom_meeting_id: '123456789', transcript_chunk_count: 4 },
  });
  assert.match(activePage, /data-zoom-rtms-form/);
  assert.match(activePage, /data-zoom-rtms-status="streaming"/);
  assert.match(activePage, /4 transcript chunk\(s\) received/);
  assert.match(activePage, /value="123456789"/);

  const unconfiguredPage = LectureSummaryPage({
    ...baseModel,
    session: SESSION,
    zoomStatus: { session_id: 'session-1', status: 'not_configured' },
  });
  assert.doesNotMatch(unconfiguredPage, /data-zoom-rtms-form/);
  assert.match(unconfiguredPage, /not configured/);

  const endedPage = LectureSummaryPage({
    ...baseModel,
    session: { ...SESSION, status: 'ended', ended_at: '2026-01-01T01:00:00.000Z' },
  });
  assert.doesNotMatch(endedPage, /data-zoom-live-transcript/);
});

test('student transcript panel escapes live Zoom text and reports the stream state', async () => {
  const { StudentTranscriptPanel } = await import(
    '../../dist/renderer/features/recovery-cards/student_summary_page.mjs'
  );
  const panel = StudentTranscriptPanel({
    isDemo: false,
    session: SESSION,
    courses: [],
    joinedSessions: [],
    submittedEvents: [],
    recoveryCards: [],
    transcript: [buildChunk({ text: '<b>alert</b>' })],
    liveEventsConnection: { session_id: 'session-1', state: 'connected' },
  });
  assert.match(panel, /Live · Zoom transcript streaming/);
  assert.match(panel, /&lt;b&gt;alert&lt;\/b&gt;/);
  assert.doesNotMatch(panel, /<b>alert<\/b>/);
});
