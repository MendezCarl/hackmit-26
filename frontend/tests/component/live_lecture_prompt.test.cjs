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
  zoom_meeting_id: '987654321',
};

const ENROLLMENT = {
  enrollment_id: 'enrollment-1',
  course_id: 'course-1',
  user_id: 'user-1',
  course_title: 'Biology',
  course_code: 'BIO101',
  is_auto_join_enabled: false,
  enrolled_at: '2026-01-01T00:00:00.000Z',
};

const baseModel = (overrides = {}) => ({
  isDemo: false,
  user: { user_id: 'user-1', display_name: 'Alex', email: 'alex@example.test', role: 'student' },
  courses: [],
  activeSession: null,
  joinedSessions: [],
  enrollments: [],
  availableSessions: [],
  dismissedAvailableSessionIds: [],
  participantCount: null,
  submittedEvents: [],
  zoomRunning: false,
  zoomBannerDismissed: false,
  externalTextConsentGranted: false,
  externalTextConsentNote: null,
  cameraSignalsEnabled: false,
  cameraSignalsStatus: 'off',
  cameraSignalsError: null,
  pendingDriftPrompt: null,
  ...overrides,
});

const loadPage = () =>
  import('../../dist/renderer/features/lecture-session/student_dashboard_page.mjs');

test('student dashboard shows a one-click prompt for a live enrolled lecture', async () => {
  const { StudentDashboardPage } = await loadPage();
  const page = StudentDashboardPage(
    baseModel({
      enrollments: [ENROLLMENT],
      availableSessions: [
        { session: SESSION, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
      ],
    }),
  );
  assert.match(page, /BIO101 lecture just started/);
  assert.match(page, /data-join-available-session="session-1"/);
  assert.match(page, /data-dismiss-available-session="session-1"/);
  assert.match(page, /Detected from a course you enrolled in/);
  // The manual code form stays available as a fallback.
  assert.match(page, /data-join-session-form/);
});

test('zoom-matched sessions explain the match and replace the join-code reminder', async () => {
  const { StudentDashboardPage } = await loadPage();
  const page = StudentDashboardPage(
    baseModel({
      zoomRunning: true,
      availableSessions: [
        { session: SESSION, matched_by: 'zoom_meeting', is_joined: false, is_auto_join_enabled: false },
      ],
    }),
  );
  assert.match(page, /Matched to the Zoom meeting open on this device/);
  assert.doesNotMatch(page, /data-dismiss-zoom-banner/);
});

test('zoom reminder falls back to the join code when nothing is live', async () => {
  const { StudentDashboardPage } = await loadPage();
  const withoutEnrollments = StudentDashboardPage(baseModel({ zoomRunning: true }));
  assert.match(withoutEnrollments, /Zoom detected — enter your join code, or enroll in a course/);
  const withEnrollments = StudentDashboardPage(
    baseModel({ zoomRunning: true, enrollments: [ENROLLMENT] }),
  );
  assert.match(withEnrollments, /none of your courses is live yet/);
});

test('joined, dismissed, and active sessions are not prompted again', async () => {
  const { selectPromptableSessions } = await loadPage();
  const other = { ...SESSION, session_id: 'session-2' };
  const third = { ...SESSION, session_id: 'session-3' };
  const promptable = selectPromptableSessions({
    activeSession: third,
    dismissedAvailableSessionIds: ['session-2'],
    availableSessions: [
      { session: SESSION, matched_by: 'enrollment', is_joined: true, is_auto_join_enabled: false },
      { session: other, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
      { session: third, matched_by: 'enrollment', is_joined: false, is_auto_join_enabled: false },
    ],
  });
  assert.deepEqual(promptable, []);
});

test('enrollment panel lists courses with an opt-in auto-join toggle and enroll form', async () => {
  const { StudentDashboardPage } = await loadPage();
  const page = StudentDashboardPage(
    baseModel({ enrollments: [{ ...ENROLLMENT, is_auto_join_enabled: true }] }),
  );
  assert.match(page, /<strong>BIO101<\/strong><small>Biology<\/small>/);
  assert.match(page, /data-enrollment-auto-join="enrollment-1" checked/);
  assert.match(page, /data-leave-course="enrollment-1"/);
  assert.match(page, /data-enroll-course-form/);
  const empty = StudentDashboardPage(baseModel());
  assert.match(empty, /No courses yet/);
  assert.doesNotMatch(empty, /data-enrollment-auto-join/);
});
