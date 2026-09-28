"""Chronological MiniLM action replay through real encrypted HTTP object reads."""
import argparse,csv,gzip,json,multiprocessing as mp,secrets,subprocess,sys,time
from collections import Counter,defaultdict
from pathlib import Path
from urllib.request import Request,urlopen
import pyarrow.parquet as pq
from run_object_observation_witness import serve,RemoteIndex,ForwardPrivateKeywordIndex,ForwardPrivateBM25,AESGCM
from memorycd_data import parse_interactions, terms
from privmemlab.trace import ServerTraceEvent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--eligible-csv',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--users',type=int,default=3)
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    with gzip.open(a.eligible_csv,'rt') as f:eligible=sorted({r['user_id'] for r in csv.DictReader(f)})[:a.users]
    runs=defaultdict(list)
    for r in map(json.loads,(a.archive/'r011_memorycd_all_users/task_runs.jsonl').open()):
        if r['user_id'] in eligible:runs[r['user_id']].append(r)
    results=[]
    for batch in pq.ParquetFile(a.archive/'memorycd_users_interactions.parquet').iter_batches(batch_size=1):
        user_data=batch.to_pylist()[0];user=user_data['user_id']
        if user not in eligible:continue
        uid=eligible.index(user);interactions=parse_interactions(user_data)
        out=a.output_dir/f'private_user_{uid}';out.mkdir(exist_ok=True);logs=out/'server_requests.jsonl';logs.write_text('')
        ctx=mp.get_context('spawn');parent,child=ctx.Pipe();proc=ctx.Process(target=serve,args=(child,str(logs)));proc.start()
        started=time.monotonic()
        try:
            if not parent.poll(20):raise TimeoutError('Server did not start')
            remote=RemoteIndex(f'http://127.0.0.1:{parent.recv()}')
            index=ForwardPrivateKeywordIndex(*(secrets.token_bytes(32) for _ in range(3)),server=remote)
            ranker=ForwardPrivateBM25(index);cipher=AESGCM(secrets.token_bytes(32));cursor=0;handles={};reverse={};postings=defaultdict(set)
            freq=Counter();order={};history_queries=set();truth=[];readcount=0;matched_events=0;mismatched_events=0;knowledge={}
            tasks=sorted(runs[user],key=lambda r:r['task_position']);assert len(tasks)==15
            for pos,r in enumerate(tasks):
                remote.task=pos
                while cursor<len(interactions) and interactions[cursor]['timestamp']<r['timestamp']:
                    doc=interactions[cursor];cursor+=1;logical=doc['record_id'];handle=secrets.token_hex(16)
                    handles[logical]=handle;reverse[handle]=logical
                    body=f"{doc['domain'].replace('_',' ')} {doc['review_title']} {doc['review_text']}"
                    tokenized=terms(body);nonce=secrets.token_bytes(12)
                    payload=json.dumps(dict(record_id=logical,body=body)).encode()
                    remote.post('/objects/put',dict(object_key=handle,ciphertext=(nonce+cipher.encrypt(nonce,payload,handle.encode())).hex()))
                    ranker.upsert(handle,tokenized)
                    for token in tokenized:postings[token].add(handle)
                new=set();repeated=set();taskdocs=set()
                for q,old in zip(r['queries'],r['events']):
                    report=ranker.search([q],top_k=5)
                    selected=[h for h in report.ids if h in postings[q]]
                    fetched=[]
                    for h in selected:
                        req=Request(remote.url+'/objects/'+h,headers={'X-Task-Sequence':str(pos)})
                        with urlopen(req,timeout=10) as response:raw=response.read()
                        content=json.loads(cipher.decrypt(raw[:12],raw[12:],h.encode()))
                        assert content['record_id']==reverse[h];fetched.append(content['record_id']);readcount+=1
                    # Old digests are only a post-execution reference; not used in retrieval.
                    old_ids=list(ServerTraceEvent.from_handles(session_id='audit',step=0,search_pattern='',handles=fetched,delta_ms=0).access_pattern)
                    if old_ids==old['access_pattern']:matched_events+=1
                    else:mismatched_events+=1
                    taskdocs.update(selected)
                    (repeated if q.casefold() in history_queries else new).update(selected)
                if pos<10:
                    freq.update(taskdocs)
                    for h in sorted(taskdocs,key=lambda h:reverse[h]):order.setdefault(h,len(order))
                if pos==9:
                    chosen=sorted(freq,key=lambda h:(-freq[h],order[h]))[:10]
                    knowledge={h:reverse[h] for h in chosen};(out/'initial_knowledge.json').write_text(json.dumps(knowledge))
                if pos>=10:truth.append(dict(task=pos,additional_labels=sorted(knowledge[h] for h in (new & knowledge.keys())-repeated),known_repeated_labels=sorted(knowledge[h] for h in repeated & knowledge.keys())))
                history_queries.update(q.casefold() for q in r['queries'])
            subprocess.run([sys.executable,str(Path(__file__).with_name('attack_object_tasks.py')),'--logs',str(logs),'--knowledge',str(out/'initial_knowledge.json'),'--output',str(out/'attack.json')],check=True)
            attack=json.loads((out/'attack.json').read_text());assert attack==truth
            (out/'client_truth.json').write_text(json.dumps(truth,indent=2))
            result=dict(user_index=uid,tasks=len(tasks),initial_mappings=len(knowledge),object_gets=readcount,
                archive_matching_events=matched_events,archive_differing_events=mismatched_events,
                additional_records=[len(r['additional_labels']) for r in attack],truth_mismatches=0,
                elapsed_seconds=round(time.monotonic()-started,2))
            results.append(result);(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
        finally:proc.terminate();proc.join()
    (a.output_dir/'summary.json').write_text(json.dumps(dict(policy='minilm',selection='first eligible users in lexicographic order, not selected for leakage',knowledge='ten highest historical task-frequency mappings; ties by historical encounter then logical ID',results=results,scope='Actual localhost service execution with chronological corpus and archived actions; not closed-loop generation or production deployment; population is the selected eligible cohort.'),indent=2)+'\n')

if __name__=='__main__':main()
