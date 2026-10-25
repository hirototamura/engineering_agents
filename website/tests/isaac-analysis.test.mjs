import test from 'node:test';
import assert from 'node:assert/strict';
import { CORNERS, emptyPanel, linearQuantile, matches, summarizePaths, validateWhere } from '../public/isaac-viewer/analysis.mjs';

test('pointwise empirical bands include failed trials and preserve inclusive stop ticks', () => {
  const rows=[{end_tick:1,screening_passed:true,seed:10},{end_tick:0,screening_passed:false,seed:20}];
  const values=new Float32Array([1,3,5,7, 2,4,6,8]);
  const all=summarizePaths(values,4,rows,[0,1],'all-recorded',true);
  assert.deepEqual(all.q[4],[1.5,3.5,5.5,7.5]);
  assert.deepEqual(all.count,[2,2,2,2]);
  assert.equal(all.selected,2);assert.equal(all.passed,1);
  const evaluation=summarizePaths(values,4,rows,[0,1],'evaluation-only',true);
  assert.deepEqual(evaluation.evaluation_count,[2,1,0,0]);
  assert.deepEqual(evaluation.count,[2,1,0,0]);
  assert.equal(evaluation.q[4][1],3);
  assert.equal(evaluation.q[4][2],null);
  assert.ok(Number.isNaN(evaluation.paths[6]));
  assert.ok(Number.isNaN(evaluation.paths[7]));
});

test('filtering keeps architecture and corner case counts separate', () => {
  const where={campaign:['candidate'],corner:['101'],initial_tilt_radius_deg:[0,2],screening_passed:[false],seed_values:[8]};
  validateWhere(where);
  assert.equal(matches({seed:8,initial_tilt_radius_deg:1,screening_passed:false},{campaign:'candidate',corner:'101'},where),true);
  assert.equal(matches({seed:9,initial_tilt_radius_deg:1,screening_passed:false},{campaign:'candidate',corner:'101'},where),false);
  assert.deepEqual(CORNERS,['000','001','010','011','100','101','110','111']);
  assert.equal(emptyPanel(3).q[4][2],null);
});

test('quantile definition uses linear interpolation and rejects malformed ranges', () => {
  assert.equal(linearQuantile([0,10],.25),2.5);
  assert.equal(linearQuantile([1,2,3,4],.5),2.5);
  assert.throws(()=>validateWhere({initial_tilt_radius_deg:[2,1]}),/finite minimum/);
  assert.throws(()=>validateWhere({unrecognized:[1]}),/Unknown filter/);
});
