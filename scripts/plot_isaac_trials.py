"""Show per-corner measured tilt through each trial's recorded stopping point."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path);args=parser.parse_args()
r=json.loads((args.run/'result.json').read_text());a=np.load(args.run/'telemetry.npz')
fig,axes=plt.subplots(2,4,figsize=(15,7),sharex=True,sharey=True,layout='constrained')
for i,(ax,row) in enumerate(zip(axes.flat,r['summaries'])):
    end=int(a['end_tick'][i])+1
    ax.plot(a['time_s'][:end],a['values'][:end,i,2],color='#197d83',label='Measured total tilt')
    ax.axhline(5,color='#c38d23',ls=':',label='5° screening limit')
    ax.axhline(20,color='#cb5143',ls='--',label='20° stop limit')
    ax.set(title=f"Corner {row['corner']} · {row['status'].replace('_',' ')}",xlabel='Time (s)',ylabel='Tilt (degrees)',ylim=(0,23))
axes[0,0].legend(fontsize=8,loc='upper right')
fig.suptitle('Eight-corner Isaac / PhysX demo · delayed noisy sensing\nEach curve ends at its recorded stop. Numerical model; hardware unverified.',fontsize=13)
fig.savefig(args.run/'tilt-traces.png',dpi=160)
