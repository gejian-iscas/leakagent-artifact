"""Normalize a legally obtained local archive; output contains private identifiers."""
import argparse,csv,gzip,json
from collections import defaultdict
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--eligible-csv',type=Path,required=True,help='CSV or CSV.gz with user_id column; strict temporal cohort selection')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
opening=gzip.open if a.eligible_csv.suffix=='.gz' else open
with opening(a.eligible_csv,'rt') as f: eligible={r['user_id'] for r in csv.DictReader(f)}
streams=[]
for policy,folder in [('minilm','r011_memorycd_all_users'),('qwen','r012_qwen_memorycd_all_users'),('deepseek','r013_deepseek_memorycd_all_users')]:
    groups=defaultdict(list)
    with (a.archive/folder/'task_runs.jsonl').open() as f:
        for row in map(json.loads,f):
            if row['user_id'] in eligible:groups[row['user_id'],row.get('policy_seed',0)].append(row)
    for (user,seed),rows in sorted(groups.items()):
        stream=dict(policy=policy,user=user,seed=seed,history=[],future=[])
        for row in rows:
            if len(row['queries'])!=len(row['events']):raise ValueError('Mismatched queries/events')
            stream[row['task_role']].append(dict(id=row['task_id'],position=row['task_position'],events=[dict(query=q.casefold(),documents=e['access_pattern']) for q,e in zip(row['queries'],row['events'])]))
        if len(stream['history'])!=10 or len(stream['future'])!=5:raise ValueError('Expected ten histories and five futures')
        streams.append(stream)
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(streams)+'\n')
print(f'Wrote {len(streams)} private streams. Do not publish this output without data review.')
