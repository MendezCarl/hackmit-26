const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const { join } = require('node:path');
const test = require('node:test');
const routes = [
  'student-dashboard',
  'student-summary',
  'lecture-library',
  'educator-dashboard',
  'educator-summary',
  'account',
  'login',
];

test('every wireframe route renders a complete Bloom page', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  for (const route of routes) {
    const page = renderPage(route);
    assert.match(page, /class="app-frame"/);
    assert.match(page, /Bloom/);
    assert.ok(page.length > 500);
  }
});

test('pages use the repository Bloom asset instead of a drawn placeholder', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  assert.match(renderPage('student-dashboard'), /\.\/assets\/bloom-icon\.svg/);
  assert.match(renderPage('login'), /\.\/assets\/bloom-icon\.svg/);
});

test('educator pages use recovery language instead of attention claims', async () => {
  const { renderPage } = await import('../../dist/renderer/app/render_page.mjs');
  const educatorPages = [
    renderPage('educator-dashboard'),
    renderPage('educator-summary'),
  ].join(' ');

  assert.doesNotMatch(educatorPages, /attention ratio/i);
  assert.doesNotMatch(educatorPages, /students? lost focus/i);
  assert.match(educatorPages, /Anonymous aggregate/);
  assert.match(educatorPages, /Evidence coverage/);
});

test('student Zoom sessions show a detector-agnostic recovery cue', async () => {
  const { StudentDashboardPage } = await import(
    '../../dist/renderer/features/lecture-session/student_dashboard_page.mjs'
  );
  const page = StudentDashboardPage({
    isDemo: false,
    user: { user_id: 'user-1', display_name: 'Alex', email: 'alex@example.test', role: 'student' },
    activeSession: {
      session_id: 'session-1',
      lecture_id: 'lecture-1',
      owner_id: 'professor-1',
      course_id: 'course-1',
      title: 'Zoom lecture',
      join_code: 'K7PQ2M',
      mode: 'zoom',
      status: 'active',
      started_at: '2026-01-01T00:00:00.000Z',
      session_clock_origin: '2026-01-01T00:00:00.000Z',
      zoom_meeting_id: '987654321',
    },
    joinedSessions: [],
    participantCount: 1,
    submittedEvents: [
      {
        event_id: 'event-1',
        session_id: 'session-1',
        event_type: 'possible_missed_window',
        start_ms: 30000,
        end_ms: 60000,
        confidence: 0.82,
        signals: ['local_detector'],
      },
    ],
  });

  assert.match(page, /data-zoom-recovery-cue/);
  assert.match(page, /Possible missed moment/);
  assert.match(page, /Marked for review, not scored/);
  assert.doesNotMatch(page, /attention score/i);
});

test('the Electron renderer loads browser-native modules', async () => {
  const builtIndex = await readFile(
    join(__dirname, '..', '..', 'dist', 'index.html'),
    'utf8',
  );

  assert.match(
    builtIndex,
    /<script type="module" src="\.\/renderer\/index\.mjs"><\/script>/,
  );
  assert.doesNotMatch(builtIndex, /src="\.\/renderer\.js"/);
});
