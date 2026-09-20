import { AppShell } from '../../components/app_shell.mjs';
import { SettingRow } from '../../components/setting_row.mjs';

/**
 * Builds the local processing, privacy, and account preferences page.
 *
 * @returns Account page markup.
 */
export function AccountPage(): string {
  return AppShell({
    route: 'account',
    role: 'student',
    eyebrow: 'Account',
    title: 'Privacy and preferences',
    content: `
      <section class="settings-layout">
        <article class="settings-card">
          <h2>Profile</h2>
          <div class="profile-summary"><span class="avatar avatar--large">AM</span><div><strong>Alex Morgan</strong><p>alex.morgan@example.edu</p></div><button class="secondary-button" type="button">Edit profile</button></div>
        </article>
        <article class="settings-card">
          <h2>On-device processing</h2>
          ${SettingRow('System audio capture', 'Capture lecture audio locally when you explicitly enable a session.', true)}
          ${SettingRow('Visual quality signals', 'Analyze consented frames locally without saving raw video.', true)}
          ${SettingRow('Automatic cloud upload', 'Raw media cannot be uploaded through Bloom.', false, true)}
        </article>
        <article class="settings-card settings-card--danger">
          <h2>Local data</h2><p>Removing lecture data deletes locally retained recordings, transcripts, and derived artifacts according to your retention settings.</p>
          <button class="danger-button" type="button" data-delete-local-data>Delete local lecture data</button>
        </article>
      </section>
    `,
  });
}
