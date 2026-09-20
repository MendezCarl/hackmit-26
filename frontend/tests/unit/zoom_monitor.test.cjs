const assert = require('node:assert/strict');
const test = require('node:test');
const { access, readFile } = require('node:fs/promises');
const { join } = require('node:path');

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

test('readBackendBaseUrl uses the local override or hosted default', async () => {
  const moduleLoader = require('node:module');
  const originalLoad = moduleLoader._load;
  moduleLoader._load = function loadElectronMain(request, parent, isMain) {
    if (request === 'electron/main') return { ipcMain: { handle() {} } };
    return originalLoad.call(this, request, parent, isMain);
  };
  const previous = process.env.BLOOM_BACKEND_URL;
  try {
    const { DEFAULT_HOSTED_BACKEND_URL, readBackendBaseUrl } = await import(
      '../../dist/main/backend_ipc.js'
    );
    process.env.BLOOM_BACKEND_URL = ' https://backend.example.test ';
    assert.equal(readBackendBaseUrl(), 'https://backend.example.test');
    process.env.BLOOM_BACKEND_URL = '   ';
    assert.equal(readBackendBaseUrl(), DEFAULT_HOSTED_BACKEND_URL);
    delete process.env.BLOOM_BACKEND_URL;
    assert.equal(readBackendBaseUrl(), DEFAULT_HOSTED_BACKEND_URL);
  } finally {
    moduleLoader._load = originalLoad;
    if (previous === undefined) delete process.env.BLOOM_BACKEND_URL;
    else process.env.BLOOM_BACKEND_URL = previous;
  }
});

test('overlay HTML loads the emitted renderer module', async () => {
  const overlayHtml = await readFile(
    join(__dirname, '../../src/renderer/overlay.html'),
    'utf8',
  );
  assert.match(overlayHtml, /src="\.\/renderer\/overlay\.mjs"/);
});

test('build packages the ONNX runtime and approved detector', async () => {
  await access(join(__dirname, '../../dist/vendor/ort/ort-wasm-simd-threaded.wasm'));
  await access(join(__dirname, '../../dist/models/person_detector.onnx'));
});
