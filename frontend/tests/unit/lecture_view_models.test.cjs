const assert = require('node:assert/strict');
const test = require('node:test');

test('lecture view models format timestamps and preserve recovery language', async () => {
  const { buildMomentsFromEvents, buildMomentsFromSummary, formatLectureTime, sessionDurationMs } = await import('../../dist/renderer/services/lecture_view_models.mjs');
  assert.equal(formatLectureTime(125000), '02:05');
  const event = { event_id: 'event-1', session_id: 'session-1', event_type: 'possible_missed_window', start_ms: 30000, end_ms: 60000, confidence: 1 };
  assert.match(buildMomentsFromEvents([event], 120000)[0].title, /Possible missed-content moment/);
  const summary = { highest_signal_intervals: [{ start_ms: 30000, end_ms: 60000, event_count: 4, dominant_event_types: ['possible_missed_window'] }] };
  assert.match(buildMomentsFromSummary(summary, 120000)[0].evidence, /4 anonymous recovery signals/);
  assert.equal(sessionDurationMs({ session_clock_origin: '2026-01-01T00:00:00.000Z', started_at: '2026-01-01T00:00:00.000Z', ended_at: '2026-01-01T00:01:00.000Z' }), 60000);
});
