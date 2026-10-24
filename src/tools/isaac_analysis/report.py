"""Reproducible technical report generated from audited campaign artifacts."""
from __future__ import annotations
import base64
import csv
import html
import json
import re
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from .data import write_json
from .statistics import select,summarize,risk_bins,paired_outcomes,quantile_records
from .figures import plot_bands,plot_comparison


def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n|'+'|'.join('---' for _ in headers)+'|\n'+''.join('| '+' | '.join(str(x) for x in row)+' |\n' for row in rows)+'\n'


def build(dataset,output):
    expected={'151f2bd27d18139b73b5b26f6cdcfff7926c534922e2971bd57ab3b4608483a8',
              'b4b65a32da74137d5b91666e7d2ab383ac27c66bf38cc74d8106493f26be7227'}
    if {g['payload']['compiled']['input_digest'] for g in dataset.catalog['groups'].values()}!=expected:
        raise ValueError('This detailed protocol report covers the original two frozen architectures. Use inventory/select/quantiles for other configurations.')
    if any(g['manifest']['plan_sha256']!='97776e29c25b46dbbca6595c5b7563b54f431d4d99493a7c0b5c32cda777250f' for g in dataset.catalog['groups'].values()):
        raise ValueError('The detailed historical report requires the original 24,576-case plan')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);groups=dataset.catalog['groups'];labels=list(groups)
    all_ids=select(dataset);summary=summarize(dataset,all_ids);risk=risk_bins(dataset,all_ids)
    figures=[];all_quantiles=[]
    for label in labels:
        ids=select(dataset,{'campaign':[label]})
        for mode in ('all-recorded','evaluation-only'):
            name=f'{label}-{mode}-percentiles.png'
            fig,bands=plot_bands(dataset,ids,mode=mode,title=f'{label} · {len(ids):,} Monte Carlo runs')
            fig.savefig(output/name,dpi=180);plt.close(fig);figures.append(name)
            all_quantiles+=quantile_records(dataset,bands,label,mode,'tilt_total_deg')
    if len(labels)==2:
        fig=plot_comparison(dataset,*labels);fig.savefig(output/'paired-design-comparison.png',dpi=180);plt.close(fig);figures.append('paired-design-comparison.png')
        paired=paired_outcomes(dataset,*labels)
    else:paired=[]
    write_json(output/'statistics.json',{'corner_summaries':summary,'initial_tilt_risk_bins':risk,'paired_outcomes':paired})
    write_json(output/'quantiles.json',all_quantiles)
    for name,rows in [('quantiles.csv',all_quantiles),('risk-bins.csv',risk)]:
        with (output/name).open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_json(output/'source-catalog.json',dataset.catalog)
    write_json(output/'selection.json',{'where':{},'case_count':len(dataset.cases),'dataset':str(dataset.root.resolve()),
        'quantile_method':'numpy linear sample quantiles; pointwise; central empirical coverage',
        'coverages_percent':[68.3,95.5,99.7,100],'after_stop_modes':['all-recorded','evaluation-only']})
    first=groups[labels[0]]['payload'];config=first['compiled']['config'];ctrl=first['compiled']['controller']
    sections=['# Isaac cube campaigns: technical specification and Monte Carlo analysis\n',
        'Analysis date: 2026-10-24 (Asia/Tokyo). This report analyzes existing measurements; no new physics trials were run. '
        'The dataset is exploratory, the cross-backend comparison is inconclusive, and hardware is unverified.\n',
        '## 1. Exactly what was tested\n',
        f'Two distinct mechanical configurations were tested with the same saved controller and paired initial-condition/noise plan. '
        f'This analysis includes {len(dataset.cases):,} recorded episodes. Each campaign contributes 24,576 episodes, with 3,072 per corner. '
        'The two campaigns are paired design experiments, not 49,152 independent initial-condition samples. '
        'The earlier wiring pilots, Cartpole installation tests, failed launch attempts, native comparison fixtures and eight-case videos are separate evidence and are excluded from these percentile denominators.\n',
        table(['Campaign','Source directory','Input digest','Wall time (s)'],[[k,Path(g['campaign_path']).name,g['payload']['compiled']['input_digest'],f"{g['manifest']['wall_time_s']:.6f}"] for k,g in groups.items()]),
        'The source snapshot is `bottom-corner-000-20261017-3`. The reference is an unverified lower-face descendant, not an adopted design. '
        'The candidate proposal ID is `prop-20261017-001`; its predicted >95% screening success on the six weaker corners was falsified. '
        'Only side length was changed as a design variable. The existing compiler also changes derived wheel radius, frame mass and inertias when side length changes.\n',
        '## 2. Monte Carlo initial conditions\n',
        'The frozen plan uses NumPy default_rng seed 20261023. The eight corner bit strings are interleaved deterministically. '
        'For each case, radius r is uniform on [0,5] degrees, azimuth a is uniform on [-pi,pi], and the commanded initial rotation vector is '
        '`[r*cos(a), r*sin(a), 0]` in world axes. This is a rotation vector, not a pair of finite Euler rotations. '
        'Uniform radius is **not uniform area over a disk**; it gives relatively greater density near upright. '
        'World yaw rate is independently uniform on [-1,1] rad/s (about ±57.296 degrees/s). A per-case integer seed is drawn from [0,2^31-1) '
        'and drives tilt/gyro noise. Corner assignment is stratified; it is not sampled from an operational probability model.\n',
        'At initialization, the selected corner sphere center is placed at world `[0,0,0.004]` m plus its environment origin. '
        'The equilibrium rotation aligns the fixed assembly COM-minus-corner direction with world +Z. The sampled world rotation is then applied. '
        'Root-link linear velocity and world angular x/y rates are zero; world angular z rate is the sampled yaw rate. '
        'All rotor joint angles and relative angular rates start at zero. The wheels retain their three lower-face body mounts for every corner. '
        'They are never moved to whichever corner is being tested. There are no external torque disturbances, randomized friction, mass errors, gains, delays or material-property draws in these two campaigns.\n',
        table(['Campaign','Observed initial radius range (°)','Observed yaw-rate range (rad/s)','Noise seeds'],[
            [label,f"{min(r['initial_tilt_radius_deg'] for r in dataset.cases if r['campaign']==label):.8f} – {max(r['initial_tilt_radius_deg'] for r in dataset.cases if r['campaign']==label):.8f}",
            f"{min(r['initial_yaw_rate_rad_s'] for r in dataset.cases if r['campaign']==label):.8f} – {max(r['initial_yaw_rate_rad_s'] for r in dataset.cases if r['campaign']==label):.8f}",'Per-case archived seed'] for label in labels]),
        '## 3. Mechanical model and mass properties\n',
        'The simulation model is four rigid bodies (one carrier plus three wheels), three revolute reaction-wheel joints and eight corner-sphere colliders. '
        'Carrier mass is declared once through explicit inertial properties. Decorative geometry has no additional mass. '
        'This is the numerical model exported through the trusted design compiler, not a mass-identified 152 mm STL/CAD assembly. '
        'All mass, inertia, motor and contact values remain modeling assumptions pending hardware identification.\n']
    keys=[('cube_side_m','Side length','m'),('frame_mass_kg','Carrier mass','kg'),('frame_inertia_kg_m2','Carrier principal inertias','kg m²'),
        ('frame_com_fraction','Carrier COM / side','1'),('wheel_mass_kg','Each rotating wheel + rotor mass','kg'),
        ('wheel_radius_m','Wheel radius','m'),('wheel_thickness_m','Wheel thickness','m'),('wheel_axial_inertia_kg_m2','Each wheel axial inertia','kg m²'),
        ('wheel_transverse_inertia_kg_m2','Each wheel transverse inertia','kg m²'),('wheel_face_inset_m','Lower-face mount inset','m'),
        ('joint_damping_nm_s','MJCF joint damping','N m s/rad'),('gravity_m_s2','Gravity','m/s²')]
    sections.append(table(['Property','Unit',*labels],[[name,unit,*[json.dumps(g['payload']['compiled']['config']['physics'][key]) for g in groups.values()]] for key,name,unit in keys]))
    sections.append(table(['Derived property',*labels],[[name,*[json.dumps(g['factors'][key]) for g in groups.values()]] for key,name in [('total_mass_kg','Total mass (kg)'),('body_com_m','Assembly COM in body axes (m)'),('wheel_centers_body_m','Wheel center coordinates in body axes (m)')]]))
    sections += ['Wheel x/y/z shafts align with their respective carrier body axes. The center of wheel i has coordinate i equal to 0.012 m and the other two equal to half the side. '
        'The carrier COM is at half the side along every body axis. Authored USD masses, COMs and principal inertia values were audited against exported MJCF. '
        'That audit and the runtime total-mass check do not establish contact-solver equivalence.\n',
        '## 4. Controller, exact gains and actuator limits\n',
        'The saved controller is identical in both campaigns; it was not retuned to the larger cube or to each corner. '
        'The six-element control state is `[tilt_x, tilt_y, omega_x, omega_y, H_x, H_y]`, with angles in radians, rates in rad/s, '
        'and wheel momentum H in kg m²/s. Tilt/gyro use delayed noisy observations; wheel rates, momentum transformations and body rotation for command mapping use ideal simulator state. '
        'The controller computes `tau_world_xy = -K @ state` and wheel yaw command `tau_world_z = +g_yaw * omega_z_delayed`. '
        'The world torque is transformed by the current true body rotation transpose into the three wheel motor commands. The carrier reacts against these wheel torques. '
        'Yaw rate is suppressed; absolute yaw angle is not regulated.\n',
        'Exact saved controller (small off-diagonal terms are retained):\n\n```json\n'+json.dumps(ctrl,indent=2)+'\n```\n',
        'The nominal model records base vertex Q weights `[300,300,1,1,50000,50000]`. The saved design parameters are tilt scale 1.0, '
        'rate scale 1.0310625, momentum scale 0.825, and yaw gain 0.03 N m s/rad. R is fixed at `[100,100]`. '
        'The saved eigenvalue magnitudes belong to the nominal linearized controller-design plant; they are not nonlinear stability certificates for all corners or for the larger cube.\n',
        'Both configurations use the registered `bldc_ec45` family. Requested wheel torque is clipped at every 1 ms physics step using '
        '`available = 0.0834 * max(0,1-abs(wheel_rate)/702.6695568529171)` N m. '
        'Above 200 rad/s (1909.859 rpm), a command accelerating a wheel farther in the same direction is zeroed; braking commands remain allowed. '
        'The continuous-comparison threshold is also 0.0834 N m, so the recorded over-continuous fraction is not an informative thermal margin here. '
        'This is a symmetric linear envelope, not a validated electrical, thermal, PWM, driver, battery or regenerative-braking model.\n',
        '## 5. Timing, sensing and communication\n',
        table(['Quantity','Executed setting','Interpretation'],[
            ['Physics step','0.001 s (1000 Hz)','Fixed; no timestep refinement'],
            ['Controller update / held request','0.015 s (66.6667 Hz)','15 physics steps per controller interval'],
            ['Tilt/gyro observation delay','0.015 s','Exactly one control sample; initial sampled observation held at startup'],
            ['Tilt noise','Independent Gaussian, σ=0.05° per x/y observation','Sampled each control tick'],
            ['Gyro noise','Independent Gaussian, σ=0.2°/s per world axis','Sampled each control tick'],
            ['Encoder and coordinate transform','Ideal current simulator state','No encoder noise or encoder transport delay'],
            ['Communication-network delay / jitter / dropouts','Not modeled','No communication-delay sweep exists in this data'],
            ['LLM/inference in feedback loop','None','Engineering proposal generated after the reference campaign'],
            ['Telemetry timestamps','401 samples: 0,0.015,…,6.000 s','Control-rate ground truth, not the noisy feedback signal']]),
        'The 15 ms delay applies to tilt and gyro observations. It should not be described as a measured ESP32/IMU/network latency. '
        'Sensor acquisition dynamics, attitude estimation, accelerometer/magnetometer physics, bus scheduling, compute jitter and actuator transport latency were not simulated. '
        'Noise streams can be regenerated from case seeds and the pinned sampling code, but noisy observations themselves were not saved in these NPZ files.\n',
        '## 6. PhysX execution, contact and termination\n',
        'Isaac Sim 6.2.0.0 / Isaac Lab 3.0.0 with CUDA PhysX used six independent processes on physical GPUs 0–5 (RTX A5000). '
        'Each process created 4,096 environments spaced 1 m apart, replicated physics and a shared ground plane. '
        'GPU 6 retained the local proposal model; GPU 7 was excluded. Torch-side telemetry/control calculations use float32; timestamps are float64. '
        'No per-step rendering was used in the large campaigns. Native MuJoCo comparisons use CPU dynamics. Analysis and quantile calculation run on CPU.\n',
        'The runner selects the USD `Physics=physx` variant, enables gyroscopic forces, disables self collisions, sets articulation solver position/velocity iterations to 16/4, '
        'sets sleep and stabilization thresholds to zero, and sets rigid-body maximum angular velocity to 2000 rad/s. '
        'Wheel implicit actuators have zero stiffness/damping and the explicit effort limit. The ground material is explicitly assigned static/dynamic friction 0.7. '
        'Each corner collider is a 4 mm sphere. Contact points are collected with a capacity of 32 per carrier. '
        'The MJCF specifies sliding friction 0.7, torsional/rolling friction zero, solref `[0.01,1.0]`, and solimp `[0.95,0.99,0.001]`. '
        'Those last tuples are MuJoCo contact settings; the campaign does not prove an identical effective PhysX contact law. '
        'Unspecified engine defaults (including unlogged solver/contact tolerances) were not independently captured and should not be inferred from this report.\n',
        'Termination checks run at control ticks: total tilt >20°, missing normal contact force below 1e-4 N for at least 0.1 s, '
        'slip speed >0.05 m/s for at least 0.15 s, pivot displacement >30 mm, or nonfinite state. Stop times are quantized to 15 ms. '
        'On a stop, the controller effort is zeroed for that case but the cloned body continues to evolve through six seconds. '
        'The original summary includes only samples through its stop index. The final-1-second RMS uses the archived slice '
        '`a[max(0,len(a)-1-int(1/control_dt)):]`; at 6 s it is 67 samples spanning 0.99 s. For an early stop it is the final available window before stopping, not the final second of a successful six-second episode. '
        'The required-duration gate prevents treating a short failed episode as a pass. Recovery-band and settle-hold fields in configuration are not additional executed screening gates.\n',
        '## 7. Executed numerical screening criteria\n']
    criteria=first['snapshot']['contract']['screening']
    sections += [table(['Metric','Operator','Limit'],[[r['metric'],r['operator'],r['limit']] for r in criteria['criteria']]+[['Required duration','>=',criteria['required_duration_s']]]),
        'These fixed numerical gates are reused for exploration on all eight corners. They are not a new human-approved eight-corner physical acceptance standard. '
        'Contact fraction excludes the initial zero-force startup sample. Recorded continuous-torque and governor fractions are accumulated at physics rate, not reconstructed from the control-rate plots.\n',
        '## 8. Per-corner results and paired comparison\n',
        table(['Campaign','Corner','N','Screening passes','Pass fraction','95% Wilson interval','Episode statuses'],[[r['campaign'],r['corner'],r['cases'],r['screening_passed'],f"{r['pass_fraction']:.6f}",str(r['wilson_95']),str(r['status_counts'])] for r in summary])]
    if paired:
        sections += [table(['Corner','Paired N','Fail→pass','Pass→fail','Difference (percentage points)','Exact McNemar p','Holm-adjusted p'],[[r['corner'],r['pairs'],r['fail_to_pass'],r['pass_to_fail'],r['difference_pp'],f"{r['mcnemar_exact_p']:.5g}",f"{r['holm_adjusted_p']:.5g}"] for r in paired]),
            'All six weaker corners regressed. The same cases and sensor seeds were paired; the two all-pass corners provide no evidence of an improvement. '
            'P-values compare paired binary screening outcomes within this simulation distribution. Holm adjustment covers the eight corner comparisons. '
            'Neither the p-values nor Wilson intervals include physical model uncertainty. The observed association does not isolate inertia, mass and geometry as independent causes. '
            'The proposal was selected using this exploration set; there is no fresh held-out confirmation campaign in this evidence.\n']
    sections += ['## 9. Time-versus-tilt percentile plots\n',
        'Each axis corresponds to one supported body corner. All 3,072 selected cases for that campaign/corner contribute; no trajectory subsample is used to compute bands. '
        'The median and central 68.3%, 95.5%, 99.7%, and 100% empirical coverage use percentiles [15.85,84.15], [2.25,97.75], [0.15,99.85], and [0,100], respectively, at each time. '
        'Linear sample-quantile interpolation is used. These are pointwise state-distribution bands, not confidence intervals, Gaussian sigma claims, simultaneous trajectory envelopes, or probability-of-success curves.\n',
        '**All-recorded view:** every case contributes at every timestamp, including uncontrolled free evolution after its recorded stop. '
        'This prevents failed cases silently disappearing, but a later plateau can mean the cube settled on another face, not successful balancing. '
        '**Evaluation-only view:** each case contributes through its stop sample, inclusively, and is missing thereafter. '
        'The evaluated count at six seconds is shown on every axis. Later low bands condition on survival and must be read with those denominators. '
        'No padding, last-observation carry-forward, invented measurements or interpolation across stopped intervals is used.\n']
    example=[r for r in all_quantiles if r['campaign']==labels[0] and r['corner']=='001' and r['time_s']==3.]
    sections.append(table(['Corner 001 at 3 s','Contributing N','Median (°)','Upper 97.75 percentile (°)'],
        [[r['mode'],r['count'],r['median'],r['hi_95_5']] for r in example]))
    sections.append('This concrete difference is the effect of including recorded post-stop falling versus conditioning on cases still under evaluation. '
        'A narrow survivor band alone would hide the failed subpopulation.\n')
    sections.append(table(['Campaign','Corner 001 initial radius bin (°)','N','Screening pass fraction'],
        [[r['campaign'],r['initial_radius_bin_deg'],r['count'],r['pass_fraction']] for r in risk if r['corner']=='001']))
    sections.append('The initial-radius bins are descriptive conditioning on recorded inputs. Full eight-corner bin counts and Wilson intervals are in risk-bins.csv; '
        'differences across bins are not a causal decomposition of the linked mechanical properties.\n')
    for name in figures:sections.append(f'![{name}]({name})\n')
    sections += ['## 10. Data quality, telemetry meaning and remaining uncertainties\n',
        'The loader verifies campaign completion, plan and input hashes, shard case/source/design/GPU identities, complete unique case coverage, time grids, finite telemetry, '
        'recorded stop indices/statuses, initial tilt consistency (a declared 0.06° float32/acos tolerance near upright), and peak-tilt agreement with historical summaries. It records SHA-256 for every read source file and for the derived cache. '
        'The original large-campaign manifests did not individually hash telemetry files; new analysis hashes identify the bytes analyzed without retroactively claiming that earlier provenance was stronger.\n',
        'The NPZ channels are true pose-derived tilt x/y/total, true world angular velocity x/y/z, joint wheel rates x/y/z, '
        'summed world-Z normal contact force, maximum tangential contact-point slip, selected-corner planar drift, and three control-tick motor-request values after the envelope/governor. '
        'The motor-request telemetry is computed before inactive cases are zeroed; **after a stop these channels do not represent the actual zero effort sent to the plant**. '
        'This analysis uses pose-derived tilt and does not reinterpret post-stop motor telemetry as physical actuation. '
        'Normal force and slip are explicitly zeroed at the startup sample. Raw body quaternions, root positions, wheel joint angles, applied effort at every physics substep, '
        'electrical energy, temperatures and calibrated sensor data were not archived. Full videos for arbitrary archived cases cannot be reconstructed exactly from tilt alone.\n',
        'Eight corner-000 native MuJoCo comparisons exceeded the frozen angular-rate and wheel-speed agreement limits. This remains inconclusive backend qualification. '
        'All mass/contact/motor values are numerical assumptions; input-distribution quantiles do not resolve that discrepancy or establish the eight-corner hardware mission. '
        'The identical saved controller and limited mechanical change make this a bounded architecture sensitivity experiment, not a trained reinforcement-learning policy.\n',
        '## 11. Reusable tools and filters\n',
        'Use `python -m tools.isaac_analysis --help`. The tool collection provides inventory, immutable preparation/audit, JSON case selection, '
        'quantile CSV/JSON/PNG export, this report, and a local filterable viewer. Filters include campaign, corner, initial rotation radius/components/azimuth, '
        'yaw rate, seed, GPU, termination class and screening outcome; mechanical properties, saved-controller digest/yaw gain and observation delay are matched to recorded campaign factors. '
        'Only two linked mechanical configurations exist. Gains and delay are fixed; filtering them does not create new simulations or identify their sensitivity. '
        'Filtering on an outcome is descriptive conditioning and must not be presented as an unconditional Monte Carlo success rate.\n',
        '```bash\npython -m tools.isaac_analysis quantiles --dataset DATASET --where selection.json --mode all-recorded --output NEW_EXPORT\n'
        'python -m tools.isaac_analysis serve --dataset DATASET --port 8526\n```\n',
        'Example `selection.json`:\n\n```json\n'+json.dumps({'campaign':[labels[0]],'initial_tilt_radius_deg':[0,2],'initial_yaw_rate_rad_s':[-.5,.5],'observation_delay_s':[.015,.015]},indent=2)+'\n```\n',
        '## 12. Exact resolved inputs and provenance\n',
        'Complete resolved configs, controller matrices, proposal, frozen screening contract, case factors and source hashes are in `source-catalog.json`. '
        'Every case and its seed remain in the prepared dataset `cases.json`; filtered selections export explicit case IDs and indices. '
        'Use `quantiles.csv`, `quantiles.json`, `risk-bins.csv`, `statistics.json` and `selection.json` as machine-readable engineering evidence. '
        'The cache and report live in fresh directories; no historical simulation record is rewritten.\n',
        'Private original evidence: https://github.com/hirototamura/balancing-cube-simulation/releases/tag/isaac-cube-20261024\n']
    markdown='\n'.join(sections);(output/'technical-report.md').write_text(markdown)
    # Embed figures so the readable HTML report is a standalone artifact.
    def inline(value):
        value=html.escape(value)
        value=re.sub(r'`([^`]+)`',r'<code>\1</code>',value)
        return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)
    blocks=[];code=False;in_table=False
    for line in markdown.splitlines():
        if in_table and not line.startswith('|'):
            blocks.append('</tbody></table></div>');in_table=False
        if line.startswith('```'):
            blocks.append('</code></pre>' if code else '<pre><code>');code=not code;continue
        if code:blocks.append(html.escape(line)+'\n');continue
        if line.startswith('!['):
            name=line.split('](',1)[1][:-1];encoded=base64.b64encode((output/name).read_bytes()).decode()
            blocks.append(f'<figure><img alt="{html.escape(name)}" src="data:image/png;base64,{encoded}"></figure>');continue
        if line.startswith('|'):
            if set(line.replace('|','').replace('-','').strip())==set():
                blocks.append('</thead><tbody>');continue
            cells=line.strip('| ').split('|')
            if not in_table:
                blocks.append('<div class="table-scroll"><table><thead>');in_table=True;tag='th'
            else:tag='td'
            blocks.append('<tr>'+''.join(f'<{tag}>'+inline(c.strip())+f'</{tag}>' for c in cells)+'</tr>');continue
        if line.startswith('# '):blocks.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('## '):blocks.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line:blocks.append('<p>'+inline(line)+'</p>')
    if in_table:blocks.append('</tbody></table></div>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Isaac campaign technical report</title><style>body{font:16px/1.6 system-ui;max-width:1450px;margin:40px auto;padding:0 24px;color:#172838}h1{font-size:32px}h2{margin-top:48px;border-bottom:1px solid #b8c7d5}img{width:100%}figure{margin:28px 0}pre{overflow:auto;background:#f2f6fa;padding:20px;font-size:13px}.table-scroll{overflow:auto;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:9px 12px;border-bottom:1px solid #dbe4ec;overflow-wrap:anywhere;min-width:80px}th{background:#eaf0f7}p{max-width:1100px}code{font-size:.88em}</style>'+'\n'.join(blocks)+'</html>'
    (output/'technical-report.html').write_text(page)
