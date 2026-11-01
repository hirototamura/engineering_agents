// Package the explicitly approved public web projection; never include the private raw archives.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstatSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const site=fileURLToPath(new URL('../',import.meta.url)),source=join(site,'public/isaac');
const output=resolve(process.argv[2]||'/tmp/engineering-research-isaac-web-20261025-r1.tar.gz');
const url=process.argv[3]||'https://github.com/hirototamura/engineering_agents/releases/download/isaac-web-20261025-r1/engineering-research-isaac-web-20261025-r1.tar.gz';
const hash=b=>createHash('sha256').update(b).digest('hex');
function walk(root){return readdirSync(root).sort().flatMap(name=>{const p=join(root,name),s=lstatSync(p);if(s.isSymbolicLink())throw Error(`Refuse asset symlink: ${p}`);return s.isDirectory()?walk(p):[p];});}
const paths=walk(source),files=paths.map(path=>({path:relative(source,path).split('\\').join('/'),sha256:hash(readFileSync(path)),size_bytes:lstatSync(path).size}));
mkdirSync(dirname(output),{recursive:true});
execFileSync('tar',['--format=ustar','--no-xattrs','-czf',output,'-C',dirname(source),'--',...files.map(f=>`isaac/${f.path}`)],{env:{...process.env,COPYFILE_DISABLE:'1'}});
const manifest={schema_version:1,id:'isaac-campaigns-20261024-v1',scope:'Public viewer projection only: tilt trajectories, selected case metadata and technical report. The original full campaign archives remain private.',artifact:{url,sha256:hash(readFileSync(output)),size_bytes:lstatSync(output).size,root:'isaac'},files};
writeFileSync(join(site,'assets/isaac-web.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({archive:output,sha256:manifest.artifact.sha256,bytes:manifest.artifact.size_bytes,files:files.length}));
