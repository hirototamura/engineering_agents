// Restore the pinned public CAD assets for clean CI/Vercel/local builds.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { constants, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync, copyFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const site = fileURLToPath(new URL('../', import.meta.url));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function safePath(path) {
  if (typeof path !== 'string' || !path || path.includes('\\') || path.includes(':') || path.split('/').some(p => !p || p === '.' || p === '..'))
    throw new Error(`Unsafe CAD asset path: ${path}`);
  return path;
}
function walk(root) {
  return readdirSync(root).sort().flatMap(name => {
    const path = join(root, name), stat = lstatSync(path);
    if (stat.isSymbolicLink()) throw new Error(`Refuse CAD asset symlink: ${path}`);
    return stat.isDirectory() ? walk(path) : [path];
  });
}
export function verifyCadAssets(root, files) {
  if (lstatSync(root).isSymbolicLink()) throw new Error('Refuse CAD asset directory symlink');
  const expected = new Set(files.map(f => resolve(root, safePath(f.path))));
  if (walk(root).some(path => !expected.has(resolve(path)))) throw new Error('Unexpected file in CAD asset directory; preserve it explicitly before rebuilding');
  for (const file of files) {
    const path = join(root, safePath(file.path));
    if (!existsSync(path) || lstatSync(path).isSymbolicLink() || lstatSync(path).size !== file.size_bytes || hash(readFileSync(path)) !== file.sha256)
      throw new Error(`CAD asset missing or changed: ${file.path}; existing files were preserved`);
  }
}
export async function restoreCadAssets({
  manifestPath = join(site, 'assets/cube_cad.json'),
  target = join(site, 'public/cube-cad'), cache = join(site, '.asset-cache'), archiveFile,
} = {}) {
  const manifest = JSON.parse(readFileSync(manifestPath));
  if (manifest.schema_version !== 1 || manifest.artifact.root !== 'cube-cad' || !/^[0-9a-f]{64}$/.test(manifest.artifact.sha256))
    throw new Error('Unsupported CAD asset manifest');
  const seen = new Set();
  for (const file of manifest.files) {
    safePath(file.path);
    if (seen.has(file.path) || !/^[0-9a-f]{64}$/.test(file.sha256) || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0)
      throw new Error('Invalid CAD asset file manifest');
    seen.add(file.path);
  }
  if (existsSync(target)) {
    verifyCadAssets(target, manifest.files);
    return { files: manifest.files.length, restored: false };
  }
  mkdirSync(cache, { recursive: true });
  const archive = join(cache, `${manifest.artifact.sha256}.tar.gz`);
  if (!existsSync(archive)) {
    if (archiveFile) copyFileSync(archiveFile, archive, constants.COPYFILE_EXCL);
    else {
      const response = await fetch(manifest.artifact.url);
      if (!response.ok) throw new Error(`CAD asset download failed: HTTP ${response.status}`);
      const chunks = []; let size = 0;
      for await (const chunk of response.body) {
        size += chunk.length;
        if (size > manifest.artifact.size_bytes) throw new Error('CAD archive exceeds pinned size');
        chunks.push(chunk);
      }
      const bytes = Buffer.concat(chunks);
      if (bytes.length !== manifest.artifact.size_bytes || hash(bytes) !== manifest.artifact.sha256) throw new Error('CAD archive SHA-256 mismatch');
      const partial = `${archive}.${process.pid}.tmp`;
      writeFileSync(partial, bytes); renameSync(partial, archive);
    }
  }
  if (lstatSync(archive).isSymbolicLink() || lstatSync(archive).size !== manifest.artifact.size_bytes || hash(readFileSync(archive)) !== manifest.artifact.sha256)
    throw new Error('CAD archive SHA-256 mismatch; remove the corrupt cache entry explicitly');
  // The archive is a fixed, verified package created by package-cube-cad.mjs.
  // Check its complete path list before extracting into an isolated directory.
  const listed = execFileSync('tar', ['-tzf', archive], { encoding: 'utf8' }).trim().split('\n');
  const expected = new Set(manifest.files.map(f => `cube-cad/${f.path}`));
  if (listed.length !== expected.size || listed.some(path => !expected.has(safePath(path)))) throw new Error('CAD archive members differ from the pinned manifest');
  mkdirSync(dirname(target), { recursive: true });
  const staging = mkdtempSync(join(dirname(target), '.cube-cad-'));
  try {
    execFileSync('tar', ['-xzf', archive, '-C', staging]);
    verifyCadAssets(join(staging, 'cube-cad'), manifest.files);
    if (existsSync(target)) throw new Error('CAD target appeared during restoration; existing files were preserved');
    renameSync(join(staging, 'cube-cad'), target);
  } finally { rmSync(staging, { recursive: true, force: true }); }
  return { files: manifest.files.length, restored: true };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const result = await restoreCadAssets({ archiveFile: process.argv[2] });
  console.log(`Verified public CAD assets: ${result.files} files (${result.restored ? 'restored' : 'already present'})`);
}
