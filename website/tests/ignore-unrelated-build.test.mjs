import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('preview compares the website with the last successful deployment', (t) => {
  const root = mkdtempSync(join(tmpdir(), 'vercel-ignore-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const git = (...args) => execFileSync('git', ['-C', root, ...args], { encoding: 'utf8' }).trim();
  const script = join(root, 'website/scripts/ignore-unrelated-build.mjs');
  const run = (previous, target = 'preview') => spawnSync(process.execPath, [script], {
    env: { ...process.env, VERCEL_ENV: target, VERCEL_GIT_PREVIOUS_SHA: previous },
  }).status;
  const commit = (path, contents) => {
    writeFileSync(join(root, path), contents);
    git('add', '.');
    git('commit', '-qm', path);
    return git('rev-parse', 'HEAD');
  };

  git('init', '-q');
  git('config', 'user.name', 'Test');
  git('config', 'user.email', 'test@example.invalid');
  mkdirSync(join(root, 'website/scripts'), { recursive: true });
  copyFileSync(new URL('../scripts/ignore-unrelated-build.mjs', import.meta.url), script);
  const deployed = commit('website/article', 'initial');
  assert.equal(run(''), 1, 'first deployment must build');
  assert.equal(run('1'.repeat(40)), 1, 'unavailable history must build');
  assert.equal(run('HEAD^'), 1, 'invalid SHA must build');

  commit('notes', 'first unrelated edit');
  assert.equal(run(deployed), 0, 'unrelated change skips the preview');
  assert.equal(run(deployed, 'production'), 1, 'production always builds');

  const websiteChange = commit('website/article', 'revised');
  assert.equal(run(deployed), 1, 'website change must build');
  commit('notes', 'unrelated follow-up');
  assert.equal(run(deployed), 1, 'unbuilt website change must survive an unrelated follow-up');
  assert.equal(run(websiteChange), 0, 'after the website deploys the follow-up can skip');

  rmSync(join(root, '.git'), { recursive: true });
  assert.equal(run(websiteChange), 1, 'a checkout without Git metadata must build');
});
