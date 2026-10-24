// Publish the self-contained CAD reference pages with portable site links.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const source = resolve(process.argv[2] || fileURLToPath(new URL('../../../balancing-cube-simulation/results/cad-reference-20261021/', import.meta.url)));
const target = fileURLToPath(new URL('../public/cube-cad/', import.meta.url));
const base = '/cube-cad/';
const origin = 'https://engineering-agents-research.vercel.app';
mkdirSync(join(target, 'en'), { recursive: true });
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const manifest = { configuration: 'cube-cad-remrc-reference-20261021-r1', sourcePages: {}, assets: {} };
const assets = ['cube_reference_assembly.step', 'cube_reference_assembly.blend', 'cube_reference_assembly.glb',
  'assembly_inventory.csv', 'bom_coverage.json', 'assembly_parameters.json', 'validation.json',
  'interface_checks.json', 'source_LICENSE.txt', 'source_README.txt',
  'assembly.png', 'assembly_exploded.png', 'assembly_cutaway.png'];
for (const filename of readdirSync(join(source, 'source'))) assets.push(`source/${filename}`);
for (const filename of readdirSync(join(source, 'part_library')).filter(f => f.endsWith('.step'))) assets.push(`part_library/${filename}`);
for (const filename of readdirSync(join(source, 'source_stl'))) assets.push(`source_stl/${filename}`);
for (const filename of assets) {
  const dest = join(target, filename); mkdirSync(resolve(dest, '..'), { recursive: true });
  copyFileSync(join(source, filename), dest); manifest.assets[filename] = sha(readFileSync(dest));
}
for (const [lang, filename, route] of [['ja', 'index.ja.html', ''], ['en', 'index.html', 'en/']]) {
  const original = readFileSync(join(source, filename), 'utf8');
  manifest.sourcePages[lang] = sha(original);
  let html = original.replace(/(<script id="model-data" type="application\/json">)([\s\S]*?)(<\/script>)/,
    (_, start, json, end) => {
      const data = JSON.parse(json); delete data.manifest.source_directory;
      return start + JSON.stringify(data).replaceAll('</', '<\\/') + end;
    });
  html = html.replace(/href="([^"]+)"/g, (_, href) => {
    if (/^(https?:|#|data:)/.test(href)) return `href="${href}"`;
    if (href === 'index.html') return `href="${base}en/"`;
    if (href === 'index.ja.html') return `href="${base}"`;
    return `href="${base}${href}"`;
  });
  const description = lang === 'ja' ? '実際の3Dプリント部品と参考BOMから構成したセルフバランシングキューブ。3Dで組立・分解・内部配置を確認し、CADファイルを取得できます。' :
    'An interactive self-balancing cube CAD reference assembled from supplied print files and a reference BOM, with assembly views and CAD downloads.';
  html = html.replace('</style>', `</style><meta name="description" content="${description}"><meta property="og:image" content="${origin}${base}assembly.png"><meta property="og:title" content="${lang === 'ja' ? 'セルフバランシングキューブ · 参考CADアセンブリ' : 'Self-balancing cube · CAD reference assembly'}"><link rel="canonical" href="${origin}${base}${route}"><link rel="alternate" hreflang="ja" href="${base}"><link rel="alternate" hreflang="en" href="${base}en/">`);
  if (/\/Users\/|\/home\/|file:\/\//.test(html)) throw new Error('Local path found in public page');
  writeFileSync(join(target, route, 'index.html'), html);
}
writeFileSync(join(target, 'publication-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Prepared bilingual CAD pages and ${assets.length} assets at ${target}`);
