/**
 * These handwritten types mirror docs/api/openapi.json. Update this file with
 * the checked-in OpenAPI contract whenever the backend schemas change.
 */
type SessionMode = 'zoom' | 'in_person';
type SessionStatus = 'created' | 'active' | 'ending' | 'ended' | 'failed';
type TranscriptSource = 'zoom_rtms' | 'local_transcription' | 'external_transcription';
type JobStatus = 'queued' | 'running' | 'completed' | 'failed';
interface UserProfile {
  user_id: string;
  email: string;
  role: string;
  display_name: string;
  created_at: string;
}
interface AuthSession {
  user: UserProfile;
  access_token: string;
  token_type?: string;
}
interface RegisterUserRequest {
  email: string;
  password: string;
  display_name: string;
  role: 'student' | 'professor';
}
interface LoginRequest {
  email: string;
  password: string;
}
interface Course {
  course_id: string;
  owner_id: string;
  title: string;
  code: string;
  created_at: string;
}
interface CreateCourseRequest {
  title: string;
  code?: string | null;
}
interface Lecture {
  lecture_id: string;
  course_id: string;
  owner_id: string;
  title: string;
  created_at: string;
}
interface CreateLectureRequest {
  course_id: string;
  title: string;
}
interface LectureSession {
  session_id: string;
  lecture_id: string;
  owner_id: string;
  course_id: string;
  title: string;
  join_code: string;
  mode: SessionMode;
  status: SessionStatus;
  started_at: string;
  ended_at?: string | null;
  session_clock_origin: string;
  zoom_meeting_id?: string | null;
}
interface CreateSessionRequest {
  lecture_id: string;
  course_id: string;
  title: string;
  mode: SessionMode;
  zoom_meeting_id?: string | null;
}
interface SessionListFilter {
  lecture_id?: string;
  course_id?: string;
}
interface ParticipantResponse {
  session_id: string;
  user_id: string;
  participant_count: number;
}
interface AggregationConsent {
  is_allowed: boolean;
}
interface SignalEvent {
  event_id: string;
  session_id: string;
  event_type: string;
  start_ms: number;
  end_ms: number;
  signals?: string[];
  confidence: number;
  user_confirmed?: boolean | null;
  client_generated_at?: string | null;
}
interface IngestEventsRequest {
  lecture_id: string;
  events: SignalEvent[];
}
interface EventBatchResponse {
  session_id: string;
  accepted_event_ids: string[];
  recovery_eligible_event_ids: string[];
}
interface TranscriptChunk {
  chunk_id: string;
  session_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  speaker_label?: string | null;
  source: TranscriptSource;
  is_final?: boolean;
  revision?: number;
}
interface IngestTranscriptRequest {
  lecture_id: string;
  chunks: TranscriptChunk[];
}
interface TranscriptBatchResponse {
  session_id: string;
  accepted_chunk_ids: string[];
  superseded_chunk_ids: string[];
  transcript_revision: number;
}
interface TranscriptWindowResponse {
  session_id: string;
  start_ms: number;
  end_ms: number;
  transcript_revision: number;
  chunks: TranscriptChunk[];
}
interface CreateRecoveryJobRequest {
  start_ms: number;
  end_ms: number;
  source_event_ids?: string[];
}
interface RecoveryJob {
  job_id: string;
  session_id: string;
  status: JobStatus;
  requested_start_ms: number;
  requested_end_ms: number;
  card_id?: string | null;
  failure?: { reason: string; message: string } | null;
  cache_status?: 'miss' | 'hit' | null;
  created_at: string;
  completed_at?: string | null;
}
interface SourceTimestamp {
  start_ms: number;
  end_ms: number;
  chunk_id?: string | null;
  source?: string | null;
}
interface ModelMetadata {
  provider: string;
  model: string;
  provider_mode: 'mock' | 'live';
  data_label?: 'synthetic' | 'measured';
  prompt_version: string;
  output_schema_version: string;
  input_character_count: number;
  output_character_count: number;
  input_token_count?: number | null;
  output_token_count?: number | null;
  latency_ms: number;
}
interface RecoveryCard {
  card_id: string;
  session_id: string;
  source_event_ids: string[];
  topic: string;
  what_you_missed: string;
  key_facts: string[];
  example_from_lecture?: string | null;
  source_timestamps: SourceTimestamp[];
  follow_up_question: string;
  model_metadata: ModelMetadata;
  created_at: string;
}
interface TimelineBucket {
  start_ms: number;
  end_ms: number;
  event_count: number;
}
interface SignalIntervalAggregate {
  start_ms: number;
  end_ms: number;
  event_count: number;
  dominant_event_types: string[];
}
interface ProfessorSummary {
  summary_id: string;
  session_id: string;
  participant_count: number;
  minimum_group_size: number;
  aggregation_window_ms: number;
  is_suppressed: boolean;
  timeline_buckets?: TimelineBucket[] | null;
  highest_signal_intervals?: SignalIntervalAggregate[] | null;
  suggested_actions?: string[] | null;
  generated_at: string;
}
interface ProfessorMetrics {
  session_id: string;
  policy_version: string;
  status: 'available' | 'suppressed' | 'insufficient_evidence';
  minimum_group_size: number;
  bucket_ms: number;
  buckets: Array<{
    start_ms: number;
    end_ms: number;
    status: 'available' | 'suppressed' | 'insufficient_evidence';
    coverage?: { numerator: number; denominator: number; ratio: number } | null;
    possible_missed?: { numerator: number; denominator: number; ratio: number } | null;
    is_hotspot?: boolean | null;
    transcript_chunk_ids: string[];
    suggested_action?: string | null;
  }>;
  continuity?: { numerator: number; denominator: number; ratio: number } | null;
  delivery_findings: Array<{
    start_ms: number;
    end_ms: number;
    signal_type: string;
    confidence: number;
    suggested_action: string;
  }>;
  recovery_outcomes_status: 'not_collected';
}
interface ConsentSettings {
  analytics_opt_in?: boolean;
  updated_at?: string | null;
}
interface UpdateConsentRequest {
  analytics_opt_in: boolean;
}
interface BackendHealth {
  status: string;
}
interface BackendStatus {
  message: string;
}
interface ErrorResponse {
  error: { code: string; message: string; details?: Record<string, unknown> | null };
}
interface BackendRequestErrorShape {
  status: number;
  code: string;
  message: string;
}
type BackendApi = {
  health: () => Promise<BackendHealth>;
  apiStatus: () => Promise<BackendStatus>;
  register: (request: RegisterUserRequest) => Promise<AuthSession>;
  login: (request: LoginRequest) => Promise<AuthSession>;
  logout: () => Promise<void>;
  readMe: () => Promise<UserProfile>;
  listCourses: () => Promise<Course[]>;
  createCourse: (request: CreateCourseRequest) => Promise<Course>;
  listLectures: (courseId: string) => Promise<Lecture[]>;
  createLecture: (request: CreateLectureRequest) => Promise<Lecture>;
  createSession: (request: CreateSessionRequest) => Promise<LectureSession>;
  listSessions: (filter?: SessionListFilter) => Promise<LectureSession[]>;
  readSession: (sessionId: string) => Promise<LectureSession>;
  resolveJoinCode: (joinCode: string) => Promise<LectureSession>;
  joinSession: (sessionId: string) => Promise<ParticipantResponse>;
  updateAggregationConsent: (
    sessionId: string,
    consent: AggregationConsent,
  ) => Promise<AggregationConsent>;
  ingestEvents: (sessionId: string, request: IngestEventsRequest) => Promise<EventBatchResponse>;
  ingestTranscript: (
    sessionId: string,
    request: IngestTranscriptRequest,
  ) => Promise<TranscriptBatchResponse>;
  readTranscript: (
    sessionId: string,
    startMs: number,
    endMs: number,
  ) => Promise<TranscriptWindowResponse>;
  requestRecoveryCard: (
    sessionId: string,
    request: CreateRecoveryJobRequest,
    idempotencyKey?: string,
  ) => Promise<RecoveryJob>;
  readRecoveryCard: (sessionId: string, cardId: string) => Promise<RecoveryCard>;
  endSession: (sessionId: string) => Promise<LectureSession>;
  readProfessorSummary: (sessionId: string) => Promise<ProfessorSummary>;
  readProfessorMetrics: (sessionId: string) => Promise<ProfessorMetrics>;
  readConsent: () => Promise<ConsentSettings>;
  updateConsent: (request: UpdateConsentRequest) => Promise<ConsentSettings>;
};
type BloomRole = 'professor' | 'student' | null;
interface ZoomDetectedPayload {
  running: boolean;
}
interface BloomDesktopApi {
  setRole: (role: BloomRole) => void;
  onZoomDetected: (callback: (payload: ZoomDetectedPayload) => void) => () => void;
  onZoomOverlayOpen: (callback: () => void) => () => void;
  overlayAction: (action: 'open' | 'dismiss') => void;
  getOverlayRole: () => BloomRole;
}
interface Window {
  backend: BackendApi;
  bloomDesktop: BloomDesktopApi;
}
