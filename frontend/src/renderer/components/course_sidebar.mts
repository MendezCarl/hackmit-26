import { AppRoute, buildRouteHash } from '../app/router.mjs';

const STUDENT_LINKS: Array<{ label: string; route: AppRoute; icon: string }> = [
  { label: 'Overview', route: 'student-dashboard', icon: '⌂' },
  { label: 'Lecture library', route: 'lecture-library', icon: '▤' },
  { label: 'Latest summary', route: 'student-summary', icon: '✦' },
];

const EDUCATOR_LINKS: Array<{ label: string; route: AppRoute; icon: string }> = [
  { label: 'Course insights', route: 'educator-dashboard', icon: '⌂' },
  { label: 'Lecture report', route: 'educator-summary', icon: '↗' },
];

/**
 * Builds the course and lecture navigation used by dashboard pages.
 *
 * @param route - Current application route used to highlight the active link.
 * @param role - Active demo role used to choose role-specific navigation.
 * @returns Sidebar markup with expandable course content.
 */
export function CourseSidebar(
  route: AppRoute,
  role: 'student' | 'educator',
  isDemo = true,
): string {
  const links = role === 'student' ? STUDENT_LINKS : EDUCATOR_LINKS;
  const renderedLinks = links
    .map(
      (link) => `
        <a class="side-link ${route === link.route ? 'is-active' : ''}" href="${buildRouteHash(link.route)}">
          <span aria-hidden="true">${link.icon}</span>${link.label}
        </a>`,
    )
    .join('');

  return `
    <aside class="course-sidebar" aria-label="Course navigation">
      <p class="sidebar-label">Workspace</p>
      <nav class="side-nav">${renderedLinks}</nav>
      ${
        isDemo
          ? `<p class="sidebar-label sidebar-label--courses">Courses</p>
      <details class="course-group" open>
        <summary><span class="course-dot course-dot--teal"></span><span>BIO 101<small>Foundations of Biology</small></span></summary>
        <a href="${buildRouteHash(role === 'student' ? 'student-summary' : 'educator-summary')}">Sep 19 · Cellular respiration</a>
        <a href="${buildRouteHash(role === 'student' ? 'student-summary' : 'educator-summary')}">Sep 17 · Cell membranes</a>
        <a href="${buildRouteHash(role === 'student' ? 'student-summary' : 'educator-summary')}">Sep 15 · Enzymes</a>
      </details>
      <details class="course-group">
        <summary><span class="course-dot course-dot--gold"></span><span>CHEM 105<small>General Chemistry</small></span></summary>
        <a href="${buildRouteHash(role === 'student' ? 'student-summary' : 'educator-summary')}">Sep 18 · Molecular geometry</a>
      </details>`
          : '<p class="empty-state">No course navigation is available yet.</p>'
      }
      <div class="privacy-note">
        <span aria-hidden="true">◇</span>
        <p><strong>Private by design</strong><br />Raw media stays on this device.</p>
      </div>
    </aside>
  `;
}
