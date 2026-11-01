// Package the already-public CAD view; do not include the private research workspace.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstatSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const site = fileURLToPath(new URL('../', import.meta.url));
const source = join(site, 'public/cube-cad');
const output = resolve(process.argv[2] || '/tmp/engineering-research-cube-cad-20261024-r2.tar.gz');
const url = process.argv[3] || 'https://github.com/hirototamura/engineering_agents/releases/download/website-cad-20261024-r2/engineering-research-cube-cad-20261024-r2.tar.gz';
const hash = value => createHash('sha256').update(value).digest('hex');
function walk(root) {
  return readdirSync(root).sort().flatMap(name => {
    if (name === '.DS_Store') return [];
    const path = join(root, name), stat = lstatSync(path);
    if (stat.isSymbolicLink()) throw new Error(`Refuse archive symlink: ${path}`);
    return stat.isDirectory() ? walk(path) : [path];
  });
}
const paths = walk(source);
const files = paths.map(path => ({ path: relative(source, path).split('\\').join('/'), sha256: hash(readFileSync(path)), size_bytes: lstatSync(path).size }));
mkdirSync(dirname(output), { recursive: true });
// Omit macOS AppleDouble files and extended attributes. BSD tar hides these
// entries when listing, while GNU tar exposes them as extra archive members.
execFileSync('tar', ['--format=ustar', '--no-xattrs', '-czf', output, '-C', dirname(source), '--', ...files.map(f => `cube-cad/${f.path}`)],
  { env: { ...process.env, COPYFILE_DISABLE: '1' } });
const manifest = { schema_version: 1, id: 'cube-cad-remrc-reference-20261021-r1',
  scope: 'Only assets already shared by the public CAD reference pages; attribution and source license are included.',
  artifact: { url, sha256: hash(readFileSync(output)), size_bytes: lstatSync(output).size, root: 'cube-cad' }, files };
writeFileSync(join(site, 'assets/cube_cad.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ archive: output, sha256: manifest.artifact.sha256, bytes: manifest.artifact.size_bytes, files: files.length }));
