import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { restoreCadAssets } from '../scripts/restore-cube-cad.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'cad-assets-test-'));
  mkdirSync(join(root, 'source/cube-cad'), { recursive: true });
  const bytes = Buffer.from('<title>Public CAD reference</title>');
  writeFileSync(join(root, 'source/cube-cad/index.html'), bytes);
  const archiveFile = join(root, 'assets.tar.gz');
  execFileSync('tar', ['-czf', archiveFile, '-C', join(root, 'source'), 'cube-cad/index.html']);
  const raw = readFileSync(archiveFile);
  const manifest = { schema_version: 1, artifact: { root: 'cube-cad', url: 'https://example.invalid/unused', sha256: hash(raw), size_bytes: raw.length },
    files: [{ path: 'index.html', sha256: hash(bytes), size_bytes: bytes.length }] };
  const manifestPath = join(root, 'manifest.json'); writeFileSync(manifestPath, JSON.stringify(manifest));
  return { root, archiveFile, manifestPath, target: join(root, 'restored/cube-cad'), cache: join(root, 'cache') };
}
test('a clean checkout can restore public CAD assets offline and retry without a download', async () => {
  const f = fixture();
  try {
    assert.equal((await restoreCadAssets(f)).restored, true);
    assert.equal((await restoreCadAssets({ ...f, archiveFile: undefined })).restored, false);
    assert.match(readFileSync(join(f.target, 'index.html'), 'utf8'), /Public CAD reference/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});
test('hash mismatch installs no CAD output', async () => {
  const f = fixture();
  try {
    writeFileSync(f.archiveFile, 'corrupt');
    await assert.rejects(restoreCadAssets(f), /SHA-256 mismatch/);
    assert.equal(existsSync(f.target), false);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});
test('existing edited CAD files are preserved', async () => {
  const f = fixture();
  try {
    await restoreCadAssets(f);
    writeFileSync(join(f.target, 'index.html'), 'human edit');
    await assert.rejects(restoreCadAssets(f), /existing files were preserved/);
    assert.equal(readFileSync(join(f.target, 'index.html'), 'utf8'), 'human edit');
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});
