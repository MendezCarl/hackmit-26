import { execFile } from 'node:child_process';
import { cp, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const root = process.cwd();
const dist = join(root, 'dist');
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';

await rm(dist, { recursive: true, force: true });
await execFileAsync(npx, ['tsc'], {
  cwd: root,
  shell: process.platform === 'win32',
});
await mkdir(dist, { recursive: true });
await cp(join(root, 'index.html'), join(dist, 'index.html'));
await cp(join(root, 'src', 'renderer', 'overlay.html'), join(dist, 'overlay.html'));
await cp(join(root, 'src', 'renderer', 'styles.css'), join(dist, 'styles.css'));
await cp(join(root, 'src', 'assets'), join(dist, 'assets'), { recursive: true });
await mkdir(join(dist, 'vendor', 'ort'), { recursive: true });
await cp(
  join(root, 'node_modules', 'onnxruntime-web', 'dist', 'ort.wasm.min.mjs'),
  join(dist, 'vendor', 'ort', 'ort.wasm.min.mjs'),
);
for (const file of [
  'ort-wasm-simd-threaded.mjs',
  'ort-wasm-simd-threaded.wasm',
  'ort-wasm-simd-threaded.asyncify.mjs',
  'ort-wasm-simd-threaded.asyncify.wasm',
  'ort-wasm-simd-threaded.jsep.mjs',
  'ort-wasm-simd-threaded.jsep.wasm',
  'ort-wasm-simd-threaded.jspi.mjs',
  'ort-wasm-simd-threaded.jspi.wasm',
]) {
  await cp(
    join(root, 'node_modules', 'onnxruntime-web', 'dist', file),
    join(dist, 'vendor', 'ort', file),
  );
}
await mkdir(join(dist, 'models'), { recursive: true });
await cp(join(root, 'models', 'person_detector.onnx'), join(dist, 'models', 'person_detector.onnx'));
await cp(
  join(root, 'models', 'person_detector.manifest.json'),
  join(dist, 'models', 'person_detector.manifest.json'),
);
