"""Portable core analysis of supplied document-access traces (Python 3.9+)."""
import argparse
from collections import defaultdict
from math import comb
import json
from pathlib import Path


def partial_probability(n, a, k):
    """Uniform k-of-n knowledge: probability of at least one of a extra records."""
    if not 0 <= a <= n or not 0 <= k <= n:
        raise ValueError('Require 0 <= a,k <= n')
    return 1 - comb(n-a, k) / comb(n, k) if k <= n-a else 1.0


def query_scoped(events):
    pairs = {}
    return [{'query': e['query'], 'documents': [pairs.setdefault((e['query'], d), len(pairs)) for d in e['documents']]} for e in events]


def restricted_view(events):
    queries, per_query = {}, defaultdict(dict)
    view = []
    for e in events:
        q = e['query']; qid = queries.setdefault(q, len(queries))
        ids = per_query[q]
        view.append((qid, [ids.setdefault(d, len(ids)) for d in e['documents']]))
    return view


def analyze(streams, budgets, fractions):
    records = []
    for stream in streams:
        history = sorted(stream['history'], key=lambda x: x['position'])
        events = [e for t in history + stream['future'] for e in t['events']]
        assert restricted_view(events) == restricted_view(query_scoped(events))
        for h in budgets:
            if h > len(history):
                raise ValueError(f'History budget {h} exceeds supplied history')
            chosen = history[-h:]
            queries = {e['query'] for t in chosen for e in t['events']}
            anchors = {d for t in chosen for e in t['events'] for d in e['documents']}
            for task in stream['future']:
                fq = {e['query'] for e in task['events']}
                novel = {d for e in task['events'] if e['query'] not in queries for d in e['documents']}
                repeated = {d for e in task['events'] if e['query'] in queries for d in e['documents']}
                extra = (novel & anchors) - repeated
                known_repeated = repeated & anchors
                assert extra.isdisjoint(known_repeated)
                assert extra | known_repeated == (novel | repeated) & anchors
                linked = any(not fq & {e['query'] for e in t['events']} and bool((novel | repeated) & {d for e in t['events'] for d in e['documents']}) for t in chosen)
                n, a = len(anchors), len(extra)
                records.append(dict(policy=stream['policy'], user=stream['user'], seed=stream['seed'], task=task['id'], history_budget=h, anchors=n, pairwise_disjoint_link=int(linked), additional_known_documents=a, repeat_known_documents=len(known_repeated), any_additional_known=int(bool(extra)), all_novel_with_known=int(not fq & queries and bool(novel & anchors)), partial=[dict(fraction=rho, mappings=round(n*rho), probability=partial_probability(n,a,round(n*rho))) for rho in fractions]))
    # Match the paper's averaging order: futures/seeds within user, then users.
    metrics = ['anchors','pairwise_disjoint_link','additional_known_documents','repeat_known_documents','any_additional_known','all_novel_with_known']
    groups = defaultdict(lambda: defaultdict(list))
    for row in records:
        groups[row['policy'],row['history_budget']][row['user']].append(row)
    summary = []
    for (policy,h), users in sorted(groups.items()):
        summary.append(dict(policy=policy,history_budget=h,**{m:sum(sum(r[m] for r in rows)/len(rows) for rows in users.values())/len(users) for m in metrics}))
    return dict(records=records,summary=summary)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=Path('examples/traces.json'))
    p.add_argument('--config',type=Path,default=Path('examples/config.json'))
    p.add_argument('--output',type=Path,default=Path('output/results.json'))
    a=p.parse_args();config=json.loads(a.config.read_text())
    result=analyze(json.loads(a.input.read_text()),config['history_budgets'],config['mapping_fractions'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))
