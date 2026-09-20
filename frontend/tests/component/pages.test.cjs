const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const { join } = require('node:path');
const test = require('node:test');
const routes = [
  'student-dashboard',
  'student-summary',
  'lecture-library',
  'home',
  'course',
  'lecture',
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
  const dashboardModel = {
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
    zoomRunning: false,
    zoomBannerDismissed: false,
    externalTextConsentGranted: false,
    externalTextConsentNote: null,
    cameraSignalsEnabled: false,
    cameraSignalsStatus: 'off',
    cameraSignalsError: null,
    pendingDriftPrompt: null,
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
  };
  const page = StudentDashboardPage(dashboardModel);

  assert.match(page, /data-zoom-recovery-cue/);
  assert.match(page, /Possible missed moment/);
  assert.match(page, /Marked for review, not scored/);
  assert.match(page, /data-external-text-consent/);
  assert.match(page, /Allow bounded transcript text to be sent to the AI provider for recovery cards/);
  assert.match(page, /data-camera-signals/);
  assert.match(page, /Camera off/);
  assert.match(page, /<input type="checkbox" data-camera-signals\s*\/>/);
  assert.doesNotMatch(page, /attention score/i);
  const watchingPage = StudentDashboardPage({
    ...dashboardModel,
    cameraSignalsEnabled: true,
    cameraSignalsStatus: 'watching',
  });
  assert.match(watchingPage, /<input type="checkbox" data-camera-signals checked \/>/);
  assert.match(watchingPage, /Watching locally…/);
  const driftPage = StudentDashboardPage({
    ...dashboardModel,
    pendingDriftPrompt: {
      event_id: 'event-2',
      session_id: 'session-1',
      event_type: 'phone_visible',
      start_ms: 120000,
      end_ms: 126000,
      confidence: 0.8,
      signals: ['phone_visible'],
    },
  });
  assert.match(driftPage, /data-request-recovery="event-2"/);
  assert.match(driftPage, /Looks like you may have drifted around 02:00/);
});

test('educator home renders metrics and course links', async () => {
  const { HomePage } = await import('../../dist/renderer/features/home/home_page.mjs');
  const page = HomePage({
    isDemo: false,
    courses: [
      {
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Biology',
        code: 'BIO 101',
        created_at: '2026-01-01T00:00:00.000Z',
      },
    ],
    lecturesByCourse: { 'course-1': [] },
    sessions: [],
    professorMetricsBySession: {},
    professorSummariesBySession: {},
    professorMetricsError: null,
    activeSession: null,
    zoomRunning: true,
    zoomBannerDismissed: false,
  });
  assert.match(page, /Zoom detected — start a session from a course below/);
  assert.match(page, /No lecture data yet/);
  assert.match(page, /course\?course_id=course-1/);
  assert.match(page, /data-open-course-modal/);
  const metricsErrorPage = HomePage({
    isDemo: false,
    courses: [],
    lecturesByCourse: {},
    sessions: [],
    professorMetricsBySession: {},
    professorSummariesBySession: {},
    professorMetricsError: 'An approved aggregation policy is required.',
    activeSession: null,
    zoomRunning: false,
    zoomBannerDismissed: false,
  });
  assert.match(metricsErrorPage, /An approved aggregation policy is required\./);
  const metricsPage = HomePage({
    isDemo: false,
    courses: [],
    lecturesByCourse: {},
    sessions: [],
    professorMetricsBySession: {
      'session-1': {
        session_id: 'session-1',
        policy_version: 'test',
        status: 'available',
        minimum_group_size: 5,
        bucket_ms: 30000,
        buckets: [
          {
            start_ms: 0,
            end_ms: 30000,
            status: 'available',
            is_hotspot: true,
            transcript_chunk_ids: [],
          },
        ],
        continuity: { numerator: 3, denominator: 4, ratio: 0.75 },
        delivery_findings: [
          {
            start_ms: 0,
            end_ms: 1000,
            signal_type: 'audio',
            confidence: 0.8,
            suggested_action: 'Review',
          },
        ],
        recovery_outcomes_status: 'not_collected',
      },
    },
    professorSummariesBySession: {
      'session-1': {
        summary_id: 'summary-1',
        session_id: 'session-1',
        participant_count: 12,
        minimum_group_size: 5,
        aggregation_window_ms: 30000,
        is_suppressed: false,
        generated_at: '2026-01-01T00:00:00.000Z',
      },
    },
    activeSession: null,
  });
  assert.match(metricsPage, /Lecture continuity/);
  assert.match(metricsPage, />75%<|>75%/);
  assert.match(metricsPage, />12</);
});

test('course and lecture pages render requested empty states', async () => {
  const { CoursePage } = await import('../../dist/renderer/features/courses/course_page.mjs');
  const { LectureSummaryPage } = await import(
    '../../dist/renderer/features/lecture-summary/lecture_summary_page.mjs'
  );
  assert.match(
    CoursePage({
      isDemo: false,
      course: null,
      lectures: [],
      allCourses: [],
      allLecturesByCourse: {},
      sessionsByLecture: {},
      activeSession: null,
    }),
    /Course not found/,
  );
  assert.match(
    LectureSummaryPage({
      isDemo: false,
      lecture: {
        lecture_id: 'lecture-1',
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Cellular respiration',
        created_at: '2026-01-01T00:00:00.000Z',
      },
      course: {
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Biology',
        code: 'BIO 101',
        created_at: '2026-01-01T00:00:00.000Z',
      },
      session: null,
      allCourses: [],
      allLecturesByCourse: {},
      summary: null,
      metrics: null,
    }),
    /No sessions yet for this lecture/,
  );
});

test('educator table rows keep navigation links separate from action buttons', async () => {
  const { CoursePage } = await import('../../dist/renderer/features/courses/course_page.mjs');
  const page = CoursePage({
    isDemo: false,
    course: {
      course_id: 'course-1',
      owner_id: 'owner-1',
      title: 'Biology',
      code: 'BIO 101',
      created_at: '2026-01-01T00:00:00.000Z',
    },
    lectures: [
      {
        lecture_id: 'lecture-old',
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Cellular respiration',
        created_at: '2026-01-01T00:00:00.000Z',
      },
      {
        lecture_id: 'lecture-new',
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Cell membranes',
        created_at: '2026-01-03T00:00:00.000Z',
      },
    ],
    allCourses: [],
    allLecturesByCourse: {},
    sessionsByLecture: {},
    activeSession: null,
  });
  assert.match(page, /class="table-row lecture-log-row"/);
  assert.match(page, /class="table-row__link"/);
  assert.doesNotMatch(page, /<a class="table-row(?:[" >])/);
  assert.doesNotMatch(page, /data-start-session/);
  assert.ok(page.indexOf('Cell membranes') < page.indexOf('Cellular respiration'));
});

test('educator sidebar starts with Home and caps lecture links at five', async () => {
  const { CourseSidebar } = await import('../../dist/renderer/components/course_sidebar.mjs');
  const lectures = Array.from({ length: 6 }, (_, index) => ({
    lecture_id: `lecture-${index}`,
    course_id: 'course-1',
    owner_id: 'owner-1',
    title: `Lecture ${index}`,
    created_at: `2026-01-0${Math.min(index + 1, 9)}T00:00:00.000Z`,
  }));
  const sidebar = CourseSidebar(
    'home',
    'educator',
    false,
    [
      {
        course_id: 'course-1',
        owner_id: 'owner-1',
        title: 'Biology',
        code: 'BIO 101',
        created_at: '2026-01-01T00:00:00.000Z',
      },
    ],
    [],
    { 'course-1': lectures },
  );
  assert.match(sidebar, /Home/);
  assert.match(sidebar, /course-group__code">BIO 101<\/span>/);
  assert.match(sidebar, /course-group__title">Biology<\/span>/);
  assert.doesNotMatch(sidebar, /BIO 101 · Biology/);
  assert.equal((sidebar.match(/href="#\/lecture\?/g) ?? []).length, 5);
});

test('student sessions show join codes and status badges', async () => {
  const { StudentDashboardPage } = await import(
    '../../dist/renderer/features/lecture-session/student_dashboard_page.mjs'
  );
  const page = StudentDashboardPage({
    isDemo: false,
    user: { user_id: 'user-1', display_name: 'Alex', email: 'alex@example.test', role: 'student' },
    courses: [],
    activeSession: null,
    joinedSessions: [
      {
        session_id: 'session-1',
        lecture_id: 'lecture-1',
        owner_id: 'owner-1',
        course_id: 'course-1',
        title: 'Cellular respiration',
        join_code: 'K7PQ2M',
        mode: 'in_person',
        status: 'ended',
        started_at: '2026-01-01T00:00:00.000Z',
        session_clock_origin: '2026-01-01T00:00:00.000Z',
      },
    ],
    participantCount: null,
    submittedEvents: [],
    zoomRunning: false,
    zoomBannerDismissed: false,
    externalTextConsentGranted: false,
    externalTextConsentNote: null,
  });
  assert.match(page, /<strong>Cellular respiration<\/strong>/);
  assert.match(page, /Join code <code>K7PQ2M<\/code>/);
  assert.match(page, /class="status-badge status-badge--ready">ended<\/span>/);
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
