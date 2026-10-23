"""Render measured Isaac pilot telemetry as a standalone figure."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
args=parser.parse_args()
rows=json.loads((args.run/'telemetry.json').read_text())
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
fig.savefig(args.run/'telemetry.png',dpi=160)
print(args.run/'telemetry.png')
