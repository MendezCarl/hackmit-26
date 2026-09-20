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
  zoom_join_url: 'https://us02web.zoom.us/j/123456789?pwd=abc.DEF-1',
};

test('resolveZoomJoinTarget builds desktop deep link and https fallback for meeting links', async () => {
  const { resolveZoomJoinTarget } = await import('../../dist/main/zoom_join_link.js');
  assert.deepEqual(resolveZoomJoinTarget(SESSION.zoom_join_url), {
    webUrl: 'https://us02web.zoom.us/j/123456789?pwd=abc.DEF-1',
    deepLink: 'zoommtg://zoom.us/join?action=join&confno=123456789&pwd=abc.DEF-1',
  });
  assert.deepEqual(resolveZoomJoinTarget('https://zoomgov.com/j/12345678901'), {
    webUrl: 'https://zoomgov.com/j/12345678901',
    deepLink: 'zoommtg://zoomgov.com/join?action=join&confno=12345678901',
  });
});

test('resolveZoomJoinTarget keeps personal-room links browser-only', async () => {
  const { resolveZoomJoinTarget } = await import('../../dist/main/zoom_join_link.js');
  assert.deepEqual(resolveZoomJoinTarget('https://zoom.us/my/prof.bloom'), {
    webUrl: 'https://zoom.us/my/prof.bloom',
    deepLink: null,
  });
});

test('resolveZoomJoinTarget drops tracking parameters and fragments', async () => {
  const { resolveZoomJoinTarget } = await import('../../dist/main/zoom_join_link.js');
  const target = resolveZoomJoinTarget('https://zoom.us/j/123456789?uname=Alex&pwd=secret#success');
  assert.equal(target.webUrl, 'https://zoom.us/j/123456789?pwd=secret');
});

for (const raw of [
  'http://zoom.us/j/123456789',
  'javascript:alert(1)',
  'file:///etc/passwd',
  'zoommtg://zoom.us/join?confno=123456789',
  'https://evil.example/j/123456789',
  'https://zoom.us.evil.example/j/123456789',
  'https://notzoom.us/j/123456789',
  'https://user:pass@zoom.us/j/123456789',
  'https://zoom.us:8443/j/123456789',
  'https://zoom.us/j/12345',
  'https://zoom.us/j/123456789/../../login',
  'https://zoom.us/rec/share/abc',
  'https://zoom.us/j/123456789?pwd=<script>',
  'https://zoom.us/j/123456789?pwd=a&pwd=b',
  'https://zoom.us/j/1234 56789',
  'https://zoom.us/j/123456789\n',
  `https://zoom.us/${'j/'.repeat(1100)}123456789`,
  '',
  null,
  undefined,
  42,
  { url: 'https://zoom.us/j/123456789' },
]) {
  test(`resolveZoomJoinTarget rejects ${String(JSON.stringify(raw)).slice(0, 60)}`, async () => {
    const { resolveZoomJoinTarget } = await import('../../dist/main/zoom_join_link.js');
    assert.equal(resolveZoomJoinTarget(raw), null);
  });
}

test('openZoomJoinLink prefers the Zoom desktop client', async () => {
  const { openZoomJoinLink } = await import('../../dist/main/zoom_join_link.js');
  const opened = [];
  const outcome = await openZoomJoinLink(SESSION.zoom_join_url, async (url) => {
    opened.push(url);
  });
  assert.equal(outcome, 'desktop');
  assert.deepEqual(opened, ['zoommtg://zoom.us/join?action=join&confno=123456789&pwd=abc.DEF-1']);
});

test('openZoomJoinLink falls back to https when no desktop handler exists', async () => {
  const { openZoomJoinLink } = await import('../../dist/main/zoom_join_link.js');
  const opened = [];
  const outcome = await openZoomJoinLink(SESSION.zoom_join_url, async (url) => {
    opened.push(url);
    if (url.startsWith('zoommtg://')) throw new Error('No application registered for zoommtg');
  });
  assert.equal(outcome, 'browser');
  assert.deepEqual(opened, [
    'zoommtg://zoom.us/join?action=join&confno=123456789&pwd=abc.DEF-1',
    'https://us02web.zoom.us/j/123456789?pwd=abc.DEF-1',
  ]);
});

test('openZoomJoinLink never opens anything for a rejected URL', async () => {
  const { openZoomJoinLink } = await import('../../dist/main/zoom_join_link.js');
  const opened = [];
  const outcome = await openZoomJoinLink('javascript:alert(1)', async (url) => {
    opened.push(url);
  });
  assert.equal(outcome, 'rejected');
  assert.deepEqual(opened, []);
});

test('ZoomJoinButton renders only for active sessions with a join link', async () => {
  const { ZoomJoinButton, hasZoomJoinLink } = await import(
    '../../dist/renderer/components/zoom_join_button.mjs'
  );
  const markup = ZoomJoinButton({ session: SESSION });
  assert.match(markup, /data-zoom-join="session-1"/);
  assert.match(markup, /Join Zoom meeting/);
  assert.doesNotMatch(markup, /zoom\.us/, 'the URL must not be embedded in the DOM');
  assert.equal(ZoomJoinButton({ session: { ...SESSION, zoom_join_url: null } }), '');
  assert.equal(ZoomJoinButton({ session: { ...SESSION, zoom_join_url: undefined } }), '');
  assert.equal(ZoomJoinButton({ session: { ...SESSION, status: 'ended' } }), '');
  assert.equal(hasZoomJoinLink(null), false);
});

test('buildZoomMeetingLinkRequest routes links and ids to the right RTMS field', async () => {
  const { buildZoomMeetingLinkRequest } = await import(
    '../../dist/renderer/components/zoom_live_transcript_panel.mjs'
  );
  assert.deepEqual(buildZoomMeetingLinkRequest('  https://zoom.us/j/123456789?pwd=x '), {
    zoom_join_url: 'https://zoom.us/j/123456789?pwd=x',
  });
  assert.deepEqual(buildZoomMeetingLinkRequest(' 123456789 '), { zoom_meeting_id: '123456789' });
});

test('ZoomLiveTranscriptPanel shows the join button and prefers the stored link in the field', async () => {
  const { ZoomLiveTranscriptPanel } = await import(
    '../../dist/renderer/components/zoom_live_transcript_panel.mjs'
  );
  const markup = ZoomLiveTranscriptPanel({
    session: SESSION,
    status: { session_id: 'session-1', status: 'awaiting_stream', zoom_meeting_id: '123456789' },
  });
  assert.match(markup, /data-zoom-join="session-1"/);
  assert.match(markup, /name="zoom_meeting_reference"[^>]*value="https:\/\/us02web\.zoom\.us\/j\/123456789\?pwd=abc\.DEF-1"/);
  const unlinked = ZoomLiveTranscriptPanel({
    session: { ...SESSION, zoom_join_url: null },
    status: { session_id: 'session-1', status: 'not_linked' },
  });
  assert.doesNotMatch(unlinked, /data-zoom-join/);
});

test('student dashboard and summary render join buttons only when the session has a link', async () => {
  const { StudentDashboardPage } = await import(
    '../../dist/renderer/features/lecture-session/student_dashboard_page.mjs'
  );
  const { StudentSummaryPage } = await import(
    '../../dist/renderer/features/recovery-cards/student_summary_page.mjs'
  );
  const baseDashboard = {
    isDemo: false,
    user: { user_id: 'student-1', display_name: 'Alex', role: 'student', email: 'a@example.edu' },
    courses: [],
    activeSession: null,
    joinedSessions: [],
    enrollments: [],
    availableSessions: [
      { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
    ],
    dismissedAvailableSessionIds: [],
    participantCount: 3,
    submittedEvents: [],
    zoomRunning: false,
    zoomBannerDismissed: false,
    externalTextConsentGranted: false,
    externalTextConsentNote: null,
    cameraSignalsEnabled: false,
    cameraSignalsStatus: 'off',
    cameraSignalsError: null,
    pendingDriftPrompt: null,
  };
  const prompt = StudentDashboardPage(baseDashboard);
  assert.equal(prompt.match(/data-zoom-join="session-1"/g).length, 1);

  const active = StudentDashboardPage({ ...baseDashboard, availableSessions: [], activeSession: SESSION });
  assert.equal(active.match(/data-zoom-join="session-1"/g).length, 1);

  const withoutLink = StudentDashboardPage({
    ...baseDashboard,
    availableSessions: [],
    activeSession: { ...SESSION, zoom_join_url: null },
  });
  assert.doesNotMatch(withoutLink, /data-zoom-join/);

  const summaryModel = {
    isDemo: false,
    session: SESSION,
    courses: [],
    joinedSessions: [SESSION],
    submittedEvents: [],
    recoveryCards: [],
    transcript: [],
  };
  assert.match(StudentSummaryPage(summaryModel), /data-zoom-join="session-1"/);
  assert.doesNotMatch(
    StudentSummaryPage({ ...summaryModel, session: { ...SESSION, status: 'ended' } }),
    /data-zoom-join/,
  );
});

test('openZoomMeeting hands the stored URL to the main process and rejects unknown sessions', async () => {
  const state = await import('../../dist/renderer/services/backend_session_state.mjs');
  const workspace = await import('../../dist/renderer/services/lecture_workspace.mjs');
  const opened = [];
  globalThis.window = {
    bloomDesktop: {
      openZoomJoinLink: async (url) => {
        opened.push(url);
        return 'desktop';
      },
    },
  };
  try {
    state.setAvailableSessions([
      { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
    ]);
    assert.equal(await workspace.openZoomMeeting('session-1'), 'desktop');
    assert.deepEqual(opened, [SESSION.zoom_join_url]);
    assert.equal(await workspace.openZoomMeeting('session-unknown'), 'rejected');
    assert.equal(opened.length, 1);
  } finally {
    delete globalThis.window;
  }
});
