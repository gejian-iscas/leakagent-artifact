"""Fixed initial document knowledge: exact uniform expectations, no new labels."""
import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from itertools import combinations
from math import comb
from pathlib import Path
import numpy as np


def probability(n, a, k):
    return 1 - comb(n-a, k)/comb(n, k) if k <= n-a else 1.0


def metrics(anchors, extras, k, chosen=None):
    counts = {d: sum(d in e for e in extras) for d in anchors}
    gap = {d: any(b-a > 1 for a,b in zip(ix, ix[1:]))
           for d in anchors for ix in [[i for i,e in enumerate(extras) if d in e]]}
    weights = {d: k/len(anchors) if chosen is None else float(d in chosen) for d in anchors}
    result = dict(expected_distinct_records=sum(weights[d] for d,c in counts.items() if c),
                  identifications_per_mapping=sum(weights[d]*c for d,c in counts.items())/k,
                  reused_mapping_fraction=sum(weights[d] for d,c in counts.items() if c >= 2)/k,
                  intermittent_mapping_fraction=sum(weights[d] for d in anchors if gap[d])/k)
    for i, e in enumerate(extras, 1):
        result[f'coverage_lag{i}'] = probability(len(anchors),len(e),k) if chosen is None else float(bool(e & chosen))
        result[f'records_lag{i}'] = len(e)*k/len(anchors) if chosen is None else len(e & chosen)
    return result


def verify():
    anchors=set('abcd'); extras=[set('ab'),set('b'),set('ac'),set(),set('a')]
    for k in (1,2,3,4):
        exact=metrics(anchors,extras,k)
        enumerated=[metrics(anchors,extras,k,set(s)) for s in combinations(sorted(anchors),k)]
        for key,value in exact.items():
            assert abs(value-sum(x[key] for x in enumerated)/len(enumerated)) < 1e-12, key
    # The same query changes from novel to repeated after its first future use.
    seen={'old'}; events=[('fresh',{'a'})]
    first={d for q,ds in events if q not in seen for d in ds}
    seen.update(q for q,_ in events)
    second={d for q,ds in events if q not in seen for d in ds}
    assert first=={'a'} and second==set()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--eligible-csv',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();verify(); args.output_dir.mkdir(parents=True,exist_ok=True)
    with gzip.open(args.eligible_csv,'rt') as f: eligible={r['user_id'] for r in csv.DictReader(f)}
    records=[]; inventory=[]; diagnostics=[]
    for policy,folder in [('minilm','r011_memorycd_all_users'),('qwen','r012_qwen_memorycd_all_users'),('deepseek','r013_deepseek_memorycd_all_users')]:
        groups=defaultdict(list); total=0
        with (args.archive/folder/'task_runs.jsonl').open() as f:
            for r in map(json.loads,f):
                total+=1
                if r['user_id'] in eligible: groups[r['user_id'],r.get('policy_seed',0)].append(r)
        lengths=Counter(); excluded=0
        for (user,seed),rows in sorted(groups.items()):
            rows.sort(key=lambda r:r['task_position'])
            history=[r for r in rows if r['task_role']=='history']; future=[r for r in rows if r['task_role']=='future']
            lengths[len(history),len(future)]+=1
            assert len(history)==10 and len(future)==5
            assert max(r['timestamp'] for r in history) <= min(r['timestamp'] for r in future)
            assert all(len(r['queries'])==len(r['events']) for r in rows)
            freq=Counter(); first_order={}; initial=set()
            for r in history:
                taskdocs=set()
                for q,e in zip(r['queries'],r['events']):
                    initial.add(q.casefold())
                    for d in e['access_pattern']:
                        first_order.setdefault(d,len(first_order));taskdocs.add(d)
                freq.update(taskdocs)
            anchors=set(freq)
            if len(anchors)<10:
                excluded+=1; continue
            for reference in ('all_prior','initial_only'):
                seen=set(initial); extras=[]; allnew=[]
                for r in future:
                    events=[(q.casefold(),set(e['access_pattern'])) for q,e in zip(r['queries'],r['events'])]
                    novel=set().union(*(ds for q,ds in events if q not in seen))
                    repeated=set().union(*(ds for q,ds in events if q in seen))
                    extra=(novel & anchors)-repeated;extras.append(extra)
                    allnew.append(not any(q in seen for q,_ in events))
                    if reference=='all_prior':seen.update(q for q,_ in events)
                diagnostics.append(dict(policy=policy,user=user,seed=seed,reference=reference,anchors=len(anchors),
                    elapsed_days=[(r['timestamp']-history[-1]['timestamp'])/86400000 for r in future],
                    all_new_tasks=allnew,full_knowledge_extra=[len(e) for e in extras]))
                for k in (1,5,10):
                    for selection in ('uniform','historical_high','historical_low'):
                        chosen=None
                        if selection!='uniform':
                            sign=-1 if selection=='historical_high' else 1
                            chosen=set(sorted(anchors,key=lambda d:(sign*freq[d],first_order[d]))[:k])
                        records.append(dict(policy=policy,user=user,seed=seed,reference=reference,k=k,selection=selection,
                                            **metrics(anchors,extras,k,chosen)))
        inventory.append(dict(policy=policy,total_archive_tasks=total,eligible_users=len({u for u,s in groups}),
            streams=len(groups),history_future_stream_counts={f'{h}/{f}':n for (h,f),n in lengths.items()},
            streams_with_fewer_than_ten_anchors=excluded))
    # Private per-user results remain local, aggregate files are separately identified.
    with gzip.open(args.output_dir/'private_records.jsonl.gz','wt') as f:
        for r in records:f.write(json.dumps(r)+'\n')
    with gzip.open(args.output_dir/'private_diagnostics.jsonl.gz','wt') as f:
        for r in diagnostics:f.write(json.dumps(r)+'\n')
    keys=['policy','reference','k','selection']; grouped=defaultdict(lambda:defaultdict(list))
    for r in records:grouped[tuple(r[x] for x in keys)][r['user']].append(r)
    metricnames=[x for x in records[0] if x not in keys+['user','seed']]
    summary=[];rng=np.random.default_rng(20260927)
    for key,users in sorted(grouped.items()):
        matrix=np.array([[np.mean([r[m] for r in rows]) for m in metricnames] for rows in users.values()])
        boots=matrix[rng.integers(0,len(matrix),size=(2000,len(matrix)))].mean(axis=1)
        low,high=np.quantile(boots,[.025,.975],axis=0)
        for j,m in enumerate(metricnames):
            summary.append(dict(zip(keys,key),metric=m,mean=float(matrix[:,j].mean()),ci_low=float(low[j]),ci_high=float(high[j]),users=len(users)))
    with (args.output_dir/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    paired=[]; rng=np.random.default_rng(20260927)
    for policy in ('deepseek','minilm','qwen'):
        users=grouped[policy,'all_prior',10,'uniform']
        differences=np.array([np.mean([r['coverage_lag5']-r['coverage_lag1'] for r in rows]) for rows in users.values()])
        draws=differences[rng.integers(0,len(differences),(2000,len(differences)))].mean(axis=1)
        lo,hi=np.quantile(draws,[.025,.975])
        paired.append(dict(policy=policy,difference=float(differences.mean()),ci_low=float(lo),ci_high=float(hi)))
    with (args.output_dir/'paired_lag5_minus_lag1.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
    report=dict(inventory=inventory,verification='exact uniform expectations agree with exhaustive subsets; sequential novelty sanity passed',
        uncertainty='2000 user-cluster bootstrap draws; seeds averaged within user; pointwise intervals',
        mapping_selection='fixed initial mappings, historical task frequency, ties by first historical encounter',
        limitations='Five future tasks; client-selected trace analysis, not server observation. No inference of expiry from last hit.')
    (args.output_dir/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
