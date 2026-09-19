const healthEl = document.querySelector<HTMLElement>('[data-health]');
const statusEl = document.querySelector<HTMLElement>('[data-status]');
const retryButton = document.querySelector<HTMLButtonElement>('[data-retry]');

if (!healthEl || !statusEl || !retryButton) {
  throw new Error('Expected frontend shell elements were not found.');
}

const renderBackendState = async (): Promise<void> => {
  healthEl.textContent = 'Checking backend...';
  statusEl.textContent = '';

  try {
    const [health, status] = await Promise.all([
      window.backend.health(),
      window.backend.status(),
    ]);

    healthEl.textContent = `Backend health: ${health.status}`;
    statusEl.textContent = status.message;
  } catch {
    healthEl.textContent = 'Backend unavailable';
    statusEl.textContent = 'Start FastAPI on http://127.0.0.1:8000, then try again.';
  }
};

retryButton.addEventListener('click', () => {
  void renderBackendState();
});

void renderBackendState();
