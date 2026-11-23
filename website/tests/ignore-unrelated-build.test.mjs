import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const script = resolve('scripts/ignore-unrelated-build.mjs');
test('skip unrelated preview commits, but build website, production, and unknown history', () => {
  const root = mkdtempSync(join(tmpdir(), 'vercel-ignore-'));
  const git = (...args) => execFileSync('git', ['-C', root, ...args], { stdio: 'ignore' });
  const run = env => spawnSync(process.execPath, [join(root, 'website/scripts/ignore-unrelated-build.mjs')], { env: {...process.env, VERCEL_ENV: env} }).status;
  try {
    git('init', '-q'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid');
    mkdirSync(join(root, 'website/scripts'), {recursive:true}); copyFileSync(script, join(root, 'website/scripts/ignore-unrelated-build.mjs'));
    git('add', '.'); git('commit', '-qm', 'initial');
    assert.equal(run('preview'), 1, 'missing parent must build');
    writeFileSync(join(root, 'outside'), 'change'); git('add', '.'); git('commit', '-qm', 'unrelated');
    assert.equal(run('preview'), 0); assert.equal(run('production'), 1);
    writeFileSync(join(root, 'website/change'), 'change'); git('add', '.'); git('commit', '-qm', 'site');
    assert.equal(run('preview'), 1);
  } finally { rmSync(root, {recursive:true, force:true}); }
});
