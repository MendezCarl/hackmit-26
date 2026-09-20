import { ipcMain } from 'electron/main';
import { BackendClient } from './backend_client.js';

type BackendOperationResult =
  { ok: true; value: unknown } | { ok: false; error: BackendRequestErrorShape };

/** Returns the configured backend origin, falling back to BackendClient defaults. */
function readBackendBaseUrl(): string | undefined {
  return process.env.BLOOM_BACKEND_URL?.trim() || undefined;
}

/** Registers one serialized IPC handler for each backend operation. */
export function registerBackendIpc(client = new BackendClient(readBackendBaseUrl())): void {
  const operations: Record<string, (...args: never[]) => Promise<unknown>> = {
    health: () => client.health(),
    apiStatus: () => client.apiStatus(),
    register: (request) => client.register(request),
    login: (request) => client.login(request),
    logout: () => client.logout(),
    readMe: () => client.readMe(),
    listCourses: () => client.listCourses(),
    createCourse: (request) => client.createCourse(request),
    listLectures: (courseId) => client.listLectures(courseId),
    createLecture: (request) => client.createLecture(request),
    createSession: (request) => client.createSession(request),
    readSession: (sessionId) => client.readSession(sessionId),
    resolveJoinCode: (joinCode) => client.resolveJoinCode(joinCode),
    joinSession: (sessionId) => client.joinSession(sessionId),
    updateAggregationConsent: (sessionId, consent) =>
      client.updateAggregationConsent(sessionId, consent),
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
