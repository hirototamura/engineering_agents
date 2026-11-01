import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { restoreIsaacAssets } from '../scripts/restore-isaac.mjs';

const hash=b=>createHash('sha256').update(b).digest('hex');
function fixture(){const root=mkdtempSync(join(tmpdir(),'isaac-assets-test-'));mkdirSync(join(root,'source/isaac/data'),{recursive:true});const bytes=Buffer.from('{"schema_version":1}');writeFileSync(join(root,'source/isaac/data/manifest.json'),bytes);const archiveFile=join(root,'assets.tar.gz');execFileSync('tar',['-czf',archiveFile,'-C',join(root,'source'),'isaac/data/manifest.json']);const archive=readFileSync(archiveFile),manifest={schema_version:1,artifact:{root:'isaac',url:'https://example.invalid/unused',sha256:hash(archive),size_bytes:archive.length},files:[{path:'data/manifest.json',sha256:hash(bytes),size_bytes:bytes.length}]};const manifestPath=join(root,'manifest.json');writeFileSync(manifestPath,JSON.stringify(manifest));return{root,archiveFile,manifestPath,target:join(root,'restored/isaac'),cache:join(root,'cache')};}
test('pinned public web assets restore offline and verify on subsequent builds',async()=>{const f=fixture();try{assert.equal((await restoreIsaacAssets(f)).restored,true);assert.equal((await restoreIsaacAssets({...f,archiveFile:undefined})).restored,false);assert.equal(readFileSync(join(f.target,'data/manifest.json'),'utf8'),'{"schema_version":1}');}finally{rmSync(f.root,{recursive:true,force:true});}});
test('a corrupt Isaac archive is rejected without installing output',async()=>{const f=fixture();try{writeFileSync(f.archiveFile,'corrupt');await assert.rejects(restoreIsaacAssets(f),/SHA-256 mismatch/);assert.equal(existsSync(f.target),false);}finally{rmSync(f.root,{recursive:true,force:true});}});
