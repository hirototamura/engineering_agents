// Pointwise empirical quantiles. No fitted model, trajectory subsample or gate changes.
export const PROBABILITIES = [0, .0015, .0225, .1585, .5, .8415, .9775, .9985, 1];
export const CORNERS = Array.from({length:8},(_,i)=>i.toString(2).padStart(3,'0'));
const NUMERIC = new Set(['initial_tilt_radius_deg','initial_tilt_x_deg','initial_tilt_y_deg','initial_tilt_azimuth_deg','initial_yaw_rate_rad_s','side_m','total_mass_kg','frame_mass_kg','wheel_mass_kg','wheel_radius_m','wheel_axial_inertia_kg_m2','wheel_transverse_inertia_kg_m2','frame_inertia_kg_m2','wheel_thickness_m','wheel_face_inset_m','motor_torque_limit_nm','wheel_speed_limit_rad_s','gravity_m_s2','observation_delay_s','control_period_s','yaw_gain_nm_s','tilt_noise_std_deg','gyro_noise_std_deg_s']);
const CATEGORIES = new Set(['campaign','corner','status','screening_passed','id','seed_values','gpu_indices','controller_digest']);
export function validateWhere(where) {
  if (!where || typeof where !== 'object' || Array.isArray(where)) throw Error('Expected a filter object.');
  for (const [key,rule] of Object.entries(where)) {
    if (!NUMERIC.has(key) && !CATEGORIES.has(key)) throw Error(`Unknown filter: ${key}`);
    if (!Array.isArray(rule)) throw Error('Filter values must be lists.');
    if (NUMERIC.has(key) && (rule.length!==2 || !rule.every(x=>typeof x==='number' && Number.isFinite(x)) || rule[0]>rule[1])) throw Error('Ranges require finite minimum ≤ maximum.');
  }
}
export function matches(row, factors, where) {
  for (const [key,rule] of Object.entries(where)) {
    const actual = key==='seed_values' ? row.seed : key==='gpu_indices' ? row.gpu_index : (key in row ? row[key] : factors[key]);
    if (NUMERIC.has(key) ? !(actual>=rule[0] && actual<=rule[1]) : !rule.includes(actual)) return false;
  }
  return true;
}
export function emptyPanel(ticks) {
  return {selected:0, passed:0, count:Array(ticks).fill(0),evaluation_count:Array(ticks).fill(0),q:PROBABILITIES.map(()=>Array(ticks).fill(null))};
}
export function linearQuantile(sorted,p) {
  const index=(sorted.length-1)*p, low=Math.floor(index), fraction=index-low;
  return sorted[low]+(sorted[Math.min(low+1,sorted.length-1)]-sorted[low])*fraction;
}
export function summarizePaths(values, ticks, rows, ids, mode, includePaths=false) {
  if (!['all-recorded','evaluation-only'].includes(mode)) throw Error('Unknown post-stop policy.');
  if (values.length!==rows.length*ticks) throw Error('Trajectory dimensions disagree with the case records.');
  const out=emptyPanel(ticks);out.selected=ids.length;out.passed=ids.reduce((n,i)=>n+Number(rows[i].screening_passed),0);
  if (!ids.length) return out;
  const buffer=new Float64Array(ids.length);
  for (let t=0;t<ticks;t++) {
    let n=0, evaluating=0;
    for (const i of ids) {
      const active=t<=rows[i].end_tick;if (active) evaluating++;
      if (mode==='all-recorded' || active) buffer[n++]=values[i*ticks+t];
    }
    out.count[t]=n;out.evaluation_count[t]=evaluating;
    if (n) {const sorted=buffer.subarray(0,n);sorted.sort();PROBABILITIES.forEach((p,j)=>out.q[j][t]=linearQuantile(sorted,p));}
  }
  if (includePaths) {
    out.paths=new Float32Array(ids.length*ticks);
    ids.forEach((i,j)=>{out.paths.set(values.subarray(i*ticks,(i+1)*ticks),j*ticks);if(mode==='evaluation-only')out.paths.fill(NaN,j*ticks+rows[i].end_tick+1,(j+1)*ticks);});
  }
  return out;
}
