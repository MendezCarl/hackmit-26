import { AppShell } from '../../components/app_shell.mjs';
import { SettingRow } from '../../components/setting_row.mjs';

export type AccountModel = { isDemo: boolean; user: UserProfile | null; consent: ConsentSettings | null };
const FIXTURE_MODEL: AccountModel = { isDemo: true, user: null, consent: null };

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
    content: `
      <section class="settings-layout">
        <article class="settings-card">
          <h2>Profile</h2>
          <div class="profile-summary"><span class="avatar avatar--large">${user?.display_name?.slice(0, 2).toUpperCase() ?? 'AM'}</span><div><strong>${user?.display_name ?? 'Alex Morgan'}</strong><p>${user?.email ?? 'alex.morgan@example.edu'}</p></div><button class="secondary-button" type="button">Edit profile</button></div>
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
