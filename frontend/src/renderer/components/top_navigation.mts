import { AppRoute, buildRouteHash } from '../app/router.mjs';
import { escapeHtml } from './html_text.mjs';

/**
 * Derives a compact avatar label from a display name.
 *
 * @param profileName - Current user's display name.
 * @returns Up to two initials, or `?` when no name is available.
 */
export function deriveProfileInitials(profileName: string): string {
  const words = profileName.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase();
}

/**
 * Builds the authenticated top navigation with role and account controls.
 *
 * @param route - Current route used to highlight account navigation.
 * @param role - Active demo role used to build the role-switch link.
 * @returns Header markup for authenticated pages.
 */
export function TopNavigation(
  route: AppRoute,
  role: 'student' | 'educator',
  profileName = '?',
): string {
  const safeProfileName = escapeHtml(profileName);
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
          <span class="avatar">${escapeHtml(deriveProfileInitials(profileName))}</span>
          <span class="profile-link__copy"><strong>${safeProfileName}</strong><small>${role === 'student' ? 'Student' : 'Educator'}</small></span>
        </a>
      </div>
    </header>
  `;
}
