import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import vm from 'node:vm';
import { renderArticle } from '../src/lib/article.mjs';

const source = language => readFileSync(new URL(`../content/balancing-cube/${language === 'ja' ? 'index.ja.html' : 'index.html'}`, import.meta.url), 'utf8');
const built = language => readFileSync(new URL(`../dist/${language === 'ja' ? '' : 'en/'}index.html`, import.meta.url), 'utf8');
const evidence = html => JSON.parse(html.match(/<script id="research-evidence" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const contentBoundary = '<script id="research-evidence"';

test('language routes preserve every recorded measurement and interactive script', () => {
  for (const language of ['ja', 'en']) {
    const original = source(language), result = renderArticle(language, original), page = built(language);
    assert.equal(result.slice(result.indexOf(contentBoundary)), original.slice(original.indexOf(contentBoundary)));
    const scripts = html => [...html.matchAll(/<script\b[^>]*>[\s\S]*?<\/script>/g)].map(match => match[0]);
    assert.deepEqual(scripts(page), scripts(original));
    assert.deepEqual(evidence(page), evidence(original));
    assert.match(page, new RegExp(`<html lang="${language}">`));
    assert.match(page, /id="hero-cube"/);
    assert.match(page, /id="mount-time"/);
    // Catch script transformations or serialization errors introduced at build.
    for (const [, tag, attributes, code] of page.matchAll(/(<script\b([^>]*)>)([\s\S]*?)<\/script>/g)) {
      if (!attributes.includes('application/json') && code.trim()) new vm.Script(code);
    }
  }
  assert.deepEqual(evidence(built('ja')), evidence(built('en')));
});

test('article opens immediately and language links work without source folders', () => {
  assert.match(built('ja'), /href="\/en\/" lang="en" hreflang="en"/);
  assert.match(built('en'), /href="\/" lang="ja" hreflang="ja"/);
  for (const language of ['ja', 'en']) {
    const page = built(language);
    const prefix = page.split(contentBoundary)[0];
    assert.match(prefix, /<h1>[^<]+<\/h1>\s*<figure class="cube-intro"/);
    assert.doesNotMatch(prefix, /href="(?:file:|\.\.\/|index\.ja\.html|index\.html|evidence\.json)/);
    assert.doesNotMatch(page, /<script\b[^>]*\bsrc=|<iframe\b|<base\b/);
    assert.doesNotMatch(prefix, /id="(?:run-sources|source-hashes|download-evidence)"/);
  }
  assert.equal(existsSync(new URL('../dist/ja/index.html', import.meta.url)), false);
});

test('import manifest matches the exact source copies', () => {
  const manifest = JSON.parse(readFileSync(new URL('../content/balancing-cube/source-manifest.json', import.meta.url)));
  for (const [filename, item] of Object.entries(manifest.files)) {
    const bytes = readFileSync(new URL(`../content/balancing-cube/${filename}`, import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), item.sha256);
    assert.equal(bytes.length, item.bytes);
  }
});
