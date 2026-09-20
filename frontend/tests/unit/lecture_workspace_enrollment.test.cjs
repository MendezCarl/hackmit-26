const assert = require('node:assert/strict');
const test = require('node:test');

const SESSION = {
  session_id: 'session-1',
  lecture_id: 'lecture-1',
  owner_id: 'professor-1',
  course_id: 'course-1',
  title: 'Cellular respiration',
  join_code: 'K7PQ2M',
  mode: 'in_person',
  status: 'active',
  started_at: '2026-01-01T00:00:00.000Z',
  session_clock_origin: '2026-01-01T00:00:00.000Z',
};

const installFakeBackend = (available) => {
  const calls = [];
  globalThis.window = {
    backend: {
      listAvailableSessions: async (zoomMeetingId) => {
        calls.push(['listAvailableSessions', zoomMeetingId]);
        return available;
      },
      joinSession: async (sessionId) => {
        calls.push(['joinSession', sessionId]);
        return { session_id: sessionId, user_id: 'user-1', participant_count: 3 };
      },
      listEnrollments: async () => {
        calls.push(['listEnrollments']);
        return [];
      },
    },
  };
  return calls;
};

test('refreshAvailableSessions only prompts when auto-join is off', async () => {
  const calls = installFakeBackend([
    { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
  ]);
  const workspace = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  state.clearBackendSessionState();
  const available = await workspace.refreshAvailableSessions();
  assert.equal(available.length, 1);
  assert.equal(state.getBackendSessionState().activeSession, null);
  assert.deepEqual(calls, [['listAvailableSessions', null]]);
});

test('refreshAvailableSessions joins zero-click when the enrollment opted in', async () => {
  const calls = installFakeBackend([
    { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: true },
  ]);
  const workspace = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  state.clearBackendSessionState();
  const available = await workspace.refreshAvailableSessions('987654321');
  assert.equal(state.getBackendSessionState().activeSession?.session_id, 'session-1');
  assert.equal(state.getBackendSessionState().participantCount, 3);
  assert.equal(available[0].is_joined, true);
  assert.deepEqual(calls, [
    ['listAvailableSessions', '987654321'],
    ['joinSession', 'session-1'],
  ]);
});

test('refreshAvailableSessions never auto-joins over an active session', async () => {
  const calls = installFakeBackend([
    {
      session: { ...SESSION, session_id: 'session-2' },
      matched_by: 'enrollment',
      is_joined: false,
      is_auto_join_enabled: true,
    },
  ]);
  const workspace = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  state.clearBackendSessionState();
  state.setActiveSession(SESSION);
  await workspace.refreshAvailableSessions();
  assert.equal(state.getBackendSessionState().activeSession?.session_id, 'session-1');
  assert.deepEqual(calls, [['listAvailableSessions', null]]);
});

test('dismissed prompts are forgotten once the session stops being live', async () => {
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  state.clearBackendSessionState();
  state.setAvailableSessions([
    { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
  ]);
  state.dismissAvailableSession('session-1');
  assert.deepEqual(state.getBackendSessionState().dismissedAvailableSessionIds, ['session-1']);
  state.setAvailableSessions([]);
  assert.deepEqual(state.getBackendSessionState().dismissedAvailableSessionIds, []);
});
