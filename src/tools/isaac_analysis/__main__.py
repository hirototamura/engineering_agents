"""Agent tools: inventory, prepare, select, quantiles, report, and serve."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
from .data import factors, inspect_campaign, load, prepare, write_json, sha256
from .statistics import quantile_records, quantiles, select, summarize


def csv_write(path,rows):
    if not rows:return
    with Path(path).open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','inventory'):
        p=sub.add_parser(name);p.add_argument('--campaign',action='append',required=True,help='Unique label=campaign directory')
        if name=='prepare':p.add_argument('--output',type=Path,required=True)
    for name in ('select','quantiles','report','serve'):
        p=sub.add_parser(name);p.add_argument('--dataset',type=Path,required=True)
        if name in ('select','quantiles'):
            p.add_argument('--where',type=Path,help='JSON filter object');p.add_argument('--output',type=Path,required=True)
        if name=='quantiles':
            p.add_argument('--mode',choices=['all-recorded','evaluation-only'],default='all-recorded')
            p.add_argument('--metric',choices=['tilt_total_deg','tilt_x_deg','tilt_y_deg'],default='tilt_total_deg')
            p.add_argument('--all-trajectories',action='store_true')
        if name=='report':p.add_argument('--output',type=Path,required=True)
        if name=='serve':
            p.add_argument('--port',type=int,default=8526)
            p.add_argument('--report',type=Path,help='Standalone technical-report.html to read and download in the viewer')
    args=parser.parse_args()
    if args.command in ('prepare','inventory'):
        campaigns={}
        for token in args.campaign:
            label,sep,path=token.partition('=')
            if not sep or not label or label in campaigns:raise ValueError('Use unique label=directory arguments')
            campaigns[label]=Path(path)
        if args.command=='inventory':
            print(json.dumps({k:{'factors':factors(inspect_campaign(v)[2]),'manifest':inspect_campaign(v)[1]} for k,v in campaigns.items()},indent=2))
        else:
            dataset=prepare(campaigns,args.output);print(json.dumps({'dataset':str(args.output.resolve()),'cases':len(dataset.cases)}))
        return
    if args.command=='serve':
        import os
        env={**os.environ,'EA_ISAAC_DATASET':str(args.dataset.resolve())}
        if args.report:
            if not args.report.is_file() or args.report.suffix.lower()!='.html':
                parser.error('--report must point to an existing HTML report')
            env['EA_ISAAC_REPORT']=str(args.report.resolve())
        app=Path(__file__).with_name('app.py')
        subprocess.run([sys.executable,'-m','streamlit','run',str(app),'--server.address','127.0.0.1',
            '--server.port',str(args.port),'--server.headless','true','--browser.gatherUsageStats','false',
            '--theme.base','light','--theme.primaryColor','#24566d','--theme.backgroundColor','#faf9f5',
            '--theme.secondaryBackgroundColor','#f0f1eb','--theme.textColor','#202d34'],env=env,check=True)
        return
    dataset=load(args.dataset,verify=True)
    if args.command=='report':
        from .report import build
        build(dataset,args.output);print(args.output.resolve());return
    where=json.loads(args.where.read_text()) if args.where else {};ids=select(dataset,where)
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/'selection.json',{'where':where,'count':len(ids),'indices':ids.tolist(),'source_dataset':str(args.dataset.resolve()),
        'source_cache_sha256':sha256(args.dataset/'checksums.json'),
        'resolved_campaigns':{name:{'factors':g['factors'],'input_digest':g['payload']['compiled']['input_digest'],
            'controller':g['payload']['compiled']['controller']} for name,g in dataset.catalog['groups'].items()
            if any(dataset.cases[i]['campaign']==name for i in ids)}})
    write_json(args.output/'selected-cases.json',[dataset.cases[i] for i in ids])
    write_json(args.output/'summary.json',summarize(dataset,ids))
    if args.command=='quantiles':
        from .figures import plot_bands
        import matplotlib.pyplot as plt
        figure,bands=plot_bands(dataset,ids,mode=args.mode,metric=args.metric,trajectories=args.all_trajectories)
        figure.savefig(args.output/'tilt-percentiles.png',dpi=170);plt.close(figure)
        campaign=dataset.cases[ids[0]]['campaign'] if len(ids) else 'empty-selection'
        records=quantile_records(dataset,bands,campaign,args.mode,args.metric)
        csv_write(args.output/'quantiles.csv',records);write_json(args.output/'quantiles.json',records)
    print(json.dumps({'selected_cases':len(ids),'output':str(args.output.resolve())}))


if __name__=='__main__':main()
