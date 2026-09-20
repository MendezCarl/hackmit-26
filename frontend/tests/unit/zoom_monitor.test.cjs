const assert = require('node:assert/strict');
const test = require('node:test');

test('parseZoomRunning detects Zoom.exe in Windows CSV output', async () => {
  const { parseZoomRunning } = await import('../../dist/main/zoom_monitor.js');
  assert.equal(parseZoomRunning('win32', '"Zoom.exe","1234","Console","1","42,000 K"'), true);
});

test('parseZoomRunning ignores other Windows processes', async () => {
  const { parseZoomRunning } = await import('../../dist/main/zoom_monitor.js');
  assert.equal(parseZoomRunning('win32', '"Teams.exe","1234","Console","1","42,000 K"'), false);
});

test('parseZoomRunning detects macOS PID output', async () => {
  const { parseZoomRunning } = await import('../../dist/main/zoom_monitor.js');
  assert.equal(parseZoomRunning('darwin', '1234\n'), true);
});

test('parseZoomRunning detects Linux PID output', async () => {
  const { parseZoomRunning } = await import('../../dist/main/zoom_monitor.js');
  assert.equal(parseZoomRunning('linux', '4321\n'), true);
});

test('parseZoomRunning treats empty output as not running', async () => {
  const { parseZoomRunning } = await import('../../dist/main/zoom_monitor.js');
  assert.equal(parseZoomRunning('linux', ''), false);
});
