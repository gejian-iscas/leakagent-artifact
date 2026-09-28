"""Exercise archive replay, rotation, padding, and summary with invented records."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import pyarrow as pa
import pyarrow.parquet as pq
from memorycd_data import DOMAINS
from privmemlab.trace import ServerTraceEvent

root=Path(__file__).resolve().parents[1]
out=root/'output/synthetic-service';archive=out/'archive';archive.mkdir(parents=True,exist_ok=True)
interactions={d:[] for d in DOMAINS}
for i in range(10):
    interactions[DOMAINS[0]].append(json.dumps(dict(timestamp=0,title=f'doc{i}',text=f'old{i} new{i} '+('x'*(i+2)))))
pq.write_table(pa.Table.from_pylist([dict(user_id='synthetic',interactions=interactions)]),archive/'memorycd_users_interactions.parquet')
runs=[]
for pos in range(15):
    i=pos if pos<10 else pos-10
    event=ServerTraceEvent.from_handles(session_id='synthetic',step=0,search_pattern='',handles=[f'synthetic:{i}'],delta_ms=0)
    runs.append(dict(user_id='synthetic',task_position=pos,task_role='history' if pos<10 else 'future',timestamp=100+pos,queries=[f'old{i}' if pos<10 else f'new{i}'],events=[dict(access_pattern=list(event.access_pattern))]))
for folder in ['r011_memorycd_all_users','r012_qwen_memorycd_all_users','r013_deepseek_memorycd_all_users']:
    target=archive/folder;target.mkdir(exist_ok=True)
    (target/'task_runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in runs))
eligible=out/'eligible.csv.gz'
with gzip.open(eligible,'wt') as f:f.write('user_id\nsynthetic\n')
base=[ '--archive',str(archive),'--eligible-csv',str(eligible)]
for name,script,extra in [('fixed','analyze_fixed_knowledge_persistence.py',[]),('stable','run_memorycd_object_pilot.py',['--users','1']),('rotated','run_memorycd_object_rotation.py',['--users','1','--rotate']),('padded','run_memorycd_object_rotation.py',['--users','1','--rotate','--padding-block','1024'])]:
    subprocess.run([sys.executable,str(Path(__file__).with_name(script)),*base,'--output-dir',str(out/name),*extra],check=True)
subprocess.run([sys.executable,str(Path(__file__).with_name('summarize_object_server_study.py')),'--stable',str(out/'stable'),'--rotation',str(out/'rotated'),'--padded',str(out/'padded'),'--client-summary',str(out/'fixed/summary.csv'),'--output-dir',str(out/'summary')],check=True)
s=json.loads((out/'summary/summary.json').read_text())
assert s['archive_differing_events']==0 and s['truth_mismatches']==0
assert s['stable_extra_records']==5 and s['rotated_direct_extra_records']==0
assert s['length_recovered_mappings']==10 and s['rotated_length_extra_records']==5
assert s['padded_recovered_mappings']==0 and s['padded_extra_records']==0
assert s['server_client_uniform_max_difference']<1e-12
print('PASS: synthetic service replay, fixed knowledge, length recovery, padding, and aggregation.')
