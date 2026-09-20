import { AppRoute } from '../app/router.mjs';
import { CourseSidebar } from './course_sidebar.mjs';
import { LoginNavigation } from './login_navigation.mjs';
import { TopNavigation } from './top_navigation.mjs';

export type AppShellOptions = {
  route: AppRoute;
  role: 'student' | 'educator';
  title: string;
  eyebrow?: string;
  content: string;
  showSidebar?: boolean;
  demoMode?: boolean;
  profileName?: string;
};

/**
 * Builds the shared Bloom application shell around a page body.
 *
 * @param options - Current route, user role, page heading, and rendered page content.
 * @returns Complete application markup for the selected page.
 */
export function AppShell(options: AppShellOptions): string {
  const sidebar =
    options.showSidebar === false
      ? ''
      : CourseSidebar(options.route, options.role, options.demoMode !== false);
  const layoutClass =
    options.showSidebar === false ? 'app-layout app-layout--centered' : 'app-layout';
  const navigation =
    options.route === 'login'
      ? LoginNavigation()
      : TopNavigation(options.route, options.role, options.profileName);
  const pageHeading =
    options.title || options.eyebrow
      ? `
          <header class="page-heading">
            ${options.eyebrow ? `<p class="eyebrow">${options.eyebrow}</p>` : ''}
            ${options.title ? `<h1>${options.title}</h1>` : ''}
          </header>
        `
      : '';

  return `
    <div class="app-frame">
      ${navigation}
      <div class="${layoutClass}">
        ${sidebar}
        <main class="page-content" id="main-content" tabindex="-1">
          ${pageHeading}
          ${options.content}
          ${options.demoMode === false || options.route === 'login' ? '' : '<span class="demo-badge">Demo mode · synthetic data</span>'}
        </main>
      </div>
    </div>
  `;
}
