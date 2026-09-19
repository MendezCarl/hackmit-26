import { contextBridge } from 'electron';

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

const apiBaseUrl = 'http://127.0.0.1:8000';

const getJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(`${apiBaseUrl}${path}`);

  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
};

const backendApi: BackendApi = {
  health: () => getJson<BackendHealth>('/health'),
  status: () => getJson<BackendStatus>('/api/status'),
};

contextBridge.exposeInMainWorld('backend', backendApi);
