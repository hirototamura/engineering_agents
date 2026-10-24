"""Read-only case selection, readable test setup and eight-corner trajectories."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from tools.isaac_analysis.data import load, CORNERS, sha256
from tools.isaac_analysis.statistics import select, quantiles, quantile_records, summarize
from tools.isaac_analysis.figures import plot_bands

st.set_page_config(page_title='Eight corners · Isaac cube evidence', layout='wide')
st.markdown('''<style>
.stApp{background:#faf9f5;color:#202d34}[data-testid="stSidebar"]{background:#f0f1eb}
.block-container{max-width:1380px;padding-top:4.5rem}h1,h2{font-family:Georgia,serif!important;font-weight:500!important;letter-spacing:-.025em}
h1{font-size:2.8rem!important;line-height:1.12!important}h2{font-size:1.9rem!important}
[data-testid="stMetricValue"]{font-family:Georgia,serif;color:#24566d}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:#5b686e}button[role="tab"]{font-size:1rem!important}
[data-testid="stHeader"]{background:#faf9f5}[data-testid="stToolbar"]{display:none}
.eyebrow{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:#5b686e;margin-bottom:14px}
.lead{font-size:19px;line-height:1.6;color:#24566d;max-width:850px;margin:10px 0 24px}
.note{padding:14px 18px;border-left:3px solid #b64628;background:#f0f1eb;font-size:14px;line-height:1.7;margin:15px 0}
.band-key{display:flex;flex-wrap:wrap;gap:12px 24px;font-size:13px;margin:10px 0 20px;color:#5b686e}
.band-key span::before{content:"";display:inline-block;width:24px;height:10px;vertical-align:middle;margin-right:8px;background:var(--swatch)}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="eyebrow">One-Piece / Engineering Agents · Recorded simulation evidence</div>', unsafe_allow_html=True)
st.title('Eight corners. Two cube designs.')
st.markdown('<p class="lead">Explore the recorded trials, follow the tilt over time, and inspect exactly what was tested.</p>', unsafe_allow_html=True)


@st.cache_resource
def dataset_at(path):
    return load(path, verify=True)


@st.cache_data(show_spinner=False, max_entries=24)
def records_at(path, filters, mode, metric):
    data = dataset_at(path)
    ids = select(data, json.loads(filters))
    records = []
    for label in data.catalog['groups']:
        subset = [i for i in ids if data.cases[i]['campaign'] == label]
        if subset:
            records += quantile_records(data, quantiles(data, subset, mode, metric), label, mode, metric)
    return records


def reset_filters():
    for key in list(st.session_state):
        if key.startswith('ea_'):
            del st.session_state[key]


path = os.environ.get('EA_ISAAC_DATASET', '')
if not path:
    st.error('Launch with python -m tools.isaac_analysis serve --dataset PATH')
    st.stop()
dataset = dataset_at(path)
groups = dataset.catalog['groups']
labels = list(groups)
report_path = Path(os.environ['EA_ISAAC_REPORT']) if os.environ.get('EA_ISAAC_REPORT') else None
report_bytes = report_path.read_bytes() if report_path and report_path.is_file() else None


def architecture_name(label):
    return f"{label.capitalize()} · {groups[label]['factors']['side_m'] * 1000:.1f} mm"


with st.sidebar:
    st.header('Select trials')
    st.caption('1 · Select a design and initial conditions. The plots update automatically.')
    choice = st.radio('Architecture', labels + ['Compare both'] if len(labels) > 1 else labels,
                      format_func=lambda x: architecture_name(x) if x in groups else x, key='ea_campaign')
    campaigns = labels if choice == 'Compare both' else [choice]
    corners = st.multiselect('Corners', list(CORNERS), default=list(CORNERS), key='ea_corners')
    preset = st.selectbox('Initial tilt range', ['Full range · 0–5°', 'Small release · 0–2°', 'Larger release · 2–5°', 'Custom range'], key='ea_preset')
    if preset == 'Custom range':
        radius = list(st.slider('Initial rotation radius (°)', 0., 5., (0., 5.), .1, key='ea_radius'))
    else:
        radius = {'Full range · 0–5°': [0., 5.], 'Small release · 0–2°': [0., 2.], 'Larger release · 2–5°': [2., 5.]}[preset]
    yaw = list(st.slider('Initial yaw rate (rad/s)', -1., 1., (-1., 1.), .05, key='ea_yaw'))
    where = {'campaign': campaigns, 'corner': corners, 'initial_tilt_radius_deg': radius, 'initial_yaw_rate_rad_s': yaw}
    with st.expander('More initial conditions'):
        where['initial_tilt_azimuth_deg'] = list(st.slider('Rotation direction (°)', -180., 180., (-180., 180.), 5., key='ea_azimuth'))
        where['initial_tilt_x_deg'] = list(st.slider('Initial rotation x (°)', -5., 5., (-5., 5.), .1, key='ea_x'))
        where['initial_tilt_y_deg'] = list(st.slider('Initial rotation y (°)', -5., 5., (-5., 5.), .1, key='ea_y'))
    with st.expander('Mechanical properties'):
        st.caption('Values are linked to the two recorded designs. Selecting a value narrows cases; it does not change a simulation.')
        for key, label, scale, unit in [
            ('side_m', 'Side length', 1000, 'mm'), ('total_mass_kg', 'Total mass', 1000, 'g'),
            ('frame_mass_kg', 'Carrier mass', 1000, 'g'), ('wheel_mass_kg', 'Each rotating wheel mass', 1000, 'g'),
            ('wheel_radius_m', 'Wheel radius', 1000, 'mm'), ('wheel_thickness_m', 'Wheel thickness', 1000, 'mm'),
            ('wheel_axial_inertia_kg_m2', 'Wheel axial inertia', 1, 'kg m²'), ('frame_inertia_kg_m2', 'Carrier principal inertia', 1, 'kg m²')]:
            options = sorted({g['factors'][key] for g in groups.values()})
            if len(options) == 1:
                st.caption(f'{label}: {options[0] * scale:.6g} {unit} · fixed')
                continue
            chosen = st.selectbox(label, [None, *options],
                                  format_func=lambda x, s=scale, u=unit: 'All recorded values' if x is None else f'{x * s:.6g} {u}', key='ea_' + key)
            if chosen is not None:
                where[key] = [chosen, chosen]
    with st.expander('Gains, noise and delay'):
        st.caption('These settings are fixed in both campaigns. Exact gains and timing are in Test setup.')
        for key, label in [('controller_digest', 'Saved controller SHA-256'), ('observation_delay_s', 'Observation delay (s)'),
                           ('control_period_s', 'Control period (s)'), ('yaw_gain_nm_s', 'Yaw gain (N m s/rad)'),
                           ('tilt_noise_std_deg', 'Tilt noise σ (°)'), ('gyro_noise_std_deg_s', 'Gyro noise σ (°/s)')]:
            options = sorted({g['factors'][key] for g in groups.values()})
            if len(options) == 1:
                if key == 'controller_digest':
                    st.caption('Same saved controller in both designs; full digest in Test setup.')
                else:
                    st.caption(f'{label}: {options[0]:g} · fixed')
                continue
            chosen = st.selectbox(label, [None, *options], key='ea_' + key)
            if chosen is not None:
                where[key] = [chosen] if key == 'controller_digest' else [chosen, chosen]
        st.caption('Network transport, jitter and packet loss were not modeled.')
    outcomes = sorted({r['status'] for r in dataset.cases})
    passing = 'All outcomes'
    gpu = list(range(6))
    seed_values = None
    with st.expander('Recorded outcomes and exact cases'):
        st.caption('Outcome filters describe a subset chosen using its result.')
        where['status'] = st.multiselect('Termination status', outcomes, default=outcomes, key='ea_status')
        passing = st.selectbox('Screening outcome', ['All outcomes', 'Passed', 'Failed'], key='ea_outcome')
        if passing != 'All outcomes':
            where['screening_passed'] = [passing == 'Passed']
        gpu = st.multiselect('Simulation GPU', list(range(6)), default=list(range(6)), key='ea_gpu')
        where['gpu_indices'] = gpu
        seed = st.text_input('Exact noise seeds, separated by commas', key='ea_seed')
        case_id = st.text_input('Exact case IDs, separated by commas', key='ea_id')
        if case_id:
            where['id'] = [x.strip() for x in case_id.split(',') if x.strip()]
        try:
            seed_values = {int(x.strip()) for x in seed.split(',') if x.strip()} if seed else None
        except ValueError:
            st.error('Noise seeds must be integers.')
            st.stop()
        if seed_values is not None:
            where['seed_values'] = sorted(seed_values)
    st.button('Reset all filters', on_click=reset_filters, width='stretch')
    st.divider()
    if report_bytes:
        st.download_button('Download full technical report', report_bytes, file_name='isaac-cube-technical-report.html', mime='text/html', width='stretch')
        st.caption('One HTML file with all figures. Open it on your PC; it also works offline.')
    st.caption('Simulation evidence only. Physical performance and agreement between MuJoCo and PhysX remain unverified.')

try:
    ids = select(dataset, where)
except ValueError as error:
    st.error(str(error))
    st.stop()
rows = [dataset.cases[i] for i in ids]
# Comparison statistics always retain separate architecture denominators.
metrics = st.columns(1 + len(campaigns))
metrics[0].metric('Selected recorded episodes', f'{len(ids):,}')
for column, label in zip(metrics[1:], campaigns):
    subset = [r for r in rows if r['campaign'] == label]
    p = sum(r['screening_passed'] for r in subset)
    column.metric(label.capitalize() + ' screening pass rate', f'{100 * p / len(subset):.2f}%' if subset else 'No cases',
                  help=f'{p:,} passes / {len(subset):,} selected cases. This rate uses the selected initial conditions and outcomes.')
st.caption(' · '.join([f'Initial tilt {radius[0]:g}–{radius[1]:g}°', f'Yaw rate {yaw[0]:g}–{yaw[1]:g} rad/s', f'{len(corners)} corners', 'same saved gains and 15 ms observation delay']))
if passing != 'All outcomes' or set(where['status']) != set(outcomes):
    st.warning('This selection uses recorded outcomes. Its pass rate and percentiles are conditional descriptions of that subset.')

plots, setup, cases_tab, report_tab = st.tabs(['Tilt trajectories', 'Test setup', 'Cases & exports', 'Full technical report'])
with plots:
    st.header('Tilt over time, corner by corner')
    st.caption('2 · Choose how to treat stopped cases, then inspect all eight axes. Hover over a median for values and sample counts.')
    controls = st.columns([1.3, 1, 1])
    mode = controls[0].selectbox('Motion after stopping', ['all-recorded', 'evaluation-only'],
                                format_func=lambda x: {'all-recorded': 'Include all recorded motion', 'evaluation-only': 'Through evaluation stop only'}[x], key='ea_mode')
    metric = controls[1].selectbox('Tilt measurement', ['tilt_total_deg', 'tilt_x_deg', 'tilt_y_deg'],
                                   format_func=lambda x: {'tilt_total_deg': 'Total tilt (°)', 'tilt_x_deg': 'Tilt x (°)', 'tilt_y_deg': 'Tilt y (°)'}[x], key='ea_metric')
    zoom = controls[2].selectbox('Vertical scale', ['Full recorded range', 'Near upright · 0–5°', 'Fine detail · 0–0.5°'], key='ea_zoom')
    if mode == 'all-recorded':
        st.markdown('<div class="note"><strong>Failures stay visible.</strong> Every selected case contributes at every timestamp. After a stop, the controller sends zero effort and the cube continues moving freely. Later tilt may describe falling or resting on another face.</div>', unsafe_allow_html=True)
    else:
        st.warning('Stopped cases leave later bands. A narrow band can hide failures; the remaining sample count is shown for each corner and in hover values.')
    if zoom != 'Full recorded range':
        st.caption('Zoom clips values outside the displayed range. Every selected case still contributes to the percentile calculation and CSV export.')
    st.markdown('<div class="band-key"><span style="--swatch:#719fb2">68.3%</span><span style="--swatch:#b0ccd6">95.5%</span><span style="--swatch:#dce7eb">99.7%</span><span style="--swatch:#eff3f3">100%</span><span style="--swatch:#24566d">Median line</span></div>', unsafe_allow_html=True)
    with st.spinner('Computing percentiles from every selected case…'):
        records = records_at(path, json.dumps(where, sort_keys=True), mode, metric)
    frame = pd.DataFrame(records)
    if not len(ids):
        st.info('No recorded cases match these filters. Widen the ranges or reset all filters.')
    else:
        scale = alt.Scale(zero=metric == 'tilt_total_deg') if zoom == 'Full recorded range' else alt.Scale(domain=[0, 5 if zoom == 'Near upright · 0–5°' else .5])
        # Use a shared explicit range so corners remain visually comparable.
        if zoom == 'Full recorded range':
            low = frame['lo_100_0'].min()
            high = frame['hi_100_0'].max()
            scale = alt.Scale(domain=[0 if metric == 'tilt_total_deg' else min(0, low) * 1.04, max(.1, high * 1.04)])
        palette = ['#24566d', '#b64628', '#276354']
        for start in range(0, len(CORNERS), 2):
            for column, corner in zip(st.columns(2), CORNERS[start:start + 2]):
                with column:
                    st.subheader('Corner ' + corner)
                    subset = frame[frame.corner == corner]
                    end = subset[subset.time_s == float(dataset.time[-1])]
                    st.caption(' · '.join(f"{r['campaign'].capitalize()}: {int(r['selected']):,} selected / {int(r['evaluation_count']):,} still evaluated at 6 s" for r in end.to_dict('records')))
                    base = alt.Chart(alt.Data(values=json.loads(subset.to_json(orient='records')))).encode(
                        x=alt.X('time_s:Q', title='Time (s)', scale=alt.Scale(domain=[float(dataset.time[0]), float(dataset.time[-1])])),
                        color=alt.Color('campaign:N', title=None, scale=alt.Scale(domain=campaigns, range=[palette[labels.index(label) % len(palette)] for label in campaigns]), legend=alt.Legend(orient='top')))
                    layers = []
                    for coverage, opacity in [('100_0', .07), ('99_7', .10), ('95_5', .18), ('68_3', .30)]:
                        layers.append(base.mark_area(opacity=opacity, clip=True).encode(y=alt.Y('lo_' + coverage + ':Q', title='Tilt (°)', scale=scale), y2='hi_' + coverage + ':Q'))
                    layers.append(base.mark_line(strokeWidth=2, clip=True).encode(y=alt.Y('median:Q', title='Tilt (°)', scale=scale), tooltip=[
                        alt.Tooltip('campaign:N', title='Architecture'), alt.Tooltip('time_s:Q', title='Time (s)', format='.3f'), alt.Tooltip('median:Q', title='Median (°)', format='.4f'),
                        alt.Tooltip('lo_95_5:Q', title='2.25 percentile (°)', format='.4f'), alt.Tooltip('hi_95_5:Q', title='97.75 percentile (°)', format='.4f'),
                        alt.Tooltip('selected:Q', title='Selected cases'), alt.Tooltip('count:Q', title='Contributing now'), alt.Tooltip('evaluation_count:Q', title='Still evaluated now')]))
                    if metric == 'tilt_total_deg':
                        thresholds = alt.Chart(pd.DataFrame({'limit': [5, 20], 'meaning': ['Peak screening limit · 5°', 'Stop threshold · 20°']})).mark_rule(strokeDash=[4, 4], color='#b6987b', opacity=.7, clip=True).encode(y=alt.Y('limit:Q', scale=scale), tooltip=['meaning:N'])
                        layers.append(thresholds)
                    chart = alt.layer(*layers).properties(height=235).configure_view(stroke=None).configure_axis(labelFontSize=12, titleFontSize=12, gridColor='#e2e6e2')
                    st.altair_chart(chart, width='stretch')
        st.caption('Bands show central empirical coverage at each time. Darkest band: middle 68.3%; palest band: full range. These are pointwise percentiles across trials, not confidence intervals or a Gaussian assumption. Dashed lines: 5° peak screening limit and 20° stop threshold.')
    with st.expander('Draw and download every selected trajectory'):
        st.caption('No trajectory subsampling. Rendering thousands of lines can take a moment; exported figures use the full vertical range.')
        if st.checkbox('Render all case paths', key='ea_paths') and len(ids):
            import matplotlib.pyplot as plt
            for label in campaigns:
                selected = [i for i in ids if dataset.cases[i]['campaign'] == label]
                if not selected:
                    continue
                figure, _ = plot_bands(dataset, selected, mode=mode, metric=metric, trajectories=True, title=label.capitalize())
                st.pyplot(figure)
                buffer = io.BytesIO()
                figure.savefig(buffer, format='png', dpi=160)
                plt.close(figure)
                st.download_button('Download ' + label + ' all-case plot', buffer.getvalue(), file_name=label + '-all-case-tilt.png', mime='image/png')

with setup:
    st.header('What was actually tested')
    st.caption('3 · These are the settings attached to the selected architectures. Filters select archived cases; they do not run a new experiment.')
    st.subheader('Mechanical configurations')
    properties = [('Side length', 'side_m', 1000, 'mm'), ('Assembly mass', 'total_mass_kg', 1000, 'g'),
                  ('Carrier mass', 'frame_mass_kg', 1000, 'g'), ('Each rotating wheel mass', 'wheel_mass_kg', 1000, 'g'),
                  ('Wheel radius', 'wheel_radius_m', 1000, 'mm'), ('Wheel thickness', 'wheel_thickness_m', 1000, 'mm'),
                  ('Wheel axial inertia', 'wheel_axial_inertia_kg_m2', 1, 'kg m²'), ('Carrier principal inertia', 'frame_inertia_kg_m2', 1, 'kg m²')]
    st.dataframe(pd.DataFrame([{'Property': label, 'Unit': unit, **{name.capitalize(): f"{groups[name]['factors'][key] * factor:.9g}" for name in campaigns}} for label, key, factor, unit in properties]), hide_index=True, width='stretch')
    st.caption('Four rigid bodies: one carrier and three reaction wheels on the lower faces near corner 000. Wheel shafts follow body x/y/z. These are numerical assumptions; mass-identified CAD and hardware verification remain outstanding.')
    st.subheader('Timing, observations and communication')
    st.dataframe(pd.DataFrame([
        {'Setting': 'Physics step', **{name.capitalize(): f"{groups[name]['factors']['timestep_s'] * 1000:g} ms" for name in campaigns}},
        {'Setting': 'Controller period', **{name.capitalize(): f"{groups[name]['factors']['control_period_s'] * 1000:g} ms" for name in campaigns}},
        {'Setting': 'Tilt / gyro observation delay', **{name.capitalize(): f"{groups[name]['factors']['observation_delay_s'] * 1000:g} ms" for name in campaigns}},
        {'Setting': 'Tilt observation noise, σ', **{name.capitalize(): f"{groups[name]['factors']['tilt_noise_std_deg']:g}°" for name in campaigns}},
        {'Setting': 'Gyro observation noise, σ', **{name.capitalize(): f"{groups[name]['factors']['gyro_noise_std_deg_s']:g}°/s" for name in campaigns}},
        {'Setting': 'Network latency / jitter / packet loss', **{name.capitalize(): 'Not modeled' for name in campaigns}},
    ]), hide_index=True, width='stretch')
    st.caption('The 15 ms observation delay is a simulated one-sample sensor delay. Encoders and coordinate transforms use ideal simulator state. The plotted tilt is geometric truth, not the noisy feedback signal.')
    st.subheader('Saved controller and gains')
    for name in campaigns:
        controller = groups[name]['payload']['compiled']['controller']
        st.markdown('**' + architecture_name(name) + '**')
        st.caption('State: [tilt x, tilt y, world angular rate x, world angular rate y, wheel momentum x, wheel momentum y], in SI units. The same saved controller is reused across all eight corners.')
        st.dataframe(pd.DataFrame([[f'{x:.10g}' for x in row] for row in controller['K']], columns=controller['state_order'], index=['World torque x', 'World torque y']), width='stretch')
        parameters = controller['design_parameters']
        st.caption(f"Tilt Q scale {parameters['tilt_q_scale']:g} · rate Q scale {parameters['rate_q_scale']:g} · momentum Q scale {parameters['momentum_q_scale']:g} · yaw gain {controller['yaw_rate_gain_nm_s']:g} N m s/rad · R = {controller['fixed_r']}")
        with st.expander(name.capitalize() + ' · full precision gains and controller source'):
            st.json(controller)
    st.markdown('The controller requests world torque **τxy = −K × state**. A yaw-rate term is mapped with that torque into the body wheel axes. The motor model limits available torque to **0.0834 × max(0, 1 − |wheel rate| / 702.6696) N m**. Above **200 rad/s**, commands accelerating a wheel farther are zeroed; braking remains allowed. The full report retains the exact constants and model limits.')
    st.subheader('Initial conditions')
    st.markdown('Each design uses the same **24,576-case plan**: 3,072 cases per corner, initial rotation radius uniform from **0 to 5°**, direction uniform from **−180 to 180°**, and world yaw rate uniform from **−1 to 1 rad/s**. Per-case seeds define sensor noise. Uniform radius gives more density near upright than a uniform-area disk.')
    with st.expander('Exact resolved physics, controller, screening gates and source identifiers'):
        for name in campaigns:
            st.subheader(name.capitalize())
            st.json({'factors': groups[name]['factors'], 'compiled': groups[name]['payload']['compiled'],
                     'screening': groups[name]['payload']['snapshot']['contract']['screening']})

with cases_tab:
    st.header('Selected cases and reproducible exports')
    st.caption('Statistics remain separate for each mechanical architecture. Every export uses the current filters.')
    summary = [r for r in summarize(dataset, ids) if r['campaign'] in campaigns and r['corner'] in corners]
    st.dataframe(pd.DataFrame([{'Architecture': r['campaign'].capitalize(), 'Corner': r['corner'], 'Cases': r['cases'], 'Passes': r['screening_passed'],
                               'Pass rate (%)': round(r['pass_fraction'] * 100, 3) if r['pass_fraction'] is not None else None} for r in summary]), hide_index=True, width='stretch')
    st.subheader('Case preview')
    preview_columns = ['campaign', 'id', 'corner', 'initial_tilt_radius_deg', 'initial_yaw_rate_rad_s', 'seed', 'gpu_index', 'status', 'screening_passed']
    st.dataframe(pd.DataFrame(rows[:200]).reindex(columns=preview_columns), hide_index=True, width='stretch')
    st.caption(f'First {min(200, len(rows)):,} of {len(rows):,} selected cases shown. Complete case records are available in the JSON export below.')
    receipt = {'where': where, 'mode': mode, 'metric': metric, 'vertical_view': zoom, 'indices': [int(i) for i in ids],
               'source_cache_sha256': sha256(dataset.root / 'checksums.json'),
               'input_digests': {k: g['payload']['compiled']['input_digest'] for k, g in groups.items() if k in campaigns}}
    downloads = st.columns(3)
    downloads[0].download_button('Percentile data · CSV', frame.to_csv(index=False), file_name='selected-quantiles.csv', mime='text/csv')
    downloads[1].download_button('Filters · JSON', json.dumps(where, indent=2), file_name='selection.json', mime='application/json')
    downloads[2].download_button('Selection receipt · JSON', json.dumps(receipt, indent=2), file_name='selection-receipt.json', mime='application/json')
    if st.checkbox('Prepare complete case-record download', key='ea_case_export'):
        st.download_button('All selected case records · JSON', json.dumps(rows, indent=2), file_name='selected-cases.json', mime='application/json')
    st.caption('The receipt contains all selected indices and source digests. Percentiles use every matching case; zoom affects display only. Archived simulation data and screening gates remain unchanged.')

with report_tab:
    st.header('The full technical report')
    st.caption('This report covers the complete frozen campaigns. Sidebar filters affect the trajectory and case tabs; they do not change this historical report.')
    if report_bytes:
        st.download_button('Save the full report to your PC', report_bytes, file_name='isaac-cube-technical-report.html', mime='text/html')
        if hasattr(st, 'iframe'):
            st.iframe(report_bytes.decode('utf-8'), height=1050, alt='Full Isaac cube technical report')
        else:
            components.html(report_bytes.decode('utf-8'), height=1050, scrolling=True)
    else:
        st.info('The full report has not been attached to this viewer. Launch serve with --report PATH/technical-report.html, or generate a fresh report with the report command.')
