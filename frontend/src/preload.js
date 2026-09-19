const { contextBridge } = require('electron');

const apiBaseUrl = 'http://127.0.0.1:8000';

contextBridge.exposeInMainWorld('backend', {
  async health() {
    const response = await fetch(`${apiBaseUrl}/health`);
    return response.json();
  },
  async status() {
    const response = await fetch(`${apiBaseUrl}/api/status`);
    return response.json();
  },
});
