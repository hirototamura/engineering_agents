/** Import a reviewable copy; a Vercel build never needs the research workspace. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const source = path.resolve(process.argv[2] ?? path.join(root, '../../reports/iphone-research'));
const destination = path.join(root, 'content/balancing-cube');
const filenames = { ja: 'index.ja.html', en: 'index.html' };
const pending = [];
for (const [language, filename] of Object.entries(filenames)) {
  const bytes = await readFile(path.join(source, filename));
  const html = bytes.toString('utf8');
  if (!html.includes(`<html lang="${language}">`) || !html.includes('id="research-evidence"')) {
    throw new Error(`Wrong language or incomplete source: ${filename}`);
  }
  pending.push({ language, filename, bytes, sha256: createHash('sha256').update(bytes).digest('hex') });
}
const evidence = html => JSON.parse(html.match(/<script id="research-evidence" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const jaData = evidence(pending[0].bytes.toString('utf8'));
const enData = evidence(pending[1].bytes.toString('utf8'));
if (JSON.stringify(jaData) !== JSON.stringify(enData)) throw new Error('Language editions contain different evidence');
await mkdir(destination, { recursive: true });
for (const item of pending) await writeFile(path.join(destination, item.filename), item.bytes);
await writeFile(path.join(destination, 'source-manifest.json'), JSON.stringify({
  schema_version: 1,
  source: 'reports/iphone-research in the engineering research workspace',
  article_revision: jaData.article_revision,
  evidence_cut: jaData.evidence_cut,
  files: Object.fromEntries(pending.map(item => [item.filename, {language: item.language, sha256: item.sha256, bytes: item.bytes.length}]))
}, null, 2) + '\n');
console.log('Imported Japanese and English article copies with identical evidence.');
