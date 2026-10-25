import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=resolve(fileURLToPath(new URL('../',import.meta.url))),out=resolve(root,'dist'),data=JSON.parse(readFileSync(resolve(root,'public/isaac/data/manifest.json')));
test('public Isaac routes expose the report, viewer shell and pinned campaign dimensions',()=>{
  assert.equal(data.schema_version,1);assert.equal(data.case_count,49152);assert.equal(data.time_s.length,401);
  assert.equal(Object.keys(data.groups).length,2);assert.equal(Object.keys(data.groups.reference.corners).length,8);
  for(const path of ['isaac/index.html','isaac/viewer/index.html','isaac/report/index.html','isaac/publication.json','isaac-viewer/app.mjs','isaac-viewer/worker.mjs'])assert.equal(existsSync(resolve(out,path)),true,`missing built route or client file: ${path}`);
  const viewer=readFileSync(resolve(out,'isaac/viewer/index.html'),'utf8'),report=readFileSync(resolve(out,'isaac/report/index.html'),'utf8');
  assert.match(viewer,/mobile-filters/);assert.match(viewer,/id="charts"/);assert.match(viewer,/id="download-cases"/);
  assert.match(report,/href="\/isaac\/viewer\/"/);assert.match(report,/In this report/);
  assert.doesNotMatch(report,/127\.0\.0\.1|\/home\/|GPU-[0-9a-fA-F]{8}-/);
  const receipt=JSON.parse(readFileSync(resolve(out,'isaac/publication.json')));assert.equal(receipt.trajectories,49152);assert.equal(receipt.samples_per_trajectory,401);
  for(const asset of Object.values(receipt.compressed_files)){const rel=asset.url.replace(/^\/isaac\//,'isaac/'),file=resolve(out,rel);assert.equal(existsSync(file),true,`missing published data: ${rel}`);assert.equal(statSync(file).size,asset.bytes);}
});
