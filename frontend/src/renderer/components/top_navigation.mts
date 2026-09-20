import { AppRoute, buildRouteHash } from '../app/router.mjs';

/**
 * Builds the authenticated top navigation with role and account controls.
 *
 * @param route - Current route used to highlight account navigation.
 * @param role - Active demo role used to build the role-switch link.
 * @returns Header markup for authenticated pages.
 */
export function TopNavigation(route: AppRoute, role: 'student' | 'educator'): string {
  const roleRoute = role === 'student' ? 'educator-dashboard' : 'student-dashboard';
  const roleLabel = role === 'student' ? 'Educator view' : 'Student view';

  return `
    <header class="top-nav">
      <a class="brand" href="${buildRouteHash(role === 'student' ? 'student-dashboard' : 'educator-dashboard')}" aria-label="Bloom home">
        <img src="./assets/bloom-icon.svg" alt="" />
        <span>Bloom</span>
      </a>
      <div class="top-nav__actions">
        <span class="connection-pill" data-backend-state="checking" aria-live="polite">
          <span class="connection-pill__dot"></span>
          <span data-backend-label>Checking local service</span>
        </span>
        <a class="role-switch" href="${buildRouteHash(roleRoute)}">${roleLabel}</a>
        <a class="profile-link ${route === 'account' ? 'is-active' : ''}" href="${buildRouteHash('account')}" aria-label="Open account settings">
          <span class="avatar">AM</span>
          <span class="profile-link__copy"><strong>Alex Morgan</strong><small>${role === 'student' ? 'Student' : 'Educator'}</small></span>
        </a>
      </div>
    </header>
  `;
}
