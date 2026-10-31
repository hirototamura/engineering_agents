"""Plot pilot, trial-shard or campaign evidence without changing its metrics."""
from pathlib import Path
import argparse

def plot_pilot(run):
    import json
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows=json.loads((run/'telemetry.json').read_text())
    t=np.array([r['time_s'] for r in rows])
    tilt=np.array([r['tilt_deg'] for r in rows])
    rates=np.array([r['wheel_rad_s'] for r in rows])*30/np.pi
    torque=np.array([r['requested_torque_nm'] for r in rows])
    fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True,layout='constrained')
    fig.suptitle('Isaac Sim cube pilot — measured PhysX telemetry\nIdeal sensing; preliminary wiring check, not acceptance',fontsize=14)
    for i,label in enumerate(('x','y')): axes[0].plot(t,tilt[:,i],label=label)
    for i,label in enumerate(('x','y','z')):
        axes[1].plot(t,rates[:,i],label=label)
        axes[2].plot(t,torque[:,i],label=label)
    for ax,ylabel in zip(axes,('Tilt (degrees)','Reaction-wheel speed (rpm)','Requested torque (N m)')):
        ax.set_ylabel(ylabel); ax.grid(alpha=.25); ax.legend(loc='upper right')
    axes[-1].set_xlabel('Simulated time (s)')
    fig.savefig(run/'telemetry.png',dpi=160)
    print(run/'telemetry.png')
    plt.close("all")

def plot_trials(run):
    import json
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r=json.loads((run/'result.json').read_text());a=np.load(run/'telemetry.npz')
    fig,axes=plt.subplots(2,4,figsize=(15,7),sharex=True,sharey=True,layout='constrained')
    for i,(ax,row) in enumerate(zip(axes.flat,r['summaries'])):
        end=int(a['end_tick'][i])+1
        ax.plot(a['time_s'][:end],a['values'][:end,i,2],color='#197d83',label='Measured total tilt')
        ax.axhline(5,color='#c38d23',ls=':',label='5° screening limit')
        ax.axhline(20,color='#cb5143',ls='--',label='20° stop limit')
        ax.set(title=f"Corner {row['corner']} · {row['status'].replace('_',' ')}",xlabel='Time (s)',ylabel='Tilt (degrees)',ylim=(0,23))
    axes[0,0].legend(fontsize=8,loc='upper right')
    fig.suptitle('Eight-corner Isaac / PhysX demo · delayed noisy sensing\nEach curve ends at its recorded stop. Numerical model; hardware unverified.',fontsize=13)
    fig.savefig(run/'tilt-traces.png',dpi=160)
    plt.close("all")

def plot_campaign(campaign):
    import json
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    stats=json.loads((campaign/'statistics.json').read_text())
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
    fig.savefig(campaign/'statistics.png',dpi=170);plt.close(fig)
    plt.close("all")

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--kind', choices=['pilot', 'trials', 'campaign'], help='Default: detect from statistics.json, result.json or telemetry.json')
    args = parser.parse_args(argv)
    kind = args.kind
    if kind is None:
        matches = [k for k, filename in [('campaign', 'statistics.json'), ('trials', 'result.json'), ('pilot', 'telemetry.json')] if (args.run/filename).is_file()]
        if len(matches) != 1:
            parser.error('Cannot determine plot kind uniquely; use --kind')
        kind = matches[0]
    {'pilot': plot_pilot, 'trials': plot_trials, 'campaign': plot_campaign}[kind](args.run)

if __name__ == '__main__':
    main()
