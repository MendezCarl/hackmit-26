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
  updateAggregationConsent: (sessionId, consent) =>
    invokeBackend('updateAggregationConsent', [sessionId, consent]),
  ingestEvents: (sessionId, request) => invokeBackend('ingestEvents', [sessionId, request]),
  ingestTranscript: (sessionId, request) => invokeBackend('ingestTranscript', [sessionId, request]),
  readTranscript: (sessionId, startMs, endMs) =>
    invokeBackend('readTranscript', [sessionId, startMs, endMs]),
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
