"""Local, read-only factor selection and Monte Carlo trajectory explorer."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import altair as alt
import pandas as pd
import streamlit as st
from tools.isaac_analysis.data import load,CORNERS,sha256
from tools.isaac_analysis.statistics import select,quantiles,quantile_records,summarize
from tools.isaac_analysis.figures import plot_bands

st.set_page_config(page_title='Isaac Monte Carlo evidence',layout='wide')
st.title('Isaac cube · Monte Carlo evidence')
st.caption('Recorded six-second trajectories · eight body corners · pose-derived tilt · physical model unverified')


@st.cache_resource
def dataset_at(path):return load(path,verify=True)


path=os.environ.get('EA_ISAAC_DATASET','')
if not path:
    st.error('Launch with python -m tools.isaac_analysis serve --dataset PATH');st.stop()
dataset=dataset_at(path);groups=dataset.catalog['groups'];where={}
with st.sidebar:
    st.header('Select recorded cases')
    campaigns=st.multiselect('Campaign',list(groups),default=[next(iter(groups))])
    where['campaign']=campaigns
    corners=st.multiselect('Supported corner',CORNERS,default=list(CORNERS));where['corner']=corners
    where['initial_tilt_radius_deg']=list(st.slider('Initial rotation radius (°)',0.,5.,(0.,5.),.1))
    where['initial_yaw_rate_rad_s']=list(st.slider('Initial yaw rate (rad/s)',-1.,1.,(-1.,1.),.05))
    with st.expander('Rotation direction and components'):
        where['initial_tilt_azimuth_deg']=list(st.slider('Initial rotation azimuth (°)',-180.,180.,(-180.,180.),5.))
        where['initial_tilt_x_deg']=list(st.slider('Initial rotation x (°)',-5.,5.,(-5.,5.),.1))
        where['initial_tilt_y_deg']=list(st.slider('Initial rotation y (°)',-5.,5.,(-5.,5.),.1))
    with st.expander('Mechanical properties'):
        for key,label in [('side_m','Side length (m)'),('total_mass_kg','Total mass (kg)'),('frame_mass_kg','Carrier mass (kg)'),
            ('wheel_mass_kg','Each wheel mass (kg)'),('wheel_radius_m','Wheel radius (m)'),
            ('wheel_axial_inertia_kg_m2','Wheel axial inertia (kg m²)'),('frame_inertia_kg_m2','Carrier principal inertia (kg m²)'),
            ('wheel_thickness_m','Wheel thickness (m)')]:
            options=sorted({g['factors'][key] for g in groups.values()})
            chosen=st.selectbox(label,['All recorded values',*options],disabled=len(options)==1,key='factor-'+key)
            if chosen!='All recorded values':where[key]=[chosen,chosen]
            if len(options)==1:st.caption(f'Fixed: {options[0]:.12g}')
    with st.expander('Control and observation timing'):
        for key,label in [('controller_digest','Saved controller (SHA-256)'),('observation_delay_s','Observation delay (s)'),
            ('control_period_s','Control period (s)'),('yaw_gain_nm_s','Yaw gain (N m s/rad)'),
            ('tilt_noise_std_deg','Tilt noise σ (°)'),('gyro_noise_std_deg_s','Gyro noise σ (°/s)')]:
            options=sorted({g['factors'][key] for g in groups.values()})
            chosen=st.selectbox(label,['All recorded values',*options],disabled=len(options)==1,key='factor-'+key)
            if chosen!='All recorded values':where[key]=[chosen] if key=='controller_digest' else [chosen,chosen]
            if len(options)==1:st.caption('Fixed: '+str(options[0]))
        st.caption('No network delay, jitter, packet loss or controller-gain sweep was simulated.')
    with st.expander('Case identity and recorded outcome'):
        outcomes=sorted({r['status'] for r in dataset.cases})
        where['status']=st.multiselect('Termination status',outcomes,default=outcomes)
        passing=st.selectbox('Screening outcome',['All outcomes','Passed','Failed'])
        if passing!='All outcomes':where['screening_passed']=[passing=='Passed']
        gpu=st.multiselect('Simulation GPU index',list(range(6)),default=list(range(6)))
        # Category-like GPU selection is expressed using case filtering below.
        seed=st.text_input('Exact noise seeds (comma-separated; blank = all)')
        case_id=st.text_input('Exact case IDs (comma-separated; blank = all)')
        if case_id:where['id']=[x.strip() for x in case_id.split(',') if x.strip()]
        where['gpu_indices']=gpu
        try:seed_values={int(x.strip()) for x in seed.split(',') if x.strip()} if seed else None
        except ValueError:st.error('Noise seeds must be integers.');st.stop()
        if seed_values is not None:where['seed_values']=sorted(seed_values)
    st.download_button('Download filter JSON',json.dumps(where,indent=2),file_name='selection.json',mime='application/json')

try:
    ids=select(dataset,where)
except ValueError as error:st.error(str(error));st.stop()

rows=[dataset.cases[i] for i in ids];passed=sum(r['screening_passed'] for r in rows)
c1,c2,c3=st.columns(3)
c1.metric('Selected recorded cases',f'{len(ids):,}')
c2.metric('Screening passes',f'{passed:,}')
c3.metric('Pass fraction in selection',f'{100*passed/len(ids):.2f}%' if len(ids) else 'No cases')
if passing!='All outcomes' or set(where['status'])!=set(outcomes):st.warning('Selection uses a recorded outcome. These are conditional descriptive statistics, not the unconditional Monte Carlo success rate.')
mode=st.radio('After a case stops',['all-recorded','evaluation-only'],format_func=lambda x:{'all-recorded':'Include all recorded motion (also after controller stops)','evaluation-only':'Use only samples through each recorded evaluation stop'}[x],horizontal=True)
metric=st.selectbox('Tilt channel',['tilt_total_deg','tilt_x_deg','tilt_y_deg'])
zoom=st.selectbox('Vertical view',['Automatic full range','0–5° near upright','0–0.5° near upright'])
y_scale=alt.Scale() if zoom=='Automatic full range' else alt.Scale(domain=[0,5 if zoom=='0–5° near upright' else .5])
if zoom!='Automatic full range':st.caption('The vertical view clips larger values. All selected cases still contribute to the unchanged percentile calculation and CSV export.')
if mode=='all-recorded':st.info('Every selected case contributes for all six seconds. After a stop, zero effort is sent and the body evolves freely; later tilt is not controlled balancing.')
else:st.warning('Stopped cases leave later percentile bands. Later bands condition on survivors. The evaluated sample count is included in tooltips and tables.')
records=[]
for campaign in campaigns:
    selected=[i for i in ids if dataset.cases[i]['campaign']==campaign]
    records+=quantile_records(dataset,quantiles(dataset,selected,mode,metric),campaign,mode,metric)
if not records:st.warning('No campaign selected.');st.stop()
frame=pd.DataFrame(records)
base=alt.Chart(alt.Data(values=json.loads(frame.to_json(orient='records')))).encode(x=alt.X('time_s:Q',title='Time (s)',scale=alt.Scale(domain=[0,6])),
    color=alt.Color('campaign:N',title='Campaign',scale=alt.Scale(domain=list(groups),range=['#1a62b8','#bd562c'])))
layers=[]
for coverage,opacity in [('100_0',.08),('99_7',.13),('95_5',.2),('68_3',.3)]:
    layers.append(base.mark_area(opacity=opacity,clip=True).encode(y=alt.Y('lo_'+coverage+':Q',title='Pose-derived tilt (°)',scale=y_scale),y2='hi_'+coverage+':Q'))
layers.append(base.mark_line(strokeWidth=1.7,clip=True).encode(y=alt.Y('median:Q',title='Pose-derived tilt (°)',scale=y_scale),tooltip=[
    alt.Tooltip('corner:N'),alt.Tooltip('campaign:N'),alt.Tooltip('time_s:Q',format='.3f'),alt.Tooltip('median:Q',format='.4f'),
    alt.Tooltip('lo_95_5:Q',title='2.25 percentile',format='.4f'),alt.Tooltip('hi_95_5:Q',title='97.75 percentile',format='.4f'),
    alt.Tooltip('selected:Q',title='Selected cases'),alt.Tooltip('count:Q',title='Contributing at time'),alt.Tooltip('evaluation_count:Q',title='Within evaluation interval')]))
chart=alt.layer(*layers).properties(width=280,height=210).facet(facet=alt.Facet('corner:N',title=None,sort=list(CORNERS)),columns=4)
st.altair_chart(chart,width='stretch')
st.caption('Bands: central 68.3%, 95.5%, 99.7% and 100% empirical coverage, darkest to lightest; line: median. All selected cases contribute. These pointwise percentiles are not confidence intervals or Gaussian assumptions.')
st.dataframe(pd.DataFrame(summarize(dataset,ids)),hide_index=True,width='stretch')
with st.expander('Plot every selected trajectory'):
    st.caption('No subsampling. This static export can contain thousands of paths per corner.')
    if st.checkbox('Draw every selected case'):
        import matplotlib.pyplot as plt
        for campaign in campaigns:
            fig,_=plot_bands(dataset,[i for i in ids if dataset.cases[i]['campaign']==campaign],mode=mode,metric=metric,trajectories=True,title=campaign)
            st.pyplot(fig);buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=160);plt.close(fig)
            st.download_button('Download '+campaign+' all-case figure',buffer.getvalue(),file_name=campaign+'-all-case-tilt.png',mime='image/png')
with st.expander('Exact properties, gains and resolved inputs'):
    for name in campaigns:
        st.subheader(name);st.json(groups[name]['factors']);st.json(groups[name]['payload']['compiled'])
st.download_button('Download percentile CSV',frame.to_csv(index=False),file_name='selected-quantiles.csv',mime='text/csv')
st.download_button('Download exact selected cases',json.dumps(rows,indent=2),file_name='selected-cases.json',mime='application/json')
st.download_button('Download complete selection receipt',json.dumps({'where':where,'gpu_indices':gpu,'exact_seeds':sorted(seed_values) if seed_values is not None else None,
    'mode':mode,'metric':metric,'vertical_view':zoom,'indices':[int(i) for i in ids],
    'source_cache_sha256':sha256(dataset.root/'checksums.json'),
    'input_digests':{k:g['payload']['compiled']['input_digest'] for k,g in groups.items() if k in campaigns}},indent=2),file_name='selection-receipt.json',mime='application/json')
st.caption('The view reads an audited derived cache. It cannot change requirements, archived simulation data, control gains, or solver settings.')
