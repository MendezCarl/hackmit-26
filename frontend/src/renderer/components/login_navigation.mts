import { buildRouteHash } from '../app/router.mjs';

/**
 * Builds the public navigation displayed on the login page.
 *
 * @returns Header markup with Bloom branding and a prototype link.
 */
export function LoginNavigation(): string {
  return `
    <header class="top-nav">
      <a class="brand" href="${buildRouteHash('login')}" aria-label="Bloom sign in">
        <img src="./assets/bloom-icon.svg" alt="" />
        <span>Bloom</span>
      </a>
      <a class="role-switch" href="${buildRouteHash('student-dashboard')}">View prototype</a>
    </header>
  `;
}
