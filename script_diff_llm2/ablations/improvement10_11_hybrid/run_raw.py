#!/usr/bin/env python3
"""Isolated Improvement 10/11 hybrid ablation; GPT-OSS, raw output only."""
import argparse
import csv
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
DERIVED=BASE/'derived'
SQL_SOURCE=ROOT/'ablations/improvement10_models/source/improvement10'
KG_SOURCE=ROOT/'ablations/improvement11_gpt_oss_120b/source/improvemnt11kgfixed'
sys.dont_write_bytecode=True
csv.field_size_limit(sys.maxsize)
sys.path.insert(0,str(ROOT/'src'))
from script_diff_llm.config.runtime import load_local_env_file


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_originals():
    manifest=json.loads((BASE/'derivation_manifest.json').read_text())
    for item in manifest['files'].values():
        if digest(ROOT.parent/item['original'])!=item['sha256']:
            raise RuntimeError('Original snapshot changed: '+item['original'])


def atomic(path,text):
    tmp=path.with_name(path.name+'.tmp');tmp.write_text(text,encoding='utf-8');os.replace(tmp,path)


def read_rows(path):
    if not path.exists():return []
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def merge(folder,ids,workers):
    rows={}
    for i in range(workers):
        for row in read_rows(folder/f'worker_{i+1:02}/raw_pipeline.csv'):
            key=str(row['Sample Row ID'])
            if key not in ids or key in rows:raise ValueError('Unknown/duplicate output ID: '+key)
            rows[key]=row
    ordered=[rows[k] for k in ids if k in rows]
    if ordered:
        out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=list(dict.fromkeys(k for r in ordered for k in r)))
        w.writeheader();w.writerows(ordered);atomic(folder/'raw_pipeline.csv',out.getvalue())
    return len(ordered)


def command(questions,output,cache=None):
    cmd=[sys.executable,'-u','-B',str(DERIVED/'run_pipeline_v3_sql/run.py'),
         '--db',str(SQL_SOURCE/'wealth_management_diverse.db'),
         '--yaml-dir',str(SQL_SOURCE/'table_medatada'),
         '--domain-intro',str(SQL_SOURCE/'domain_intro_latest.prompt'),
         '--business-rules',str(SQL_SOURCE/'business_rules_addendum.md'),
         '--questions',str(questions),'--output',str(output),'--knowledge-mode','simple',
         '--agent-consultation','on']
    if cache:cmd+=['--knowledge-cache',str(cache)]
    return cmd


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-tag',default='run_01')
    p.add_argument('--provider',choices=('bedrock','azure'),default='bedrock')
    p.add_argument('--workers',type=int,choices=range(1,9),default=4)
    p.add_argument('--max-active-workers',type=int,choices=range(1,9),default=2)
    p.add_argument('--check',action='store_true')
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',a.run_tag):p.error('Invalid run-tag')
    if a.max_active_workers>a.workers:p.error('max-active-workers exceeds workers')
    verify_originals()
    load_local_env_file()
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','JAVA_HOME','LANG','USER','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','HTTP_PROXY','NO_PROXY'}}
    key=next((os.getenv(k) for k in ['AWS_BEDROCK_API_KEY','AWS_Bedrock_API_gpt_oss_120b','BEDROCK_API_KEY'] if os.getenv(k)),'')
    if a.provider=='bedrock' and not a.check and not key:raise RuntimeError('Missing Bedrock credentials in environment/local .env')
    endpoint=os.getenv('BEDROCK_BASE_URL') or 'https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1'
    model='openai.gpt-oss-120b-1:0'
    if a.provider=='azure':
        azure_spec=importlib.util.spec_from_file_location('azure_settings',ROOT/'ablations/azure_gpt_oss_120b/run_raw.py')
        azure=importlib.util.module_from_spec(azure_spec);azure_spec.loader.exec_module(azure)
        azure.load_azure_env()
        key=os.getenv('AZURE_OPENAI_API_KEY','')
        endpoint=azure.inference_url(os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('AZURE_FOUNDRY_ENDPOINT') or '')
        model=os.getenv('AZURE_GPT_OSS_DEPLOYMENT','')
        if not model or (not a.check and not key):raise RuntimeError('Azure deployment/key missing from azure.env')
    folder=BASE/('runs/azure_gpt_oss_120b' if a.provider=='azure' else 'runs/gpt_oss_120b')/a.run_tag;folder.mkdir(parents=True,exist_ok=True)
    runtime=folder/'runtime';cache_dir=runtime/'knowledge'
    env.update(AWS_BEDROCK_API_KEY=key,BEDROCK_BASE_URL=endpoint,
               BEDROCK_GPT_OSS_MODEL=model,PYTHONDONTWRITEBYTECODE='1',
               KNOWLEDGE_CACHE_DIR=str(cache_dir),PIPELINE_RUNTIME_DIR=str(runtime),
               HYBRID_RUNTIME_DIR=str(runtime),ONTOLOGY_FILE=str(KG_SOURCE/'kg_output_fixed/wealth_management_diverse_schema.ttl'),
               INSTANCE_FILE=str(KG_SOURCE/'kg_output_fixed/wealth_management_diverse_kg.ttl'),
               SPARQL_ENDPOINT='http://127.0.0.1:3041/improvemnt11kgfixed/query',
               TEST_MAX_WORKERS='1',TEST_QUERY_OFFSET='0',RETRY_QUERY_SPEC_ERRORS_ONLY='0',QUERY_SHUFFLE_SEED='')
    spec=importlib.util.spec_from_file_location('original_dataset',SQL_SOURCE/'run_all.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    questions,summary=module.prepare_dataset(SQL_SOURCE/'datatset/wealth_management_1000_test_set_questions.xlsx',
                                             SQL_SOURCE/'datatset/216_questions_full_results.json',folder)
    records=[json.loads(l) for l in questions.read_text().splitlines() if l.strip()]
    ids=[str(r['Sample Row ID']) for r in records]
    if len(ids)!=1000 or len(set(ids))!=1000:raise ValueError('Expected 1000 unique questions')
    implementation={str(f.relative_to(BASE)):digest(f) for f in sorted(DERIVED.rglob('*.py'))}
    assets={str(f):digest(f) for f in [SQL_SOURCE/'wealth_management_diverse.db',
            SQL_SOURCE/'domain_intro_latest.prompt',SQL_SOURCE/'business_rules_addendum.md',
            KG_SOURCE/'kg_output_fixed/wealth_management_diverse_schema.ttl',
            KG_SOURCE/'kg_output_fixed/wealth_management_diverse_kg.ttl',questions]}
    for f in sorted((SQL_SOURCE/'table_medatada').iterdir()):
        if f.suffix.lower() in {'.yaml','.yml'}:assets[str(f)]=digest(f)
    config={'implementation':implementation,'assets':assets,'workers':a.workers,'model':env['BEDROCK_GPT_OSS_MODEL'],
            'endpoint':endpoint,'sparql_endpoint':env['SPARQL_ENDPOINT'],'knowledge_mode':'simple','grader':'not launched'}
    if a.provider=='azure':config['provider']='azure-openai-v1'
    manifest=folder/'run_manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())!=config:raise ValueError('Inputs/code changed; use a new run-tag')
    if a.check:
        print('[CHECK] 1000 questions; checking combined SQL/KG metadata and documents; no model calls.',flush=True)
        result=subprocess.run(command(questions,folder/'raw_pipeline.csv')+['--check-inputs'],env=env,cwd=DERIVED)
        verify_originals();return result.returncode
    with (folder/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def stop(signum,frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGHUP,stop)
        if not manifest.exists():
            for i in range(a.workers):
                worker=folder/f'worker_{i+1:02}';worker.mkdir(exist_ok=True)
                atomic(worker/'questions.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records[i::a.workers]))
            atomic(manifest,json.dumps(config,indent=2)+'\n')
        for i in range(a.workers):
            expected=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records[i::a.workers])
            if (folder/f'worker_{i+1:02}/questions.jsonl').read_text()!=expected:raise ValueError('Worker inputs changed')
        print('[PREPARE] Compiling/reusing one combined domain+rules+SQL YAML+ontology cache.',flush=True)
        subprocess.run(command(questions,folder/'preparation.csv')+['--prepare-knowledge'],env=env,cwd=DERIVED,check=True)
        caches=[f for f in cache_dir.glob('*.json') if re.fullmatch(r'[0-9a-f]{64}\.json',f.name)]
        if len(caches)!=1:raise ValueError('Expected one prepared hybrid cache')
        cache=caches[0]
        subprocess.run(command(questions,folder/'preparation.csv',cache)+['--prepare-knowledge'],env=env,cwd=DERIVED,check=True)
        if a.prepare_only:return 0
        pending=list(range(a.workers));children=[];handles=[]
        try:
            while pending or any(c.poll() is None for c in children):
                while pending and sum(c.poll() is None for c in children)<a.max_active_workers:
                    i=pending.pop(0);worker=folder/f'worker_{i+1:02}'
                    handle=(worker/'pipeline.log').open('a');handles.append(handle)
                    child=subprocess.Popen(command(worker/'questions.jsonl',worker/'raw_pipeline.csv',cache),
                                           env=env,cwd=DERIVED,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                    children.append(child);print(f'[WORKER {i+1}] PID {child.pid}; sequential within shard',flush=True)
                print(f'[PROGRESS] {merge(folder,ids,a.workers)}/1000 saved',flush=True);time.sleep(5)
        finally:
            for c in children:
                if c.poll() is None:os.killpg(c.pid,signal.SIGINT)
            for c in children:
                try:c.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(c.pid,signal.SIGTERM);c.wait()
            for h in handles:h.close()
            print('[OUTPUT]',folder/'raw_pipeline.csv',merge(folder,ids,a.workers),'rows',flush=True)
            verify_originals()
        if any(c.returncode for c in children):return 1
        if merge(folder,ids,a.workers)!=1000:raise RuntimeError('Incomplete run; inspect worker logs')
        return 0


if __name__=='__main__':raise SystemExit(main())
