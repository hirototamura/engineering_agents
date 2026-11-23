import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const output = new URL('../dist/', import.meta.url);
const cadPages = ['cube-cad/', 'cube-cad/en/'];
const isaacPages = ['isaac/', 'isaac/viewer/', 'isaac/report/'];

test('existing CAD and Isaac page URLs open lightweight archive notices', () => {
  for (const [pages, manifestName] of [[cadPages, 'cube_cad'], [isaacPages, 'isaac-web']]) {
    const manifest = JSON.parse(readFileSync(new URL(`../assets/${manifestName}.json`, import.meta.url)));
    for (const route of pages) {
      const page = readFileSync(new URL(`${route}index.html`, output), 'utf8');
      assert.match(page, /<html lang="(?:ja|en)"[\s>]/);
      const releaseLink = page.match(/href="([^"]+\/releases\/tag\/[^"]+)"/)?.[1];
      assert.ok(releaseLink, route);
      assert.ok(manifest.artifact.url.startsWith(releaseLink.replace('/tag/', '/download/') + '/'), route);
      assert.ok(Buffer.byteLength(page) < 10_000, route);
    }
  }
});

test('archive routes contain only notice pages and ship no Isaac viewer code', () => {
  for (const pages of [cadPages, isaacPages]) {
    const [root] = pages;
    const expected = pages.map(route => `${route.slice(root.length)}index.html`).sort();
    const directory = fileURLToPath(new URL(root, output));
    assert.deepEqual(readdirSync(directory, { recursive: true, withFileTypes: true })
      .filter(entry => !entry.isDirectory())
      .map(entry => relative(directory, join(entry.parentPath, entry.name)))
      .sort(), expected);
  }
  assert.equal(existsSync(new URL('isaac-viewer/', output)), false);
});

test('the offline Isaac viewer retains the archived client and report links', () => {
  const viewer = new URL('../public/isaac-viewer/', import.meta.url);
  const page = readFileSync(new URL('index.html', viewer), 'utf8');
  assert.match(page, /<script type="module" src="\/isaac-viewer\/app\.mjs"/);
  assert.match(page, /href="\/isaac\/report\/"/);
  assert.ok(existsSync(new URL('app.mjs', viewer)));
});
