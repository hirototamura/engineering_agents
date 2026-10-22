import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import vm from 'node:vm';

const root = new URL('../dist/', import.meta.url);
const page = route => readFileSync(new URL(route, root), 'utf8');
const data = (html, id) => JSON.parse(html.match(new RegExp(`<script id="${id}" type="application/json">([\\s\\S]*?)</script>`))[1]);

test('public CAD pages preserve bilingual geometry, checks and functioning local links', () => {
  const ja = page('cube-cad/index.html'), en = page('cube-cad/en/index.html');
  for (const [lang, html, other] of [['ja', ja, '/cube-cad/en/'], ['en', en, '/cube-cad/']]) {
    assert.match(html, new RegExp(`<html lang="${lang}">`));
    assert.ok(html.includes(`class="language-switch" href="${other}"`));
    assert.doesNotMatch(html, /file:\/\/|\/Users\/|\/home\//);
    assert.equal(data(html, 'model-data').parts.length, 33);
    assert.equal(data(html, 'validation-data').step_roundtrip.solid_count, 33);
    for (const [, href] of html.matchAll(/href="([^"]+)"/g)) {
      if (!href.startsWith('/')) continue;
      assert.ok(existsSync(new URL(href.slice(1) + (href.endsWith('/') ? 'index.html' : ''), root)), href);
    }
    for (const [, attrs, code] of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
      if (!attrs.includes('application/json')) new vm.Script(code);
    }
  }
  assert.deepEqual(data(ja, 'model-data'), data(en, 'model-data'));
  assert.deepEqual(data(ja, 'validation-data'), data(en, 'validation-data'));
});
