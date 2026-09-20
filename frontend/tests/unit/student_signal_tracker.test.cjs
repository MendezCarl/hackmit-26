const assert = require('node:assert/strict');
const test = require('node:test');

test('phone observations sustained for five seconds emit one grounded event', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0.8 }, 0);
  tracker.observe({ personScore: 1, phoneScore: 0.6 }, 2000);
  tracker.observe({ personScore: 1, phoneScore: 0.7 }, 4000);
  const events = tracker.observe({ personScore: 1, phoneScore: 0.1 }, 6000);
  assert.equal(events.length, 1);
  assert.equal(events[0].event_type, 'phone_visible');
  assert.equal(events[0].start_ms, 0);
  assert.equal(events[0].end_ms, 6000);
  assert.ok(Math.abs(events[0].confidence - 0.7) < 1e-6);
  assert.deepEqual(events[0].signals, ['phone_visible']);
});

test('a person absent for only three seconds emits no event', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 0, phoneScore: 0 }, 0);
  assert.deepEqual(tracker.observe({ personScore: 1, phoneScore: 0 }, 3001), []);
});

test('a gap greater than two seconds clears active candidates', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0.9 }, 0);
  tracker.observe({ personScore: 1, phoneScore: 0.9 }, 2500);
  assert.deepEqual(tracker.observe({ personScore: 1, phoneScore: 0 }, 3000), []);
});

test('samples closer than the sampling interval are ignored', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0.8 }, 0);
  tracker.observe({ personScore: 1, phoneScore: 0 }, 100);
  assert.deepEqual(tracker.observe({ personScore: 1, phoneScore: 0 }, 334), []);
});

test('non-monotonic timestamps throw', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0 }, 1000);
  assert.throws(() => tracker.observe({ personScore: 1, phoneScore: 0 }, 999));
});

test('flush closes an open candidate', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0.75 }, 0);
  tracker.observe({ personScore: 1, phoneScore: 0.75 }, 2000);
  tracker.observe({ personScore: 1, phoneScore: 0.75 }, 4000);
  const events = tracker.flush(6000);
  assert.equal(events.length, 1);
  assert.equal(events[0].end_ms, 6000);
});

test('unavailable clears candidates without emitting events', async () => {
  const { StudentSignalTracker } = await import('../../dist/renderer/services/student_signal_tracker.mjs');
  const tracker = new StudentSignalTracker({ sessionId: 'session-1' });
  tracker.observe({ personScore: 1, phoneScore: 0.75 }, 0);
  tracker.unavailable();
  assert.deepEqual(tracker.flush(6000), []);
});
