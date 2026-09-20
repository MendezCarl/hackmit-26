import { execFile } from 'node:child_process';
import { cp, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const root = process.cwd();
const dist = join(root, 'dist');
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';

await rm(dist, { recursive: true, force: true });
await execFileAsync(npx, ['tsc'], { cwd: root });
await mkdir(dist, { recursive: true });
await cp(join(root, 'index.html'), join(dist, 'index.html'));
await cp(join(root, 'src', 'renderer', 'overlay.html'), join(dist, 'overlay.html'));
await cp(join(root, 'src', 'renderer', 'styles.css'), join(dist, 'styles.css'));
await cp(join(root, 'src', 'assets'), join(dist, 'assets'), { recursive: true });
