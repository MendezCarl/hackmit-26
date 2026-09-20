/** Main-process HTTP client for the local Bloom FastAPI service. */

export type BackendRequestOptions = {
  body?: unknown;
  query?: Record<string, string>;
  headers?: Record<string, string>;
};

/** Structured error returned by the backend API boundary. */
export class BackendRequestError extends Error {
  readonly status: number;
  readonly code: string;

  /** @param status - HTTP status. @param code - Stable backend code. @param message - Safe message. */
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'BackendRequestError';
    this.status = status;
    this.code = code;
  }
}

/** Performs authenticated requests to the local FastAPI backend. */
export class BackendClient {
  private accessToken: string | null = null;

  /** @param baseUrl - Backend origin used for requests. */
  constructor(private readonly baseUrl = 'http://127.0.0.1:8000') {}

  /**
   * Sends one JSON request and maps backend errors to a typed exception.
   * @param method - HTTP method. @param path - API path. @param options - Optional request data.
   * @returns Parsed JSON response. @throws BackendRequestError for non-2xx responses.
   */
  async request<T>(method: string, path: string, options: BackendRequestOptions = {}): Promise<T> {
    const url = new URL(path, this.baseUrl);
    Object.entries(options.query ?? {}).forEach(([key, value]) => url.searchParams.set(key, value));
    const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (this.accessToken) headers.Authorization = `Bearer ${this.accessToken}`;
    const response = await fetch(url, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const text = await response.text();
    let payload: unknown;
    if (text) {
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        payload = undefined;
      }
    }
    if (!response.ok) {
      const errorResponse = payload as ErrorResponse | undefined;
      throw new BackendRequestError(
        response.status,
        errorResponse?.error?.code ?? 'request_failed',
        errorResponse?.error?.message ?? `Backend request failed with status ${response.status}.`,
      );
    }
    return payload as T;
  }

  async health(): Promise<BackendHealth> {
    return this.request('GET', '/health');
  }
  async apiStatus(): Promise<BackendStatus> {
    return this.request('GET', '/api/status');
  }

  async readApiStatus(): Promise<BackendStatus> {
    return this.apiStatus();
  }
  async register(request: RegisterUserRequest): Promise<AuthSession> {
    const result = await this.request<AuthSession>('POST', '/api/v1/auth/register', {
      body: request,
    });
    this.accessToken = result.access_token;
    return result;
  }
  async login(request: LoginRequest): Promise<AuthSession> {
    const result = await this.request<AuthSession>('POST', '/api/v1/auth/login', { body: request });
    this.accessToken = result.access_token;
    return result;
  }
  async logout(): Promise<void> {
    this.accessToken = null;
  }
  async readMe(): Promise<UserProfile> {
    return this.request('GET', '/api/v1/users/me');
  }
  async listCourses(): Promise<Course[]> {
    return this.request('GET', '/api/v1/courses');
  }
  async createCourse(request: CreateCourseRequest): Promise<Course> {
    return this.request('POST', '/api/v1/courses', { body: request });
  }
  async listLectures(courseId: string): Promise<Lecture[]> {
    return this.request('GET', '/api/v1/lectures', { query: { course_id: courseId } });
  }
  async createLecture(request: CreateLectureRequest): Promise<Lecture> {
    return this.request('POST', '/api/v1/lectures', { body: request });
  }
  async createSession(request: CreateSessionRequest): Promise<LectureSession> {
    return this.request('POST', '/api/v1/sessions', { body: request });
  }
  async listSessions(filter: SessionListFilter = {}): Promise<LectureSession[]> {
    const query: Record<string, string> = {};
    if (filter.lecture_id !== undefined) query.lecture_id = filter.lecture_id;
    if (filter.course_id !== undefined) query.course_id = filter.course_id;
    return this.request('GET', '/api/v1/sessions', { query });
  }
  async readSession(sessionId: string): Promise<LectureSession> {
    return this.request('GET', `/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  }
  async resolveJoinCode(joinCode: string): Promise<LectureSession> {
    return this.request(
      'GET',
      `/api/v1/sessions/by-join-code/${encodeURIComponent(joinCode)}`,
    );
  }
  async joinSession(sessionId: string): Promise<ParticipantResponse> {
    return this.request('POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/participants`);
  }
  async listEnrollments(): Promise<CourseEnrollment[]> {
    return this.request('GET', '/api/v1/enrollments');
  }
  async enrollInCourse(request: EnrollCourseRequest): Promise<CourseEnrollment> {
    return this.request('POST', '/api/v1/enrollments', { body: request });
  }
  async updateEnrollment(
    enrollmentId: string,
    request: UpdateEnrollmentRequest,
  ): Promise<CourseEnrollment> {
    return this.request('PATCH', `/api/v1/enrollments/${encodeURIComponent(enrollmentId)}`, {
      body: request,
    });
  }
  async leaveCourse(enrollmentId: string): Promise<void> {
    await this.request('DELETE', `/api/v1/enrollments/${encodeURIComponent(enrollmentId)}`);
  }
  /**
   * Lists live sessions the student can join without a code.
   * @param zoomMeetingId - Zoom meeting id detected on this device, when known.
   * @returns Active sessions matched by enrollment or Zoom meeting, newest first.
   */
  async listAvailableSessions(
    zoomMeetingId: string | null = null,
  ): Promise<AvailableLectureSession[]> {
    const query: Record<string, string> = {};
    if (zoomMeetingId) query.zoom_meeting_id = zoomMeetingId;
    return this.request('GET', '/api/v1/sessions/available', { query });
  }
  async updateAggregationConsent(
    sessionId: string,
    consent: AggregationConsent,
  ): Promise<AggregationConsent> {
    return this.request(
      'PUT',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/aggregation-consent`,
      { body: consent },
    );
  }

  async updateExternalTextConsent(
    sessionId: string,
    consent: ExternalTextConsent,
  ): Promise<ExternalTextConsent> {
    return this.request(
      'PUT',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/external-text-consent`,
      { body: consent },
    );
  }
  async ingestEvents(sessionId: string, request: IngestEventsRequest): Promise<EventBatchResponse> {
    return this.request('POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/events/batch`, {
      body: request,
    });
  }
  async ingestTranscript(
    sessionId: string,
    request: IngestTranscriptRequest,
  ): Promise<TranscriptBatchResponse> {
    return this.request(
      'POST',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/transcript-chunks/batch`,
      { body: request },
    );
  }
  async readTranscript(
    sessionId: string,
    startMs: number,
    endMs: number,
  ): Promise<TranscriptWindowResponse> {
    return this.request('GET', `/api/v1/sessions/${encodeURIComponent(sessionId)}/transcript`, {
      query: { start_ms: String(startMs), end_ms: String(endMs) },
    });
  }
  async startZoomRtms(sessionId: string, request: StartZoomRtmsRequest): Promise<ZoomRtmsStatus> {
    return this.request(
      'POST',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/zoom/rtms/start`,
      { body: request },
    );
  }
  async readZoomStatus(sessionId: string): Promise<ZoomRtmsStatus> {
    return this.request('GET', `/api/v1/sessions/${encodeURIComponent(sessionId)}/zoom/status`);
  }
  /**
   * Builds the authenticated WebSocket URL for one session's event stream.
   *
   * The bearer token stays in the main process; the renderer only receives
   * decoded envelopes through IPC.
   *
   * @param sessionId - Session whose events should be streamed.
   * @returns Absolute `ws://` or `wss://` URL, or null when not logged in.
   */
  buildSessionEventsUrl(sessionId: string): string | null {
    if (!this.accessToken) return null;
    const url = new URL(`/ws/v1/sessions/${encodeURIComponent(sessionId)}`, this.baseUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('token', this.accessToken);
    return url.toString();
  }
  async requestRecoveryCard(
    sessionId: string,
    request: CreateRecoveryJobRequest,
    idempotencyKey?: string,
  ): Promise<RecoveryJob> {
    return this.request(
      'POST',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/recovery-cards`,
      {
        body: request,
        headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      },
    );
  }
  async readRecoveryCard(sessionId: string, cardId: string): Promise<RecoveryCard> {
    return this.request(
      'GET',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/recovery-cards/${encodeURIComponent(cardId)}`,
    );
  }
  async endSession(sessionId: string): Promise<LectureSession> {
    return this.request('POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/end`);
  }
  async readProfessorSummary(sessionId: string): Promise<ProfessorSummary> {
    return this.request(
      'GET',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/professor/summary`,
    );
  }
  async readProfessorMetrics(sessionId: string): Promise<ProfessorMetrics> {
    return this.request(
      'GET',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/professor-metrics`,
    );
  }
  /** Generates teaching moments on explicit professor request; never called automatically. */
  async generateProfessorRecommendations(sessionId: string): Promise<RecommendationReport> {
    return this.request(
      'POST',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/professor-recommendations`,
    );
  }
  async reviewProfessorRecommendation(
    sessionId: string,
    review: RecommendationReview,
  ): Promise<RecommendationReview> {
    return this.request(
      'PUT',
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/professor-recommendations/reviews`,
      { body: review },
    );
  }
  async readConsent(): Promise<ConsentSettings> {
    return this.request('GET', '/api/v1/users/me/consent');
  }
  async updateConsent(request: UpdateConsentRequest): Promise<ConsentSettings> {
    return this.request('PUT', '/api/v1/users/me/consent', { body: request });
  }
}
