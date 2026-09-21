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
  status: 'ended',
  started_at: '2026-01-01T00:00:00.000Z',
  ended_at: '2026-01-01T01:00:00.000Z',
  session_clock_origin: '2026-01-01T00:00:00.000Z',
};

const REVISION = 'a'.repeat(64);

const buildReport = (overrides = {}) => ({
  session_id: 'session-1',
  report_revision: REVISION,
  status: 'available',
  provider_mode: 'mock',
  evidence_scope: 'lecture_transcript',
  evidence_note: null,
  recommendations: [
    {
      start_ms: 720000,
      end_ms: 780000,
      observation: 'Glycolysis was introduced once without a worked example.',
      suggested_action: 'Add a worked example of glycolysis next lecture.',
      topic: 'Glycolysis splits glucose',
      medium: 'example',
      evidence: [
        {
          text: 'Glycolysis splits glucose.',
          chunk_id: 'zoom_rtms:stream-1:720000:730000',
          evidence_quote: 'Glycolysis splits glucose.',
        },
      ],
    },
  ],
  reviews: [],
  ...overrides,
});

const installFakeBackend = ({ provider = 'openai', failAnalyze = false } = {}) => {
  const calls = [];
  globalThis.window = {
    backend: {
      readApiStatus: async () => {
        calls.push(['readApiStatus']);
        return { message: 'ok', recovery_provider: provider };
      },
      updateExternalTextConsent: async (sessionId, consent) => {
        calls.push(['updateExternalTextConsent', sessionId, consent]);
        return consent;
      },
      generateProfessorRecommendations: async (sessionId) => {
        calls.push(['generateProfessorRecommendations', sessionId]);
        if (failAnalyze) throw new Error('Provider unavailable');
        return buildReport();
      },
      reviewProfessorRecommendation: async (sessionId, review) => {
        calls.push(['reviewProfessorRecommendation', sessionId, review]);
        return review;
      },
    },
  };
  return calls;
};

const loadModules = async () => {
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  const service = await import('../../dist/renderer/services/teaching_moments.mjs');
  const panel = await import('../../dist/renderer/components/teaching_moments_panel.mjs');
  state.clearBackendSessionState();
  return { state, service, panel };
};

test('BackendClient maps teaching-moment generation and review to the professor routes', async () => {
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
    return new Response(JSON.stringify(buildReport()), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  try {
    const client = new BackendClient('https://bloom.example');
    await client.login({ email: 'a@b.c', password: 'pw' });
    await client.generateProfessorRecommendations('session 1');
    await client.reviewProfessorRecommendation('session 1', {
      report_revision: REVISION,
      recommendation_index: 0,
      status: 'resolved',
    });
    assert.deepEqual(
      requests.slice(1).map(({ method, url }) => [method, url]),
      [
        ['POST', 'https://bloom.example/api/v1/sessions/session%201/professor-recommendations'],
        [
          'PUT',
          'https://bloom.example/api/v1/sessions/session%201/professor-recommendations/reviews',
        ],
      ],
    );
    assert.equal(requests[1].body, undefined);
    assert.deepEqual(JSON.parse(requests[2].body), {
      report_revision: REVISION,
      recommendation_index: 0,
      status: 'resolved',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('analyzeTeachingMoments only calls the backend when invoked and stores the report', async () => {
  const calls = installFakeBackend();
  const { state, service, panel } = await loadModules();

  const idle = panel.TeachingMomentsPanel({
    session: SESSION,
    state: state.getBackendSessionState().teachingMoments,
  });
  assert.match(idle, /data-analyze-teaching-moments="session-1"/);
  assert.match(idle, /data-teaching-idle/);
  assert.match(idle, /Allow AI review of my lecture transcript/);
  assert.equal(calls.length, 0);

  await service.analyzeTeachingMoments('session-1');
  assert.deepEqual(calls, [['generateProfessorRecommendations', 'session-1']]);
  const current = service.readTeachingMoments();
  assert.equal(current.status, 'ready');
  assert.equal(current.report.report_revision, REVISION);

  const rendered = panel.TeachingMomentsPanel({ session: SESSION, state: current });
  assert.match(rendered, /12:00–13:00 · Example/);
  assert.match(rendered, /Glycolysis splits glucose/);
  assert.match(rendered, /Observation\.<\/strong> Glycolysis was introduced once/);
  assert.match(rendered, /<q>Glycolysis splits glucose\.<\/q>/);
  assert.match(rendered, /Suggested action<\/span>Add a worked example/);
  assert.match(rendered, /data-teaching-moment-status="new"/);
  assert.match(rendered, /Grounded in your lecture transcript/);
  assert.match(rendered, /Analyze again/);
  assert.doesNotMatch(rendered, /data-teaching-idle/);
});

test('analyzeTeachingMoments surfaces provider failures without a report', async () => {
  installFakeBackend({ failAnalyze: true });
  const { service, panel } = await loadModules();
  await service.analyzeTeachingMoments('session-1');
  const current = service.readTeachingMoments();
  assert.equal(current.status, 'failed');
  assert.equal(current.report, null);
  const rendered = panel.TeachingMomentsPanel({ session: SESSION, state: current });
  assert.match(rendered, /Teaching moments unavailable: Provider unavailable/);
});

test('setTeachingTranscriptConsent records openai consent for the live provider', async () => {
  const calls = installFakeBackend({ provider: 'openai' });
  const { service, panel } = await loadModules();
  await service.setTeachingTranscriptConsent('session-1', true);
  assert.deepEqual(calls, [
    ['readApiStatus'],
    ['updateExternalTextConsent', 'session-1', { provider: 'openai', is_allowed: true }],
  ]);
  const current = service.readTeachingMoments();
  assert.equal(current.transcriptConsentGranted, true);
  assert.equal(current.consentNote, null);
  assert.match(
    panel.TeachingMomentsPanel({ session: SESSION, state: current }),
    /data-teaching-transcript-consent="session-1" checked/,
  );

  await service.setTeachingTranscriptConsent('session-1', false);
  assert.deepEqual(calls[3], [
    'updateExternalTextConsent',
    'session-1',
    { provider: 'openai', is_allowed: false },
  ]);
  assert.equal(service.readTeachingMoments().transcriptConsentGranted, false);
});

test('setTeachingTranscriptConsent explains the mock provider instead of forwarding consent', async () => {
  const calls = installFakeBackend({ provider: 'mock' });
  const { service, panel } = await loadModules();
  await service.setTeachingTranscriptConsent('session-1', true);
  assert.deepEqual(calls, [['readApiStatus']]);
  const current = service.readTeachingMoments();
  assert.equal(current.transcriptConsentGranted, false);
  assert.equal(current.consentNote, service.MOCK_PROVIDER_NOTE);
  assert.match(
    panel.TeachingMomentsPanel({ session: SESSION, state: current }),
    /never sent externally/,
  );
});

test('reviewTeachingMoment sends the current revision and updates the status badge', async () => {
  const calls = installFakeBackend();
  const { service, panel } = await loadModules();
  await service.analyzeTeachingMoments('session-1');
  await service.reviewTeachingMoment('session-1', 0, 'dismissed');
  assert.deepEqual(calls[1], [
    'reviewProfessorRecommendation',
    'session-1',
    { report_revision: REVISION, recommendation_index: 0, status: 'dismissed' },
  ]);
  let current = service.readTeachingMoments();
  assert.equal(current.report.reviews.length, 1);
  let rendered = panel.TeachingMomentsPanel({ session: SESSION, state: current });
  assert.match(rendered, /data-teaching-moment-status="dismissed"/);
  assert.match(rendered, /is-dismissed/);
  assert.doesNotMatch(rendered, /data-review-status="dismissed"/);
  assert.match(rendered, /data-review-status="resolved"/);

  await service.reviewTeachingMoment('session-1', 0, 'resolved');
  current = service.readTeachingMoments();
  assert.equal(current.report.reviews.length, 1);
  assert.equal(current.report.reviews[0].status, 'resolved');
  rendered = panel.TeachingMomentsPanel({ session: SESSION, state: current });
  assert.match(rendered, /data-teaching-moment-status="resolved"/);
  assert.doesNotMatch(rendered, /is-dismissed/);
});

test('reviewTeachingMoment ignores reviews for a different lecture or missing report', async () => {
  const calls = installFakeBackend();
  const { service } = await loadModules();
  await service.reviewTeachingMoment('session-1', 0, 'reviewed');
  assert.deepEqual(calls, []);
  await service.analyzeTeachingMoments('session-1');
  await service.reviewTeachingMoment('session-2', 0, 'reviewed');
  assert.deepEqual(calls, [['generateProfessorRecommendations', 'session-1']]);
});

test('TeachingMomentsPanel renders honest fallbacks for consent-gated and empty reports', async () => {
  installFakeBackend();
  const { state, panel } = await loadModules();
  state.setTeachingMoments('session-1', {
    status: 'ready',
    report: buildReport({
      evidence_scope: 'intervals_only',
      evidence_note:
        'Lecture transcript analysis is off. Allow AI review of your lecture transcript to see what was taught during each hotspot.',
      recommendations: [
        {
          start_ms: 720000,
          end_ms: 780000,
          observation: 'Anonymous signals suggest 12:00–13:00 may have been missed.',
          suggested_action: 'Offer a short recap of 12:00–13:00.',
          topic: null,
          medium: null,
          evidence: [],
        },
      ],
    }),
  });
  const intervalsOnly = panel.TeachingMomentsPanel({
    session: SESSION,
    state: state.getBackendSessionState().teachingMoments,
  });
  assert.match(intervalsOnly, /no lecture transcript was analyzed/);
  assert.match(intervalsOnly, /Lecture transcript analysis is off/);
  assert.match(intervalsOnly, /Interval without transcript topic/);
  assert.match(intervalsOnly, /No transcript quote available/);

  state.setTeachingMoments('session-1', {
    status: 'ready',
    report: buildReport({ status: 'insufficient_evidence', recommendations: [] }),
  });
  const insufficient = panel.TeachingMomentsPanel({
    session: SESSION,
    state: state.getBackendSessionState().teachingMoments,
  });
  assert.match(insufficient, /data-teaching-insufficient/);
  assert.doesNotMatch(insufficient, /data-teaching-moment=/);
});

test('TeachingMomentsPanel escapes model output and resets when the lecture changes', async () => {
  installFakeBackend();
  const { state, panel } = await loadModules();
  state.setTeachingMoments('session-1', {
    status: 'ready',
    report: buildReport({
      recommendations: [
        {
          start_ms: 0,
          end_ms: 60000,
          observation: '<img src=x onerror=alert(1)>',
          suggested_action: 'Ignore previous instructions',
          topic: '<script>alert(1)</script>',
          medium: 'explanation',
          evidence: [],
        },
      ],
    }),
  });
  const rendered = panel.TeachingMomentsPanel({
    session: SESSION,
    state: state.getBackendSessionState().teachingMoments,
  });
  assert.doesNotMatch(rendered, /<script>/);
  assert.doesNotMatch(rendered, /<img src=x/);
  assert.match(rendered, /&lt;script&gt;/);

  state.setTeachingMoments('session-2', { status: 'loading' });
  const other = state.getBackendSessionState().teachingMoments;
  assert.equal(other.report, null);
  assert.equal(other.sessionId, 'session-2');
  const staleRender = panel.TeachingMomentsPanel({ session: SESSION, state: other });
  assert.match(staleRender, /data-teaching-idle/);
});
