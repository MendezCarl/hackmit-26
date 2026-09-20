import { AppShell } from '../../components/app_shell.mjs';
import { escapeHtml } from '../../components/html_text.mjs';
import { SettingRow } from '../../components/setting_row.mjs';

export type AccountModel = {
  isDemo: boolean;
  user: UserProfile | null;
  courses: Course[];
  joinedSessions: LectureSession[];
  consent: ConsentSettings | null;
  routeError?: string | null;
  isLoading?: boolean;
};
const FIXTURE_MODEL: AccountModel = {
  isDemo: true,
  user: null,
  courses: [],
  joinedSessions: [],
  consent: null,
};

/**
 * Builds the local processing, privacy, and account preferences page.
 *
 * @returns Account page markup.
 */
export function AccountPage(model: AccountModel = FIXTURE_MODEL): string {
  const user = model.user;
  return AppShell({
    route: 'account',
    role: user?.role === 'professor' ? 'educator' : 'student',
    eyebrow: 'Account',
    title: 'Privacy and preferences',
    demoMode: model.isDemo,
    profileName: user?.display_name ?? '?',
    courses: model.courses,
    joinedSessions: model.joinedSessions,
    content: `
      ${model.isLoading ? '<p class="empty-state">Loading from local service…</p>' : ''}
      ${model.routeError ? `<p class="empty-state">Account unavailable: ${escapeHtml(model.routeError)}</p>` : ''}
      <section class="settings-layout">
        <article class="settings-card">
          <h2>Profile</h2>
          <div class="profile-summary"><span class="avatar avatar--large">${escapeHtml(user?.display_name?.slice(0, 2).toUpperCase() ?? '--')}</span><div><strong>${escapeHtml(user?.display_name ?? 'Profile unavailable')}</strong><p>${escapeHtml(user?.email ?? 'No profile loaded')}</p></div><button class="secondary-button" type="button" disabled>Edit profile unavailable</button></div>
        </article>
        <article class="settings-card">
          <h2>On-device processing</h2>
          ${SettingRow('System audio capture', 'Capture lecture audio locally when you explicitly enable a session.', true)}
          ${SettingRow('Visual quality signals', 'Analyze consented frames locally without saving raw video.', true)}
          ${SettingRow('Automatic cloud upload', 'Raw media cannot be uploaded through Bloom.', false, true)}
        </article>
        <article class="settings-card settings-card--danger">
          <h2>Local data</h2><p>Deletion controls are not yet available from this build.</p>
          <button class="danger-button" type="button" disabled>Deletion controls unavailable</button>
        </article>
        <article class="settings-card"><h2>Anonymous analytics consent</h2><label class="checkbox-label"><input type="checkbox" data-analytics-consent ${model.consent?.analytics_opt_in ? 'checked' : ''}/> Allow aggregated analytics</label><p class="form-message" data-consent-message></p><button class="secondary-button" type="button" data-logout>Log out</button></article>
      </section>
    `,
  });
}
