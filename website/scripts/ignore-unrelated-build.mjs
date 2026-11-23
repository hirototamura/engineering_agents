// Vercel skips preview builds when this command exits with zero.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

if (process.env.VERCEL_ENV !== 'preview') process.exit(1);

const previous = process.env.VERCEL_GIT_PREVIOUS_SHA ?? '';
if (!/^[a-f0-9]{40}$/i.test(previous)) {
  console.log('No usable previous successful deployment SHA; build preview.');
  process.exit(1);
}

const site = fileURLToPath(new URL('../', import.meta.url));
const { status } = spawnSync('git', [
  '-C', site, 'diff', '--quiet', '--no-ext-diff', previous, 'HEAD', '--', '.',
]);
if (status === 0) {
  console.log('Website matches the last successful deployment; skip preview build.');
  process.exit(0);
}

console.log(status === 1
  ? 'Website changed since the last successful deployment; build preview.'
  : 'Could not compare with the last successful deployment; build preview.');
process.exit(1);
