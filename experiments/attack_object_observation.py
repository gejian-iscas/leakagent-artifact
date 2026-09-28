"""Direct mapping transfer from actual sequential server lookup/GET logs."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--logs',type=Path,required=True)
p.add_argument('--knowledge',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
knowledge=json.loads(a.knowledge.read_text())
queries={}; observations=[]; current=None
for line in a.logs.read_text().splitlines():
    e=json.loads(line)
    if e['operation']=='lookup':
        # Actual static-index token equality, not client query plaintext.
        sig=json.dumps(e['tokens'],sort_keys=True)
        q=queries.setdefault(sig,len(queries))
        current=dict(query=q,objects=[],labels=[]);observations.append(current)
    elif e['operation']=='get':
        assert current is not None
        current['objects'].append(e['object_key'])
        if e['object_key'] in knowledge:current['labels'].append(knowledge[e['object_key']])
seen=set();result=[]
for i,e in enumerate(observations):
    novel=e['query'] not in seen
    result.append(dict(lookup=i,query_identity=e['query'],novel_query=novel,identified_labels=e['labels'],
                       additional_labels=e['labels'] if novel and i>0 else []))
    seen.add(e['query'])
a.output.write_text(json.dumps(result,indent=2)+'\n')
