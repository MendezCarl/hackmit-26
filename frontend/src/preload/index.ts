/** Safe, context-isolated bridge between the renderer and local backend. */
import { contextBridge, ipcRenderer } from 'electron';

const invokeBackend = async <T>(operation: string, args: unknown[]): Promise<T> => {
  const result = (await ipcRenderer.invoke(`backend:${operation}`, ...args)) as
    { ok: true; value: T } | { ok: false; error: BackendRequestErrorShape };
  if (!result.ok) {
    const error = new Error(result.error.message) as Error & BackendRequestErrorShape;
    error.name = 'BackendRequestError';
    error.status = result.error.status;
    error.code = result.error.code;
    throw error;
  }
  return result.value;
};

const backendApi: BackendApi = {
  health: () => invokeBackend('health', []),
  apiStatus: () => invokeBackend('apiStatus', []),
  readApiStatus: () => invokeBackend('readApiStatus', []),
  register: (request) => invokeBackend('register', [request]),
  login: (request) => invokeBackend('login', [request]),
  logout: () => invokeBackend('logout', []),
  readMe: () => invokeBackend('readMe', []),
  listCourses: () => invokeBackend('listCourses', []),
  createCourse: (request) => invokeBackend('createCourse', [request]),
  listLectures: (courseId) => invokeBackend('listLectures', [courseId]),
  createLecture: (request) => invokeBackend('createLecture', [request]),
  createSession: (request) => invokeBackend('createSession', [request]),
  listSessions: (filter) => invokeBackend('listSessions', [filter]),
  readSession: (sessionId) => invokeBackend('readSession', [sessionId]),
  resolveJoinCode: (joinCode) => invokeBackend('resolveJoinCode', [joinCode]),
  joinSession: (sessionId) => invokeBackend('joinSession', [sessionId]),
  listEnrollments: () => invokeBackend('listEnrollments', []),
  enrollInCourse: (request) => invokeBackend('enrollInCourse', [request]),
  updateEnrollment: (enrollmentId, request) =>
    invokeBackend('updateEnrollment', [enrollmentId, request]),
  leaveCourse: (enrollmentId) => invokeBackend('leaveCourse', [enrollmentId]),
  listAvailableSessions: (zoomMeetingId) =>
    invokeBackend('listAvailableSessions', [zoomMeetingId ?? null]),
  updateAggregationConsent: (sessionId, consent) =>
    invokeBackend('updateAggregationConsent', [sessionId, consent]),
  updateExternalTextConsent: (sessionId, consent) =>
    invokeBackend('updateExternalTextConsent', [sessionId, consent]),
  ingestEvents: (sessionId, request) => invokeBackend('ingestEvents', [sessionId, request]),
  ingestTranscript: (sessionId, request) => invokeBackend('ingestTranscript', [sessionId, request]),
  readTranscript: (sessionId, startMs, endMs) =>
    invokeBackend('readTranscript', [sessionId, startMs, endMs]),
  startZoomRtms: (sessionId, request) => invokeBackend('startZoomRtms', [sessionId, request]),
  readZoomStatus: (sessionId) => invokeBackend('readZoomStatus', [sessionId]),
  requestRecoveryCard: (sessionId, request, key) =>
    invokeBackend('requestRecoveryCard', [sessionId, request, key]),
  readRecoveryCard: (sessionId, cardId) => invokeBackend('readRecoveryCard', [sessionId, cardId]),
  endSession: (sessionId) => invokeBackend('endSession', [sessionId]),
  readProfessorSummary: (sessionId) => invokeBackend('readProfessorSummary', [sessionId]),
  readProfessorMetrics: (sessionId) => invokeBackend('readProfessorMetrics', [sessionId]),
  readConsent: () => invokeBackend('readConsent', []),
  updateConsent: (request) => invokeBackend('updateConsent', [request]),
};

contextBridge.exposeInMainWorld('backend', backendApi);

const subscribe = <T>(
  channel: string,
  callback: (payload: T) => void,
): (() => void) => {
  const listener = (_event: Electron.IpcRendererEvent, payload: T): void => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

const bloomDesktop: BloomDesktopApi = {
  setRole: (role) => ipcRenderer.send('app:set-role', role),
  onZoomDetected: (callback) => subscribe('zoom:detected', callback),
  onZoomOverlayOpen: (callback) => subscribe('zoom:overlay-open', callback),
  subscribeSessionEvents: (sessionId) => ipcRenderer.send('session-events:subscribe', sessionId),
  onSessionEvent: (callback) => subscribe('session:event', callback),
  onSessionEventsConnection: (callback) => subscribe('session:events-connection', callback),
  overlayAction: (action) => ipcRenderer.send('overlay:action', { action }),
  showDriftPrompt: () => ipcRenderer.send('overlay:show-drift'),
  openZoomJoinLink: (joinUrl) =>
    ipcRenderer.invoke('zoom:open-join', joinUrl) as Promise<ZoomJoinOutcome>,
  getOverlayRole: () => {
    const role = new URLSearchParams(window.location.search).get('role');
    return role === 'professor' || role === 'student' ? role : null;
  },
};

contextBridge.exposeInMainWorld('bloomDesktop', bloomDesktop);
