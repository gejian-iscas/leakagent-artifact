"""Task-level mapping transfer using server-visible search tokens and object GETs."""
import argparse,json
from collections import defaultdict
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--logs',type=Path,required=True);p.add_argument('--knowledge',type=Path,required=True)
p.add_argument('--history-tasks',type=int,default=10);p.add_argument('--output',type=Path,required=True)
p.add_argument('--recover-length',action='store_true')
a=p.parse_args();known=json.loads(a.knowledge.read_text());tasks=defaultdict(list);current=None
for line in a.logs.read_text().splitlines():
    e=json.loads(line)
    if e['operation']=='replace_objects' and a.recover_length:
        old=defaultdict(list);new=defaultdict(list)
        block=e.get('padding_block',0)
        for key,length in e['old_objects']:
            expected=((length+block-1)//block)*block if block else length
            old[expected].append(key)
        for key,length in e['new_objects']:new[length].append(key)
        for length,keys in old.items():
            if len(keys)==1 and len(new[length])==1 and keys[0] in known:
                known[new[length][0]]=known[keys[0]]
    elif e['operation']=='lookup':
        # The first old epoch remains in subsequent search token families.
        q=e['tokens'][0]['address_key'] if e['tokens'] else None
        current=dict(query=q,objects=set());tasks[e['task']].append(current)
    elif e['operation']=='get':
        assert current is not None
        assert e['task'] in tasks
        current['objects'].add(e['object_key'])
seen=set();result=[]
for task,events in sorted(tasks.items()):
    new=set().union(*(e['objects'] for e in events if e['query'] is not None and e['query'] not in seen))
    repeat=set().union(*(e['objects'] for e in events if e['query'] in seen))
    extra=(new & known.keys())-repeat
    if task>=a.history_tasks:
        result.append(dict(task=task,additional_labels=sorted(known[d] for d in extra),known_repeated_labels=sorted(known[d] for d in repeat & known.keys())))
    seen.update(e['query'] for e in events if e['query'] is not None)
a.output.write_text(json.dumps(result,indent=2)+'\n')
