const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const test = require('node:test');

const dataUrl = (value) => `data:application/json,${encodeURIComponent(value)}`;

test('toInputTensor uses RGB NCHW order and scales values', async () => {
  const { toInputTensor } = await import('../../dist/renderer/services/student_frame_analyzer.mjs');
  const tensor = toInputTensor({
    width: 2,
    height: 1,
    data: [255, 128, 0, 255, 0, 64, 255, 255],
  });
  assert.deepEqual(
    Array.from(tensor).map((value) => Number(value.toFixed(6))),
    [1, 0, 0.501961, 0.25098, 0, 1],
  );
});

test('bestScore selects only the requested finite class score', async () => {
  const { bestScore } = await import('../../dist/renderer/services/student_frame_analyzer.mjs');
  assert.equal(
    bestScore(
      [
        [0, 0, 1, 1, 0.4, 77],
        [0, 0, 1, 1, 0.9, 1],
        [0, 0, 1, 1, 0.7, 77],
      ],
      77,
    ),
    0.7,
  );
});

test('body crops use padded normalized person bounds', async () => {
  const { bodyCropRects } = await import('../../dist/renderer/services/student_frame_analyzer.mjs');
  const rects = bodyCropRects([[0.25, 0.1, 0.75, 0.9, 0.8, 1]], 640, 480);
  assert.equal(rects.length, 3);
  assert.deepEqual(rects[0], { left: 112, top: 182, width: 416, height: 250 });
});

test('load rejects an unapproved manifest and digest mismatch', async () => {
  const { OnnxStudentFrameAnalyzer } = await import(
    '../../dist/renderer/services/student_frame_analyzer.mjs'
  );
  const modelBytes = Uint8Array.from([1, 2, 3]);
  const modelUrl = `data:application/octet-stream;base64,${Buffer.from(modelBytes).toString('base64')}`;
  const unapprovedManifest = dataUrl(
    JSON.stringify({ sha256: '00', is_approved: false, input_size: 320 }),
  );
  await assert.rejects(
    OnnxStudentFrameAnalyzer.load(modelUrl, unapprovedManifest, async () => {
      throw new Error('session factory should not run');
    }),
    /not approved/,
  );
  const wrongHashManifest = dataUrl(
    JSON.stringify({ sha256: '00', is_approved: true, input_size: 320 }),
  );
  await assert.rejects(
    OnnxStudentFrameAnalyzer.load(modelUrl, wrongHashManifest, async () => {
      throw new Error('session factory should not run');
    }),
    /digest does not match/,
  );
});

test('load accepts a verified manifest with an injectable session factory', async () => {
  const { OnnxStudentFrameAnalyzer } = await import(
    '../../dist/renderer/services/student_frame_analyzer.mjs'
  );
  const modelBytes = Uint8Array.from([4, 5, 6]);
  const hash = createHash('sha256').update(modelBytes).digest('hex');
  const modelUrl = `data:application/octet-stream;base64,${Buffer.from(modelBytes).toString('base64')}`;
  const manifestUrl = dataUrl(
    JSON.stringify({ sha256: hash, is_approved: true, input_size: 320 }),
  );
  global.document = {
    createElement: () => ({
      getContext: () => ({
        getImageData: () => ({ data: [], width: 320, height: 320 }),
      }),
    }),
  };
  const session = {
    inputNames: ['image'],
    outputNames: ['detections'],
    release: () => Promise.resolve(),
  };
  const analyzer = await OnnxStudentFrameAnalyzer.load(modelUrl, manifestUrl, async () => session);
  assert.ok(analyzer);
  analyzer.dispose();
  delete global.document;
});
