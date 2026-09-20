import { LoginPage } from '../features/authentication/login_page.mjs';
import { LectureLibraryPage } from '../features/lecture-library/lecture_library_page.mjs';
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
 * @returns Full page markup composed from feature pages and shared components.
 */
export function renderPage(route: AppRoute, state?: BackendSessionState): string {
  const isReal = Boolean(state?.user);
  const pages: Record<AppRoute, () => string> = {
    'student-dashboard': () =>
      StudentDashboardPage({
        isDemo: !isReal,
        user: state?.user ?? null,
        activeSession: state?.activeSession ?? null,
        joinedSessions: state?.joinedSessions ?? [],
        participantCount: state?.participantCount ?? null,
      }),
    'student-summary': () =>
      StudentSummaryPage({
        isDemo: !isReal,
        profileName: state?.user?.display_name,
        session: state?.activeSession ?? null,
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
