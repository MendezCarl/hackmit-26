const healthEl = document.querySelector('[data-health]');
const statusEl = document.querySelector('[data-status]');
const retryButton = document.querySelector('[data-retry]');

const renderBackendState = async () => {
  healthEl.textContent = 'Checking backend...';
  statusEl.textContent = '';

  try {
    const [health, status] = await Promise.all([
      window.backend.health(),
      window.backend.status(),
    ]);

    healthEl.textContent = `Backend health: ${health.status}`;
    statusEl.textContent = status.message;
  } catch (error) {
    healthEl.textContent = 'Backend unavailable';
    statusEl.textContent = 'Start FastAPI on http://127.0.0.1:8000, then try again.';
  }
};

retryButton.addEventListener('click', renderBackendState);

renderBackendState();
