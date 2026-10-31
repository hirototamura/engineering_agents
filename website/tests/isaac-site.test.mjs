import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { factorOptions } from '../public/isaac-viewer/filter-options.mjs';
import { matches, validateWhere } from '../public/isaac-viewer/analysis.mjs';

const root=resolve(fileURLToPath(new URL('../',import.meta.url))),out=resolve(root,'dist'),data=JSON.parse(readFileSync(resolve(root,'public/isaac/data/manifest.json')));
test('published factor aliases and exact mechanical options match their own archived campaign',()=>{
  const converted=['side_m','total_mass_kg','frame_mass_kg','wheel_mass_kg','wheel_radius_m','wheel_thickness_m','wheel_face_inset_m'];
  for(const group of Object.values(data.groups)){
    assert.equal(group.factors.side_m,group.physics.cube_side_m);
    assert.equal(group.factors.total_mass_kg,group.physics.frame_mass_kg+3*group.physics.wheel_mass_kg);
    assert.equal(group.factors.yaw_gain_nm_s,group.controller.yaw_rate_gain_nm_s);
    const where={};
    for(const key of [...converted,'yaw_gain_nm_s']){
      assert.equal(typeof group.factors[key],'number',`missing published factor: ${key}`);
      const option=factorOptions([group.factors[key]],'',converted.includes(key)?1000:1)[0];
      const value=Number(option.value);
      assert.equal(value,group.factors[key]);
      where[key]=[value,value];
    }
    validateWhere(where);
    assert.equal(matches({},group.factors,where),true);
  }
});
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
