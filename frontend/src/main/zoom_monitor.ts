import { execFile } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const DEFAULT_POLL_MS = 5_000;
const COMMAND_TIMEOUT_MS = 4_000;

/**
 * Parses platform-specific process output into a Zoom running state.
 *
 * @param platform - Operating system process output format.
 * @param stdout - Process listing output.
 * @returns Whether a matching Zoom process appears to be running.
 */
export function parseZoomRunning(platform: NodeJS.Platform, stdout: string): boolean {
  if (platform === 'win32') return /zoom\.exe/i.test(stdout);
  if (platform === 'darwin') return Boolean(stdout.trim());
  return Boolean(stdout.trim());
}

type ZoomMonitorEvents = {
  change: (running: boolean) => void;
};

/**
 * Polls the local process table for a Zoom desktop process.
 *
 * @remarks Process names are used deliberately instead of an SDK or window
 * injection so all detection remains local and bounded to process metadata.
 */
export class ZoomProcessMonitor extends EventEmitter {
  private readonly platform: NodeJS.Platform;
  private readonly pollMs: number;
  private timer: NodeJS.Timeout | undefined;
  private running: boolean | undefined;

  /**
   * Creates a process monitor using the current platform and environment.
   *
   * @param platform - Platform override used by tests and platform adapters.
   * @param pollMs - Poll interval override in milliseconds.
   */
  constructor(
    platform: NodeJS.Platform = process.platform,
    pollMs = readPollInterval(),
  ) {
    super();
    this.platform = platform;
    this.pollMs = pollMs;
  }

  /**
   * Starts polling unless monitoring is disabled by configuration.
   *
   * @returns Nothing; changes are emitted through the `change` event.
   */
  start(): void {
    if (this.timer || this.isDisabled()) return;
    void this.poll();
    this.timer = setInterval(() => void this.poll(), this.pollMs);
  }

  /**
   * Stops polling and clears its timer.
   *
   * @returns Nothing.
   */
  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }

  /**
   * Narrows EventEmitter listeners to the monitor's public event.
   *
   * @param event - Event name.
   * @param listener - Transition callback.
   * @returns This monitor for chaining.
   */
  override on<K extends keyof ZoomMonitorEvents>(
    event: K,
    listener: ZoomMonitorEvents[K],
  ): this {
    return super.on(event, listener);
  }

  private isDisabled(): boolean {
    return (
      this.pollMs === 0 ||
      process.env.NODE_ENV === 'test' ||
      process.env.BLOOM_DISABLE_ZOOM_MONITOR === '1'
    );
  }

  private async poll(): Promise<void> {
    const stdout = await readProcessOutput(this.platform);
    if (stdout === null) return;
    const running = parseZoomRunning(this.platform, stdout);
    if (this.running === undefined) {
      this.running = running;
      if (running) this.emit('change', true);
      return;
    }
    if (running === this.running) return;
    this.running = running;
    this.emit('change', running);
  }
}

function readPollInterval(): number {
  const configured = Number(process.env.BLOOM_ZOOM_POLL_MS ?? DEFAULT_POLL_MS);
  return Number.isFinite(configured) && configured >= 0 ? configured : DEFAULT_POLL_MS;
}

async function readProcessOutput(platform: NodeJS.Platform): Promise<string | null> {
  const commands = processCommands(platform);
  let hadNoMatch = false;
  for (const [command, args] of commands) {
    try {
      const result = await execFileAsync(command, args, { timeout: COMMAND_TIMEOUT_MS });
      return result.stdout;
    } catch (error) {
      if (readExitCode(error) === 1) {
        hadNoMatch = true;
        continue;
      }
    }
  }
  return hadNoMatch ? '' : null;
}

function processCommands(platform: NodeJS.Platform): Array<[string, string[]]> {
  if (platform === 'win32') {
    return [['tasklist', ['/FI', 'IMAGENAME eq Zoom.exe', '/FO', 'CSV', '/NH']]];
  }
  if (platform === 'darwin') {
    return [
      ['pgrep', ['-x', 'zoom.us']],
      ['pgrep', ['-f', 'zoom.us.app']],
    ];
  }
  return [['pgrep', ['-x', 'zoom']]];
}

function readExitCode(error: unknown): number | undefined {
  if (!error || typeof error !== 'object' || !('code' in error)) return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === 'number' ? code : undefined;
}
