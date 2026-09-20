import { AppShell } from '../../components/app_shell.mjs';

/**
 * Builds the public Bloom login page.
 *
 * @returns Login form and product-introduction markup.
 */
export function LoginPage(): string {
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
        <form class="login-card" data-login-form>
          <p class="eyebrow">Welcome back</p><h2>Sign in to Bloom</h2>
          <label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@example.edu" /></label>
          <label>Password<input type="password" name="password" autocomplete="current-password" required minlength="8" placeholder="At least 8 characters" /></label>
          <div class="form-row"><label class="checkbox-label"><input type="checkbox" name="remember" />Remember me</label><button class="link-button" type="button">Forgot password?</button></div>
          <p class="form-message" data-form-message aria-live="polite"></p>
          <button class="primary-button primary-button--full" type="submit">Sign in</button>
          <p class="demo-note">Prototype screen: use any valid email and an 8-character password.</p>
        </form>
      </section>
    `,
  });
}
