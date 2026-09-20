import { AppRoute, buildRouteHash, resolveRoute } from './app/router.mjs';
import { renderPage } from './app/render_page.mjs';
import { renderSelectedMoment } from './components/moment_detail.mjs';

const appRoot = document.querySelector<HTMLElement>('#app');

if (!appRoot) {
  throw new Error('Bloom requires an #app mount element.');
}

/**
 * Refreshes the navigation status using the local backend health endpoint.
 *
 * @returns A promise that settles after the visible status is updated.
 */
const updateBackendStatus = async (): Promise<void> => {
  const statusPill = document.querySelector<HTMLElement>('[data-backend-state]');
  const statusLabel = document.querySelector<HTMLElement>('[data-backend-label]');

  if (!statusPill || !statusLabel) {
    return;
  }

  statusPill.dataset.backendState = 'checking';
  statusLabel.textContent = 'Checking local service';

  try {
    const health = await window.backend.health();
    statusPill.dataset.backendState = 'connected';
    statusLabel.textContent = health.status === 'ok' ? 'Local service ready' : 'Local service connected';
  } catch {
    statusPill.dataset.backendState = 'offline';
    statusLabel.textContent = 'Demo mode';
  }
};

/**
 * Connects timeline markers to the route-appropriate moment detail panel.
 *
 * @param route - Current application route used to select audience language.
 * @returns Nothing; event listeners are registered on rendered markers.
 */
const bindTimelineInteractions = (route: AppRoute): void => {
  const momentButtons = document.querySelectorAll<HTMLButtonElement>('[data-moment-id]');

  momentButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const momentId = button.dataset.momentId;
      const detail = document.querySelector<HTMLElement>('[data-moment-detail]');

      if (!momentId || !detail) {
        return;
      }

      momentButtons.forEach((candidate) => candidate.classList.remove('is-selected'));
      button.classList.add('is-selected');
      const audience = route === 'educator-summary' ? 'educator' : 'student';
      detail.outerHTML = renderSelectedMoment(momentId, audience);
    });
  });
};

/**
 * Connects summary tab buttons to their corresponding content panels.
 *
 * @returns Nothing; event listeners are registered on rendered tabs.
 */
const bindSummaryTabs = (): void => {
  const tabButtons = document.querySelectorAll<HTMLButtonElement>('[data-tab]');
  const tabPanels = document.querySelectorAll<HTMLElement>('[data-tab-panel]');

  tabButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const tabName = button.dataset.tab;

      tabButtons.forEach((candidate) => {
        const isSelected = candidate === button;
        candidate.classList.toggle('is-active', isSelected);
        candidate.setAttribute('aria-selected', String(isSelected));
      });

      tabPanels.forEach((panel) => {
        panel.hidden = panel.dataset.tabPanel !== tabName;
      });
    });
  });
};

/**
 * Connects lecture search and status controls to the visible card set.
 *
 * @returns Nothing; event listeners are registered when controls are present.
 */
const bindLibraryFilters = (): void => {
  const searchInput = document.querySelector<HTMLInputElement>('[data-library-search]');
  const statusFilter = document.querySelector<HTMLSelectElement>('[data-library-filter]');
  const cards = document.querySelectorAll<HTMLElement>('[data-lecture-title]');
  const emptyState = document.querySelector<HTMLElement>('[data-library-empty]');

  if (!searchInput || !statusFilter || !emptyState) {
    return;
  }

  const applyFilters = (): void => {
    const query = searchInput.value.trim().toLowerCase();
    const selectedStatus = statusFilter.value;
    let visibleCount = 0;

    cards.forEach((card) => {
      const matchesQuery = card.dataset.lectureTitle?.includes(query) ?? false;
      const matchesStatus = selectedStatus === 'all' || card.dataset.lectureStatus === selectedStatus;
      const isVisible = matchesQuery && matchesStatus;
      card.hidden = !isVisible;
      visibleCount += isVisible ? 1 : 0;
    });

    emptyState.hidden = visibleCount > 0;
  };

  searchInput.addEventListener('input', applyFilters);
  statusFilter.addEventListener('change', applyFilters);
};

/**
 * Connects page-specific prototype buttons and forms.
 *
 * @returns Nothing; event listeners are registered when actions are present.
 */
const bindPageActions = (): void => {
  const consentDialog = document.querySelector<HTMLDialogElement>('[data-consent-dialog]');
  const openConsentButton = document.querySelector<HTMLButtonElement>('[data-open-consent]');
  openConsentButton?.addEventListener('click', () => consentDialog?.showModal());

  const loginForm = document.querySelector<HTMLFormElement>('[data-login-form]');
  loginForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    if (loginForm.reportValidity()) {
      window.location.hash = buildRouteHash('student-dashboard');
    }
  });

  document.querySelector<HTMLButtonElement>('[data-export-report]')?.addEventListener('click', (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    button.textContent = 'Summary exported';
    button.disabled = true;
  });

  document.querySelector<HTMLButtonElement>('[data-delete-local-data]')?.addEventListener('click', (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    button.textContent = 'Demo: no local data deleted';
  });
};

/**
 * Renders the active hash route and binds interactions for the new page tree.
 *
 * @returns Nothing; the application mount element is replaced in place.
 */
const renderApplication = (): void => {
  const route = resolveRoute(window.location.hash);
  appRoot.innerHTML = renderPage(route);
  document.title = `Bloom · ${route.split('-').map((word) => word[0].toUpperCase() + word.slice(1)).join(' ')}`;

  bindTimelineInteractions(route);
  bindSummaryTabs();
  bindLibraryFilters();
  bindPageActions();
  void updateBackendStatus();
};

window.addEventListener('hashchange', renderApplication);

if (!window.location.hash) {
  window.location.hash = buildRouteHash('student-dashboard');
} else {
  renderApplication();
}
