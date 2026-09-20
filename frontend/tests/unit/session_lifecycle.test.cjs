const assert = require('node:assert/strict');
const test = require('node:test');

const active = {
  session_id: 'older-session', lecture_id: 'lecture-1', course_id: 'course-1',
  title: 'Synthetic lecture', status: 'active', join_code: 'ABC123',
  started_at: '2026-01-01T00:00:00Z', session_clock_origin: '2026-01-01T00:00:00Z',
};
const ended = { ...active, status: 'ended', ended_at: '2026-01-01T01:00:00Z' };

test('end responses and refreshed lists reconcile cached sessions', async () => {
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  for (const update of [state.updateCachedSession, (session) => state.setBackendSessions([session])]) {
    state.clearBackendSessionState();
    state.setBackendSessions([active]);
    state.addJoinedSession(active);
    state.setSelectedSession(active);
    update(ended);
    const current = state.getBackendSessionState();
    assert.equal(current.activeSession, null);
    assert.equal(current.selectedSession.status, 'ended');
    assert.equal(current.sessions[0].status, 'ended');
    assert.equal(current.sessionsByLecture['lecture-1'][0].status, 'ended');
    assert.equal(current.joinedSessions[0].status, 'ended');
  }
  state.clearBackendSessionState();
  state.setActiveSession(active);
  state.setBackendSessions([{ ...ended, session_id: 'unrelated-session' }]);
  assert.equal(state.getBackendSessionState().activeSession, active);
  state.clearBackendSessionState();
});

test('history opens the exact older session and its end control', async () => {
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  const { loadLectureWorkspace } = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const { HomePage } = await import('../../dist/renderer/features/home/home_page.mjs');
  const { LectureSummaryPage } = await import('../../dist/renderer/features/lecture-summary/lecture_summary_page.mjs');
  const course = { course_id: 'course-1', title: 'Biology', code: 'BIO', created_at: active.started_at };
  const lecture = { lecture_id: 'lecture-1', course_id: 'course-1', title: active.title };
  const newer = { ...ended, session_id: 'newer-session' };
  const previousWindow = global.window;
  global.window = { backend: {
    listSessions: async () => [newer, active],
    readProfessorSummary: async () => null,
    readProfessorMetrics: async () => null,
  } };
  try {
    state.clearBackendSessionState();
    state.setBackendCourses([course]);
    state.setBackendLectures(course.course_id, [lecture]);
    const home = HomePage({ ...state.getBackendSessionState(), isDemo: false, sessions: [active] });
    assert.match(home, /session_id=older-session/);
    await loadLectureWorkspace('lecture-1', 'older-session');
    assert.equal(state.getBackendSessionState().selectedSession.session_id, 'older-session');
    const model = { isDemo: false, course, lecture, allCourses: [course], allLecturesByCourse: {}, summary: null, metrics: null };
    assert.match(LectureSummaryPage({ ...model, session: state.getBackendSessionState().selectedSession }), /data-end-session="older-session"/);
    await loadLectureWorkspace('lecture-1');
    assert.equal(state.getBackendSessionState().selectedSession.session_id, 'newer-session');
    assert.doesNotMatch(LectureSummaryPage({ ...model, session: newer }), /data-end-session/);
    await assert.rejects(loadLectureWorkspace('lecture-1', 'missing'), /could not be found/);
    assert.equal(state.getBackendSessionState().selectedSession, null);
  } finally {
    global.window = previousWindow;
    state.clearBackendSessionState();
  }
});

test('dashboard end controls require an active session and carry its ID', async () => {
  const { EducatorDashboardPage } = await import('../../dist/renderer/features/professor-summary/educator_dashboard_page.mjs');
  const model = { isDemo: false, courses: [], lecturesByCourse: {} };
  assert.match(EducatorDashboardPage({ ...model, activeSession: active }), /data-end-session="older-session"/);
  for (const status of ['ended', 'ending', 'failed', 'created']) {
    assert.doesNotMatch(EducatorDashboardPage({ ...model, activeSession: { ...active, status } }), /Active session|data-end-session/);
  }
});
