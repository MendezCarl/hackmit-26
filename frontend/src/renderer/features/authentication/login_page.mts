import { AppShell } from '../../components/app_shell.mjs';

export type LoginPageModel = { isDemo: boolean };
const FIXTURE_MODEL: LoginPageModel = { isDemo: true };

/**
 * Builds the public Bloom login page.
 *
 * @param _model - Optional view model reserved for authentication status.
 * @returns Login form and product-introduction markup.
 */
export function LoginPage(_model: LoginPageModel = FIXTURE_MODEL): string {
  return AppShell({
    route: 'login',
    role: 'student',
    title: '',
    showSidebar: false,
    content: `
      <section class="login-page">
        <div class="login-intro">
          <img src="./assets/bloom-icon.svg" alt="" />
          <p class="eyebrow">Private lecture recovery</p>
          <h1>Learning has a rhythm. Find yours again.</h1>
          <p>Bloom helps students recover missed context and gives educators anonymous, actionable lecture insights.</p>
        </div>
        <form class="login-card" data-login-form data-auth-mode="login">
          <p class="eyebrow" data-auth-eyebrow>Welcome back</p><h2 data-auth-title>Sign in to Bloom</h2>
          <label data-register-field hidden>Display name<input type="text" name="display_name" autocomplete="name" minlength="1" /></label>
          <label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@example.edu" /></label>
          <label>Password<input type="password" name="password" autocomplete="current-password" required minlength="8" placeholder="At least 8 characters" /></label>
          <label data-register-field hidden>Role<select name="role"><option value="student">Student</option><option value="professor">Professor</option></select></label>
          <div class="form-row"><label class="checkbox-label" data-login-only><input type="checkbox" name="remember" />Remember me</label><button class="link-button" type="button" data-auth-toggle>Create account</button></div>
          <p class="form-message" data-form-message aria-live="polite"></p>
          <button class="primary-button primary-button--full" type="submit" data-auth-submit>Sign in</button>
        </form>
      </section>
    `,
  });
}
