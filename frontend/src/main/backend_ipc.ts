import { ipcMain } from 'electron/main';
import { BackendClient } from './backend_client.js';

type BackendOperationResult =
  { ok: true; value: unknown } | { ok: false; error: BackendRequestErrorShape };

export const DEFAULT_HOSTED_BACKEND_URL = 'https://bloom-backend-srdd.onrender.com';

/**
 * Returns the configured backend origin.
 *
 * `BLOOM_BACKEND_URL` is an override for local backend development.
 *
 * @returns The `BLOOM_BACKEND_URL` override or the hosted Render backend URL.
 */
export function readBackendBaseUrl(): string {
  return process.env.BLOOM_BACKEND_URL?.trim() || DEFAULT_HOSTED_BACKEND_URL;
}

/** Registers one serialized IPC handler for each backend operation. */
export function registerBackendIpc(client = new BackendClient(readBackendBaseUrl())): void {
  const operations: Record<string, (...args: never[]) => Promise<unknown>> = {
    health: () => client.health(),
    apiStatus: () => client.apiStatus(),
    readApiStatus: () => client.readApiStatus(),
    register: (request) => client.register(request),
    login: (request) => client.login(request),
    logout: () => client.logout(),
    readMe: () => client.readMe(),
    listCourses: () => client.listCourses(),
    createCourse: (request) => client.createCourse(request),
    listLectures: (courseId) => client.listLectures(courseId),
    createLecture: (request) => client.createLecture(request),
    createSession: (request) => client.createSession(request),
    listSessions: (filter) => client.listSessions(filter),
    readSession: (sessionId) => client.readSession(sessionId),
    resolveJoinCode: (joinCode) => client.resolveJoinCode(joinCode),
    joinSession: (sessionId) => client.joinSession(sessionId),
    listEnrollments: () => client.listEnrollments(),
    enrollInCourse: (request) => client.enrollInCourse(request),
    updateEnrollment: (enrollmentId, request) => client.updateEnrollment(enrollmentId, request),
    leaveCourse: (enrollmentId) => client.leaveCourse(enrollmentId),
    listAvailableSessions: (zoomMeetingId) => client.listAvailableSessions(zoomMeetingId),
    updateAggregationConsent: (sessionId, consent) =>
      client.updateAggregationConsent(sessionId, consent),
    updateExternalTextConsent: (sessionId, consent) =>
      client.updateExternalTextConsent(sessionId, consent),
    ingestEvents: (sessionId, request) => client.ingestEvents(sessionId, request),
    ingestTranscript: (sessionId, request) => client.ingestTranscript(sessionId, request),
    readTranscript: (sessionId, startMs, endMs) => client.readTranscript(sessionId, startMs, endMs),
    requestRecoveryCard: (sessionId, request, key) =>
      client.requestRecoveryCard(sessionId, request, key),
    readRecoveryCard: (sessionId, cardId) => client.readRecoveryCard(sessionId, cardId),
    endSession: (sessionId) => client.endSession(sessionId),
    readProfessorSummary: (sessionId) => client.readProfessorSummary(sessionId),
    readProfessorMetrics: (sessionId) => client.readProfessorMetrics(sessionId),
    readConsent: () => client.readConsent(),
    updateConsent: (request) => client.updateConsent(request),
  };
  Object.entries(operations).forEach(([operation, handler]) => {
    ipcMain.handle(
      `backend:${operation}`,
      async (_event, ...args: unknown[]): Promise<BackendOperationResult> => {
        try {
          return { ok: true, value: await handler(...(args as never[])) };
        } catch (error) {
          const typed = error as Partial<BackendRequestErrorShape>;
          return {
            ok: false,
            error: {
              status: typeof typed.status === 'number' ? typed.status : 500,
              code: typeof typed.code === 'string' ? typed.code : 'request_failed',
              message: error instanceof Error ? error.message : 'Backend request failed.',
            },
          };
        }
      },
    );
  });
}
