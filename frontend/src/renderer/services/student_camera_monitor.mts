import { recordSubmittedEvent } from './lecture_workspace.mjs';
import {
  DEFAULT_STUDENT_SIGNAL_POLICY,
  StudentSignalTracker,
  type StudentSignalPolicy,
} from './student_signal_tracker.mjs';
import { OnnxStudentFrameAnalyzer } from './student_frame_analyzer.mjs';

interface StudentCameraMonitorOptions {
  session: LectureSession;
  onEvents: (events: SignalEvent[]) => void;
  onError: (message: string) => void;
  policy?: StudentSignalPolicy;
}

type CameraMonitorState = {
  session: LectureSession;
  stream: MediaStream;
  video: HTMLVideoElement;
  analyzer: OnnxStudentFrameAnalyzer;
  tracker: StudentSignalTracker;
  timer: ReturnType<typeof setInterval>;
  tickInProgress: boolean;
  onEvents: (events: SignalEvent[]) => void;
  onError: (message: string) => void;
};

let activeMonitor: CameraMonitorState | null = null;
let stopPromise: Promise<void> | null = null;
let monitorStarting = false;

/**
 * Starts the singleton local camera monitor for one active lecture session.
 *
 * @param options - Session, local callbacks, and optional temporal policy.
 * @returns A promise resolved after camera and model initialization.
 */
export async function startStudentCameraMonitor(
  options: StudentCameraMonitorOptions,
): Promise<void> {
  if (activeMonitor || monitorStarting) return;
  monitorStarting = true;
  const policy = options.policy ?? DEFAULT_STUDENT_SIGNAL_POLICY;
  let stream: MediaStream | undefined;
  let analyzer: OnnxStudentFrameAnalyzer | undefined;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480 },
      audio: false,
    });
    analyzer = await OnnxStudentFrameAnalyzer.load(
      new URL('../../models/person_detector.onnx', import.meta.url).href,
      new URL('../../models/person_detector.manifest.json', import.meta.url).href,
    );
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.hidden = true;
    video.srcObject = stream;
    document.body.append(video);
    await video.play();
    const tracker = new StudentSignalTracker({
      sessionId: options.session.session_id,
      policy,
    });
    const state: CameraMonitorState = {
      session: options.session,
      stream,
      video,
      analyzer,
      tracker,
      timer: setInterval(() => {
        void analyzeTick(state);
      }, policy.samplingMs),
      tickInProgress: false,
      onEvents: options.onEvents,
      onError: options.onError,
    };
    activeMonitor = state;
    stream.getVideoTracks().forEach((track) => {
      track.addEventListener('ended', () => {
        tracker.unavailable();
        void stopStudentCameraMonitor().finally(() => {
          options.onError('Camera monitoring stopped because the camera is no longer available.');
        });
      });
    });
    monitorStarting = false;
  } catch (error) {
    stream?.getTracks().forEach((track) => track.stop());
    analyzer?.dispose();
    monitorStarting = false;
    options.onError(cameraErrorMessage(error));
    throw error;
  }
}

/**
 * Stops local capture, releases the model, and posts any sustained final event.
 *
 * @returns A promise resolved after local resources and flushed events are handled.
 */
export async function stopStudentCameraMonitor(): Promise<void> {
  if (stopPromise) return stopPromise;
  const state = activeMonitor;
  activeMonitor = null;
  if (!state) return;
  stopPromise = (async () => {
    clearInterval(state.timer);
    state.stream.getTracks().forEach((track) => track.stop());
    state.video.pause();
    state.video.srcObject = null;
    state.video.remove();
    state.analyzer.dispose();
    const endMs = Date.now() - Date.parse(state.session.session_clock_origin);
    const events = state.tracker.flush(Number.isFinite(endMs) ? endMs : 0);
    await postEvents(state, events, { notify: false });
  })().finally(() => {
    stopPromise = null;
  });
  return stopPromise;
}

async function analyzeTick(state: CameraMonitorState): Promise<void> {
  if (state !== activeMonitor || state.tickInProgress || state.video.readyState < 2) return;
  state.tickInProgress = true;
  try {
    const width = state.video.videoWidth;
    const height = state.video.videoHeight;
    const observation = await state.analyzer.analyze(state.video, width, height);
    const lectureTimeMs = Date.now() - Date.parse(state.session.session_clock_origin);
    const events = state.tracker.observe(observation, lectureTimeMs);
    await postEvents(state, events);
  } catch (error) {
    state.tracker.unavailable();
    await stopStudentCameraMonitor();
    state.onError(cameraErrorMessage(error));
  } finally {
    state.tickInProgress = false;
  }
}

/**
 * Posts derived signal events and optionally surfaces them to the UI.
 *
 * Shutdown flushes still post so the interval is recorded, but they never prompt: the
 * student has already left the session or turned the camera off.
 */
async function postEvents(
  state: CameraMonitorState,
  events: SignalEvent[],
  { notify }: { notify: boolean } = { notify: true },
): Promise<void> {
  for (const event of events) {
    await window.backend.ingestEvents(state.session.session_id, {
      lecture_id: state.session.lecture_id,
      events: [event],
    });
    recordSubmittedEvent(event);
    if (notify) state.onEvents([event]);
  }
}

function cameraErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Camera permission was not granted.';
  }
  if (error instanceof Error && error.message) return error.message;
  return 'Camera monitoring is unavailable on this device.';
}
