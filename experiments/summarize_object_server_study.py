"""Aggregate server-only observations and pair actual object rotation results."""
import argparse,json,csv
from collections import defaultdict
from math import comb
from pathlib import Path
import numpy as np

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stable',type=Path,required=True);p.add_argument('--rotation',type=Path,required=True);p.add_argument('--padded',type=Path,required=True);p.add_argument('--client-summary',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
stable=json.loads((a.stable/'summary.json').read_text())['results']
rotated=json.loads((a.rotation/'summary.json').read_text())['results']
padded=json.loads((a.padded/'summary.json').read_text())['results']
rows=[]
for user in stable:
    events=defaultdict(list);current=None;uid=user['user_index']
    for e in map(json.loads,(a.stable/f'private_user_{uid}'/'server_requests.jsonl').open()):
        if e['operation']=='lookup':
            q=e['tokens'][0]['address_key'] if e['tokens'] else None
            current=dict(query=q,documents=set());events[e['task']].append(current)
        elif e['operation']=='get':
            assert current is not None
            current['documents'].add(e['object_key'])
    anchors=set().union(*(e['documents'] for task,es in events.items() if task<10 for e in es))
    seen={e['query'] for task,es in events.items() if task<10 for e in es if e['query'] is not None}
    for task,es in sorted(events.items()):
        if task<10:continue
        novel=set().union(*(e['documents'] for e in es if e['query'] is not None and e['query'] not in seen))
        repeated=set().union(*(e['documents'] for e in es if e['query'] in seen))
        extra=(novel&anchors)-repeated;n=len(anchors);count=len(extra)
        for k in (1,5,10):
            assert n>=k
            hit=1-comb(n-count,k)/comb(n,k) if k<=n-count else 1.
            rows.append(dict(user=uid,offset=task-9,k=k,anchors=n,extra=count,uniform_hit=hit,uniform_records=count*k/n))
        seen.update(e['query'] for e in es if e['query'] is not None)
with (a.output_dir/'private_server_rows.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
rng=np.random.default_rng(20260928);curve=[]
for k in (1,5,10):
    for offset in range(1,6):
        v=np.array([r['uniform_hit'] for r in rows if r['k']==k and r['offset']==offset])
        boots=v[rng.integers(0,len(v),(2000,len(v)))].mean(axis=1);lo,hi=np.quantile(boots,[.025,.975])
        curve.append(dict(k=k,offset=offset,mean=float(v.mean()),ci_low=float(lo),ci_high=float(hi),users=len(v)))
with (a.output_dir/'server_uniform_curve.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(curve[0]));w.writeheader();w.writerows(curve)
client=list(csv.DictReader(a.client_summary.open()));max_difference=0.
for row in curve:
    expected=next(r for r in client if r['policy']=='minilm' and r['reference']=='all_prior' and r['selection']=='uniform' and int(r['k'])==row['k'] and r['metric']==f"coverage_lag{row['offset']}")
    max_difference=max(max_difference,abs(row['mean']-float(expected['mean'])))
assert max_difference<1e-12
paired=[];byuser={r['user_index']:r for r in stable}
for r in rotated:
    uid=r['user_index'];s=byuser[uid]
    assert s['additional_records']==r['semantic_possible_records']
    assert s['object_gets']==r['object_gets']
    assert r['archive_differing_events']==0 and r['length_false_labels']==0
    out=a.rotation/f'private_user_{uid}';known=json.loads((out/'initial_knowledge.json').read_text())
    logs=[json.loads(line) for line in (out/'server_requests.jsonl').open()]
    j=next(i for i,e in enumerate(logs) if e['operation']=='replace_objects');event=logs[j]
    updates=logs[j+1];assert updates['operation']=='put_index_batch'
    old=defaultdict(list);new=defaultdict(list)
    for key,length in event['old_objects']:old[length].append(key)
    for key,length in event['new_objects']:new[length].append(key)
    recovered=sum(len(keys)==1 and len(new[length])==1 and keys[0] in known for length,keys in old.items())
    paired.append(dict(index_rotation_ciphertext_bytes=updates['bytes'],index_rotation_entries=updates['entries'],user=uid,mappings=len(known),length_recovered_mappings=recovered,
        stable_extra=sum(s['additional_records']),rotated_direct_extra=sum(r['additional_records']),rotated_length_extra=sum(r['length_attack_records']),
        stable_hit_tasks=sum(n>0 for n in s['additional_records']),rotated_length_hit_tasks=sum(n>0 for n in r['length_attack_records']),
        **{k:r['rotation'][k] for k in ['rewrite_bytes','peak_object_bytes','elapsed_seconds','objects','equal_ciphertexts','same_keys']}))
padded_byuser={r['user_index']:r for r in padded}
assert set(padded_byuser)=={r['user'] for r in paired}
for row in paired:
    r=padded_byuser[row['user']]
    assert r['semantic_possible_records']==byuser[row['user']]['additional_records']
    assert r['archive_differing_events']==0 and r['length_false_labels']==0
    out=a.padded/f"private_user_{row['user']}"
    known=json.loads((out/'initial_knowledge.json').read_text())
    event=next(e for e in map(json.loads,(out/'server_requests.jsonl').open()) if e['operation']=='replace_objects')
    old=defaultdict(list);new=defaultdict(list);block=event['padding_block']
    for key,length in event['old_objects']:old[((length+block-1)//block)*block].append(key)
    for key,length in event['new_objects']:new[length].append(key)
    row['padded_recovered_mappings']=sum(len(keys)==1 and len(new[length])==1 and keys[0] in known for length,keys in old.items())
    row['padded_extra']=sum(r['length_attack_records'])
    row['padded_hit_tasks']=sum(n>0 for n in r['length_attack_records'])
    row['padded_object_bytes']=r['rotation']['rewrite_bytes']
    row['padded_rotation_seconds']=r['rotation']['elapsed_seconds']
    assert r['rotation']['unpadded_object_bytes']==row['rewrite_bytes']
with (a.output_dir/'private_paired.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
result=dict(padded_recovered_mappings=sum(r['padded_recovered_mappings'] for r in paired),server_client_uniform_max_difference=max_difference,stable_users=len(stable),stable_tasks=sum(r['tasks'] for r in stable),stable_queries=sum(r['archive_matching_events']+r['archive_differing_events'] for r in stable),
    stable_object_gets=sum(r['object_gets'] for r in stable),archive_differing_events=sum(r['archive_differing_events'] for r in stable),
    truth_mismatches=sum(r['truth_mismatches'] for r in stable),rotation_users=len(paired),
    rotation_initial_mappings=sum(r['mappings'] for r in paired),length_recovered_mappings=sum(r['length_recovered_mappings'] for r in paired),
    stable_extra_records=sum(r['stable_extra'] for r in paired),rotated_direct_extra_records=sum(r['rotated_direct_extra'] for r in paired),rotated_length_extra_records=sum(r['rotated_length_extra'] for r in paired),
    padded_extra_records=sum(r['padded_extra'] for r in paired),padded_hit_tasks=sum(r['padded_hit_tasks'] for r in paired),
    total_object_padding_ratio=sum(r['padded_object_bytes'] for r in paired)/sum(r['rewrite_bytes'] for r in paired),
    median_padded_rotation_seconds=float(np.median([r['padded_rotation_seconds'] for r in paired])),
    stable_hit_tasks=sum(r['stable_hit_tasks'] for r in paired),rotated_length_hit_tasks=sum(r['rotated_length_hit_tasks'] for r in paired),
    median_object_rewrite_bytes=float(np.median([r['rewrite_bytes'] for r in paired])),median_rotation_seconds=float(np.median([r['elapsed_seconds'] for r in paired])),
    median_index_rotation_ciphertext_bytes=float(np.median([r['index_rotation_ciphertext_bytes'] for r in paired])),
    scope='Stable full selected cohort; rotation first 30 eligible users; one object rotation at t0, preserved query identity. Object bytes exclude encrypted index rewrite. Local timings, not network benchmark. Length attack uses unique old/new lengths and no extra semantic mappings.')
(a.output_dir/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
