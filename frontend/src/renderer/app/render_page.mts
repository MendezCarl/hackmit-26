import { LoginPage } from '../features/authentication/login_page.mjs';
import { LectureLibraryPage } from '../features/lecture-library/lecture_library_page.mjs';
import { StudentDashboardPage } from '../features/lecture-session/student_dashboard_page.mjs';
import { AccountPage } from '../features/privacy-settings/account_page.mjs';
import { EducatorDashboardPage } from '../features/professor-summary/educator_dashboard_page.mjs';
import { EducatorSummaryPage } from '../features/professor-summary/educator_summary_page.mjs';
import { StudentSummaryPage } from '../features/recovery-cards/student_summary_page.mjs';
import { AppRoute } from './router.mjs';

/**
 * Renders the complete markup for a Bloom application route.
 *
 * @param route - Supported route selected by the hash router.
 * @returns Full page markup composed from feature pages and shared components.
 */
export function renderPage(route: AppRoute): string {
  const pages: Record<AppRoute, () => string> = {
    'student-dashboard': StudentDashboardPage,
    'student-summary': StudentSummaryPage,
    'lecture-library': LectureLibraryPage,
    'educator-dashboard': EducatorDashboardPage,
    'educator-summary': EducatorSummaryPage,
    account: AccountPage,
    login: LoginPage,
  };

  return pages[route]();
}
