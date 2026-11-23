// Vercel ignores a deployment when this command returns zero.
// Always build production and fail open when git history is unavailable.
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

if (process.env.VERCEL_ENV !== 'preview') process.exit(1);
const site = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const result = spawnSync('git', ['-C', site, 'diff', '--quiet', 'HEAD^', 'HEAD', '--', '.'], { stdio: 'inherit' });
if (result.status === 0) {
  console.log('No website changes in this commit; skip preview build.');
  process.exit(0);
}
console.log('Website changed or git history unavailable; build preview.');
process.exit(1);
