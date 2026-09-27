"""Check hand-derived examples and enumerate all small mapping subsets."""
from itertools import combinations
import json
from math import isclose
from pathlib import Path
from analyze import analyze, partial_probability, query_scoped, restricted_view
root=Path(__file__).resolve().parent
config=json.loads((root/'examples/config.json').read_text())
result=analyze(json.loads((root/'examples/traces.json').read_text()),config['history_budgets'],config['mapping_fractions'])
expected=json.loads((root/'expected/demo.json').read_text())
for key,values in expected.items():
    for row,value in zip(result['records'],values):
        if key=='probabilities':
            assert all(isclose(x['probability'],y,abs_tol=1e-12) for x,y in zip(row['partial'],value))
        else:
            assert row[key]==value,(key,row[key],value)
assert isclose(result['summary'][0]['any_additional_known'],2/3)
witness=[dict(query='p',documents=['a']),dict(query='r',documents=['a'])]
scoped=query_scoped(witness)
assert restricted_view(witness)==restricted_view(scoped)
assert witness[0]['documents'][0]==witness[1]['documents'][0]
assert scoped[0]['documents'][0]!=scoped[1]['documents'][0]
for n in range(9):
    for a in range(n+1):
        for k in range(n+1):
            subsets=list(combinations(range(n),k))
            exact=sum(bool(set(x)&set(range(a))) for x in subsets)/len(subsets)
            assert isclose(partial_probability(n,a,k),exact,abs_tol=1e-12)
print('PASS: hand-derived disclosure cases, B preservation with F separation, exhaustive uniform-subset probabilities for n=0..8.')
