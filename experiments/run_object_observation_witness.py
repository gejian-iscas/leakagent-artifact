"""Synthetic execution witness: encrypted index + real HTTP ciphertext GETs.

One query per task, static index, sequential client, one combined service operator.
Not a production deployment or full-cohort replay.
"""
import argparse
import json
import multiprocessing as mp
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from privmemlab.fpdsse import EncryptedUpdateServer, EpochSearchToken, ForwardPrivateKeywordIndex
from privmemlab.encrypted_bm25 import ForwardPrivateBM25
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def serve(conn, logpath):
    index=EncryptedUpdateServer();objects={};seq=0
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            return  # Structured request observations are written below.
        def do_POST(self):
            nonlocal seq
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/index/put':
                index.put(bytes.fromhex(data['address']),bytes.fromhex(data['ciphertext']))
                event=dict(operation='put_index',address=data['address'],bytes=len(bytes.fromhex(data['ciphertext'])))
                result={}
            elif self.path=='/index/put_batch':
                for address,ciphertext in data['entries']:index.put(bytes.fromhex(address),bytes.fromhex(ciphertext))
                event=dict(operation='put_index_batch',entries=len(data['entries']),bytes=sum(len(bytes.fromhex(c)) for _,c in data['entries']))
                result={}
            elif self.path=='/index/lookup':
                found=index.lookup([EpochSearchToken(t['epoch'],bytes.fromhex(t['address_key']),t['update_count']) for t in data['tokens']])
                result=dict(entries=[[a.hex(),c.hex()] for a,c in found])
                event=dict(operation='lookup',tokens=data['tokens'],returned_entries=len(found))
            elif self.path=='/objects/replace':
                replacement={k:bytes.fromhex(c) for k,c in data['objects']}
                old_bytes=sum(map(len,objects.values()));new_bytes=sum(map(len,replacement.values()))
                event=dict(operation='replace_objects',padding_block=data.get('padding_block',0),old_objects=[[k,len(c)] for k,c in objects.items()],
                    new_objects=[[k,len(c)] for k,c in replacement.items()],
                    equal_ciphertexts=len(set(objects.values()) & set(replacement.values())),
                    same_keys=len(objects.keys() & replacement.keys()),
                    rewrite_bytes=new_bytes,peak_object_bytes=old_bytes+new_bytes)
                objects.clear();objects.update(replacement)
                result={k:event[k] for k in ['equal_ciphertexts','same_keys','rewrite_bytes','peak_object_bytes']}
            elif self.path=='/objects/put':
                objects[data['object_key']]=bytes.fromhex(data['ciphertext'])
                event=dict(operation='put_object',object_key=data['object_key'],bytes=len(objects[data['object_key']]))
                result={}
            else:
                self.send_error(404);return
            self.finish_response(event,json.dumps(result).encode())
        def do_GET(self):
            if not self.path.startswith('/objects/'):
                self.send_error(404);return
            key=self.path.removeprefix('/objects/')
            if key not in objects:
                self.send_error(404);return
            self.finish_response(dict(operation='get',object_key=key,bytes=len(objects[key])),objects[key])
        def finish_response(self,event,body):
            nonlocal seq
            event.update(sequence=seq,time_ns=time.time_ns(),status=200);seq+=1
            if 'X-Task-Sequence' in self.headers:event['task']=int(self.headers['X-Task-Sequence'])
            with open(logpath,'a') as f:f.write(json.dumps(event)+'\n')
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',0),Handler)
    conn.send(server.server_port);conn.close();server.serve_forever()


class RemoteIndex:
    """Existing index storage interface transported over HTTP."""
    def __init__(self,url):self.url=url;self.task=None;self.pending=[]
    def post(self,path,data):
        headers={'Content-Type':'application/json'}
        if self.task is not None:headers['X-Task-Sequence']=str(self.task)
        req=Request(self.url+path,data=json.dumps(data).encode(),headers=headers)
        with urlopen(req,timeout=10) as r:return json.load(r)
    def put(self,address,ciphertext):
        self.pending.append([address.hex(),ciphertext.hex()])
    def lookup(self,tokens):
        if self.pending:
            self.post('/index/put_batch',dict(entries=self.pending));self.pending.clear()
        result=self.post('/index/lookup',dict(tokens=[dict(epoch=t.epoch,address_key=t.address_key.hex(),update_count=t.update_count) for t in tokens]))
        return [(bytes.fromhex(a),bytes.fromhex(c)) for a,c in result['entries']]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    logs=a.output_dir/'server_requests.jsonl';logs.write_text('')
    ctx=mp.get_context('spawn');parent,child=ctx.Pipe();proc=ctx.Process(target=serve,args=(child,str(logs)))
    proc.start()
    try:
        if not parent.poll(15):raise TimeoutError('Object server did not start')
        port=parent.recv();remote=RemoteIndex(f'http://127.0.0.1:{port}')
        index=ForwardPrivateKeywordIndex(*(secrets.token_bytes(32) for _ in range(3)),server=remote)
        ranker=ForwardPrivateBM25(index); cipher=AESGCM(secrets.token_bytes(32))
        docs=[('record-A','alpha beta gamma'),('record-B','alpha'),('record-C','delta'),('record-D','epsilon')]
        handles={label:secrets.token_hex(16) for label,_ in docs};terms={}
        for label,body in docs:
            handle=handles[label];tokens=body.split();terms[handle]=set(tokens)
            nonce=secrets.token_bytes(12);plain=json.dumps(dict(label=label,body=body)).encode()
            remote.post('/objects/put',dict(object_key=handle,ciphertext=(nonce+cipher.encrypt(nonce,plain,handle.encode())).hex()))
            ranker.upsert(handle,tokens)
        queries=['alpha','beta','delta','gamma','epsilon','beta']
        client=[];seen=set();knowledge={};known_labels=set()
        for i,q in enumerate(queries):
            report=ranker.search([q],top_k=5)
            selected=[h for h in report.ids if q in terms[h]]
            labels=[]
            for h in selected:
                with urlopen(remote.url+'/objects/'+h,timeout=10) as r:raw=r.read()
                content=json.loads(cipher.decrypt(raw[:12],raw[12:],h.encode()));labels.append(content['label'])
            if i==0:
                knowledge={handles['record-A']:'record-A'};known_labels={'record-A'}
                (a.output_dir/'initial_knowledge.json').write_text(json.dumps(knowledge))
            extra=sorted(set(labels)&known_labels) if q not in seen and i>0 else []
            client.append(dict(lookup=i,expected_labels=sorted(set(labels)&known_labels),expected_additional=extra))
            seen.add(q)
        attack=Path(__file__).with_name('attack_object_observation.py')
        subprocess.run([sys.executable,str(attack),'--logs',str(logs),'--knowledge',str(a.output_dir/'initial_knowledge.json'),'--output',str(a.output_dir/'attack.json')],check=True)
        inferred=json.loads((a.output_dir/'attack.json').read_text())
        assert len(inferred)==len(client)
        for actual,expected in zip(inferred,client):
            assert sorted(actual['identified_labels'])==expected['expected_labels']
            assert sorted(actual['additional_labels'])==expected['expected_additional']
        assert [r['lookup'] for r in inferred if r['additional_labels']]==[1,3]
        # Truth is saved only after the standalone attacker has exited.
        (a.output_dir/'client_truth.json').write_text(json.dumps(client,indent=2))
        requests=[json.loads(l) for l in logs.read_text().splitlines()]
        result=dict(status='passed',dataset='synthetic',server_process='independent HTTP process on localhost',
            executed_lookups=sum(r['operation']=='lookup' for r in requests),
            executed_object_gets=sum(r['operation']=='get' for r in requests),
            initial_mappings=1,future_tasks=5,future_identifications=sum(len(r['identified_labels']) for r in inferred[1:]),
            additional_identifications=sum(len(r['additional_labels']) for r in inferred[1:]),
            additional_task_offsets=[r['lookup'] for r in inferred if r['additional_labels']],
            truth_mismatches=0,query_identity='exact token-family equality for a static index',
            scope='Synthetic architecture witness only; no empirical prevalence, long-term claim, rotation or closed-loop agent evaluation.')
        (a.output_dir/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    finally:
        proc.terminate();proc.join()

if __name__=='__main__':main()
