"""Plot complete eight-corner campaign statistics and sampled trajectories."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path);args=parser.parse_args()
stats=json.loads((args.campaign/'statistics.json').read_text())
corners=list(stats['corners']); rows=list(stats['corners'].values())
plt.style.use('seaborn-v0_8-whitegrid')
fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
values=np.array([r['screening_pass_fraction'] for r in rows])*100
interval=np.array([r['wilson_95_ci'] for r in rows])*100
axes[0,0].bar(corners,values,color='#197d83',yerr=np.stack([values-interval[:,0],interval[:,1]-values]),capsize=4)
axes[0,0].set(title='Existing numerical screening gates',ylabel='Trials passing (%)',ylim=(0,105))
for i,v in enumerate(values): axes[0,0].text(i,v+2,f'{v:.1f}%',ha='center',fontsize=9)
bottom=np.zeros(8)
for status,color in [('completed','#197d83'),('lost_balance','#d65d47'),('lost_contact','#e6ad36'),('excessive_slip','#665b9c')]:
    counts=np.array([r['status_counts'].get(status,0) for r in rows])
    axes[0,1].bar(corners,counts,bottom=bottom,label=status.replace('_',' '),color=color);bottom+=counts
axes[0,1].set(title='Episode termination',ylabel='Trials');axes[0,1].legend(fontsize=8)
for key,ax,title in [('final_1s_tilt_rms_deg',axes[1,0],'Final one-second tilt RMS (degrees)'),('peak_wheel_rpm',axes[1,1],'Peak wheel speed (rpm)')]:
    median=np.array([r['quantiles'][key]['p50'] for r in rows]);lo=np.array([r['quantiles'][key]['p05'] for r in rows]);hi=np.array([r['quantiles'][key]['p95'] for r in rows])
    ax.errorbar(corners,median,yerr=[median-lo,hi-median],fmt='o',capsize=5,color='#197d83')
    ax.set(title=title,xlabel='Supported corner (body coordinates)',ylabel='Median and 5–95% range')
fig.suptitle(f"Isaac Sim / GPU PhysX · {stats['trial_count']:,} seeded trials · all eight corners\nExploratory numerical results; cross-backend agreement remains inconclusive; hardware unverified",fontsize=13)
fig.savefig(args.campaign/'statistics.png',dpi=170);plt.close(fig)
