import { LoginPage } from '../features/authentication/login_page.mjs';
import { CoursePage } from '../features/courses/course_page.mjs';
import { HomePage } from '../features/home/home_page.mjs';
import { LectureLibraryPage } from '../features/lecture-library/lecture_library_page.mjs';
import { LectureSummaryPage } from '../features/lecture-summary/lecture_summary_page.mjs';
import { StudentDashboardPage } from '../features/lecture-session/student_dashboard_page.mjs';
import { AccountPage } from '../features/privacy-settings/account_page.mjs';
import { EducatorDashboardPage } from '../features/professor-summary/educator_dashboard_page.mjs';
import { EducatorSummaryPage } from '../features/professor-summary/educator_summary_page.mjs';
import { StudentSummaryPage } from '../features/recovery-cards/student_summary_page.mjs';
import type { BackendSessionState } from '../services/backend_session_state.mjs';
import { AppRoute } from './router.mjs';

/**
 * Renders the complete markup for a Bloom application route.
 *
 * @param route - Supported route selected by the hash router.
 * @param state - Optional authenticated renderer state.
 * @param params - Query parameters for course or lecture detail routes.
 * @returns Full page markup composed from feature pages and shared components.
 */
export function renderPage(
  route: AppRoute,
  state?: BackendSessionState,
  params: URLSearchParams = new URLSearchParams(),
): string {
  const isReal = Boolean(state?.user);
  const selectedCourse = params.has('course_id')
    ? state?.courses?.find((course) => course.course_id === params.get('course_id')) ?? null
    : state?.courses?.[0] ?? null;
  const allLectures = Object.values(state?.lecturesByCourse ?? {}).flat();
  const selectedLecture = params.has('lecture_id')
    ? allLectures.find((lecture) => lecture.lecture_id === params.get('lecture_id')) ?? null
    : allLectures[0] ?? null;
  const pages: Record<AppRoute, () => string> = {
    'student-dashboard': () =>
      StudentDashboardPage({
        isDemo: !isReal,
        user: state?.user ?? null,
        courses: state?.courses ?? [],
        activeSession: state?.activeSession ?? null,
        joinedSessions: state?.joinedSessions ?? [],
        participantCount: state?.participantCount ?? null,
        submittedEvents: state?.submittedEvents ?? [],
        zoomRunning: state?.zoomRunning ?? false,
        zoomBannerDismissed: state?.zoomBannerDismissed ?? false,
      }),
    'student-summary': () =>
      StudentSummaryPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        session: state?.activeSession ?? null,
        courses: state?.courses ?? [],
        joinedSessions: state?.joinedSessions ?? [],
        submittedEvents: state?.submittedEvents ?? [],
        recoveryCards: state?.recoveryCards ?? [],
        transcript: state?.transcriptChunks ?? [],
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    'lecture-library': () =>
      LectureLibraryPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        role: state?.user?.role === 'professor' ? 'educator' : 'student',
        courses: state?.courses ?? [],
        lectures: Object.values(state?.lecturesByCourse ?? {}).flat(),
        joinedSessions: state?.joinedSessions ?? [],
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    home: () =>
      HomePage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        courses: state?.courses ?? [],
        lecturesByCourse: state?.lecturesByCourse ?? {},
        sessions: state?.sessions ?? [],
        professorMetricsBySession: state?.professorMetricsBySession ?? {},
        professorSummariesBySession: state?.professorSummariesBySession ?? {},
        activeSession: state?.activeSession ?? null,
        zoomRunning: state?.zoomRunning ?? false,
        zoomBannerDismissed: state?.zoomBannerDismissed ?? false,
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    course: () =>
      CoursePage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        course: selectedCourse,
        lectures: selectedCourse
          ? state?.lecturesByCourse?.[selectedCourse.course_id] ?? []
          : [],
        allCourses: state?.courses ?? [],
        allLecturesByCourse: state?.lecturesByCourse ?? {},
        sessionsByLecture: state?.sessionsByLecture ?? {},
        activeSession: state?.activeSession ?? null,
        routeError: state?.routeError,
      }),
    lecture: () =>
      LectureSummaryPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        lecture: selectedLecture,
        course:
          state?.courses?.find(
            (course) =>
              course.course_id ===
              selectedLecture?.course_id,
          ) ?? null,
        session: state?.selectedSession ?? null,
        allCourses: state?.courses ?? [],
        allLecturesByCourse: state?.lecturesByCourse ?? {},
        summary: state?.selectedSession
          ? state?.professorSummariesBySession[state.selectedSession.session_id] ?? null
          : null,
        metrics: state?.selectedSession
          ? state?.professorMetricsBySession[state.selectedSession.session_id] ?? null
          : null,
        routeError: state?.routeError,
      }),
    'educator-dashboard': () =>
      EducatorDashboardPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        courses: state?.courses ?? [],
        lecturesByCourse: state?.lecturesByCourse ?? {},
        activeSession: state?.activeSession ?? null,
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    'educator-summary': () =>
      EducatorSummaryPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        session: state?.activeSession ?? null,
        courses: state?.courses ?? [],
        summary: state?.professorSummary ?? null,
        metrics: state?.professorMetrics ?? null,
        summaryError: state?.professorSummaryError,
        metricsError: state?.professorMetricsError,
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    account: () =>
      AccountPage({
        isDemo: !isReal,
        user: state?.user ?? null,
        courses: state?.courses ?? [],
        joinedSessions: state?.joinedSessions ?? [],
        consent: state?.consent ?? null,
        routeError: state?.routeError,
        isLoading: state?.routeLoading,
      }),
    login: LoginPage,
  };

  return pages[route]();
}
