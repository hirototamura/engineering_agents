"""Standalone scientific figures; every selected case contributes to the bands."""
from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from .data import CORNERS,TILT_FIELDS
from .statistics import quantiles


def plot_bands(dataset,indices,*,mode='all-recorded',metric='tilt_total_deg',trajectories=False,title=None):
    bands=quantiles(dataset,indices,mode,metric);field=TILT_FIELDS.index(metric)
    fig,axes=plt.subplots(4,2,figsize=(12,15),sharex=True,sharey=True,layout='constrained')
    fig.set_facecolor('#faf9f5')
    colors={100.:'#eff3f3',99.7:'#dce7eb',95.5:'#b0ccd6',68.3:'#719fb2'}
    for ax,corner in zip(axes.flat,CORNERS):
        b=bands[corner]
        if trajectories and b['selected']:
            paths=np.array(dataset.tilt[b['ids'],:,field],dtype=float)
            if mode=='evaluation-only':
                ends=np.array([dataset.cases[i]['end_tick'] for i in b['ids']]);paths[np.arange(len(dataset.time))[None,:]>ends[:,None]]=np.nan
            ax.plot(dataset.time,paths.T,color='#152f4c',lw=.25,alpha=.018,rasterized=True,zorder=2.5)
        for coverage in (100.,99.7,95.5,68.3):
            lo,hi=b['bands'][coverage];ax.fill_between(dataset.time,lo,hi,color=colors[coverage],alpha=.85,zorder=2)
        ax.plot(dataset.time,b['median'],color='#24566d',lw=1.7,zorder=3)
        if metric=='tilt_total_deg':
            ax.axhline(5,color='#c48420',lw=.8,ls=':');ax.axhline(20,color='#b34c42',lw=.8,ls='--')
        ax.set_title(f"Corner {corner} · {b['selected']:,} selected\nWithin evaluation at final sample: {int(b['evaluation_count'][-1]):,}",fontsize=11,loc='left',pad=10)
        ax.set(xlabel='Time (s)',ylabel='Pose-derived tilt (°)',xlim=(dataset.time[0],dataset.time[-1]))
        ax.grid(alpha=.18)
        ax.spines[['top','right']].set_visible(False)
        ax.tick_params(labelbottom=True,labelleft=True)
    # Shared axes must be scaled after all corners have been added. Setting a
    # lower limit in the first panel otherwise freezes limits before failures
    # in later panels appear and clips the all-recorded percentile bands.
    if metric=='tilt_total_deg':
        maxima=[np.nanmax(b['bands'][100.][1]) for b in bands.values() if b['selected']]
        axes[0,0].set_ylim(0,max(21.,max(maxima,default=0)*1.04))
    legend=[Patch(facecolor=colors[c],label=f'{c:g}% central coverage') for c in (68.3,95.5,99.7,100.)]
    legend += [Line2D([0],[0],color='#24566d',label='Median')]
    if metric=='tilt_total_deg':
        legend += [Line2D([0],[0],color='#c48420',ls=':',label='5° peak screening limit'),
                   Line2D([0],[0],color='#b34c42',ls='--',label='20° stop threshold')]
    fig.legend(handles=legend,loc='outside lower center',ncol=3,frameon=False,fontsize=10)
    policy=('All recorded states, including free evolution after stopping; all selected cases at every time.' if mode=='all-recorded'
        else 'Evaluation interval only; stopped cases leave later bands. Changing denominators are shown; survivor bias applies.')
    fig.suptitle((title or 'Eight-corner Monte Carlo tilt trajectories')+'\n'+policy+'\nPointwise empirical percentiles; these are not confidence intervals.',fontsize=11)
    return fig,bands


def plot_comparison(dataset,first,second):
    fig,axes=plt.subplots(4,2,figsize=(12,15),sharex=True,sharey=True,layout='constrained')
    fig.set_facecolor('#faf9f5')
    from .statistics import select
    maximum=21.
    for label,color in [(first,'#24566d'),(second,'#b64628')]:
        b=quantiles(dataset,select(dataset,{'campaign':[label]}))
        for ax,corner in zip(axes.flat,CORNERS):
            lo,hi=b[corner]['bands'][95.5]
            ax.fill_between(dataset.time,lo,hi,color=color,alpha=.15)
            ax.plot(dataset.time,b[corner]['median'],color=color,lw=1.4,label=label)
            maximum=max(maximum,float(np.nanmax(hi))*1.04)
            ax.set(title='Corner '+corner,xlabel='Time (s)',ylabel='Pose-derived tilt (°)');ax.grid(alpha=.18)
            ax.spines[['top','right']].set_visible(False)
            ax.tick_params(labelbottom=True,labelleft=True)
    axes[0,0].set_ylim(0,maximum)
    axes[0,0].legend(fontsize=9)
    fig.suptitle('Paired design comparison · median and central 95.5% coverage\nAll recorded trajectories, including post-stop free evolution; descriptive exploration.',fontsize=13)
    return fig
