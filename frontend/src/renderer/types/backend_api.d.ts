/** Response shapes exposed by the context-isolated preload bridge. */
type BackendHealth = {
  status: string;
};

type BackendStatus = {
  message: string;
};

type BackendApi = {
  health: () => Promise<BackendHealth>;
  status: () => Promise<BackendStatus>;
};

interface Window {
  backend: BackendApi;
}
