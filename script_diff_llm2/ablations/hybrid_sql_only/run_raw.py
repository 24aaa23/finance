#!/usr/bin/env python3
"""SQL-only ablation of the main pipeline, with isolated sequential workers."""
import argparse
import csv
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import re
from datetime import datetime
from retry_support import is_transient_failure, error_summary

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0,str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('hybrid_launcher',ROOT / 'ablations/v5_test1000/run_raw.py')
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)
from script_diff_llm.evaluation.benchmark_io import load_input_samples
csv.field_size_limit(sys.maxsize)


def atomic(path, text):
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(text,encoding='utf-8')
    os.replace(temp,path)


def merge(folder, ids, workers):
    rows={}
    for i in range(workers):
        path=folder/f'worker_{i+1:02}/raw_pipeline.csv'
        if not path.exists():continue
        with path.open(newline='',encoding='utf-8') as f:
            for r in csv.DictReader(f):
                key=r['Sample Row ID']
                if key not in ids or key in rows:raise ValueError('Unknown or duplicate ID: '+key)
                rows[key]=r
    ordered=[rows[k] for k in ids if k in rows]
    if ordered:
        out=io.StringIO(newline='')
        w=csv.DictWriter(out,fieldnames=list(dict.fromkeys(k for r in ordered for k in r)))
        w.writeheader();w.writerows(ordered)
        atomic(folder/'raw_pipeline.csv',out.getvalue())
    return len(ordered)


def show_progress(folder, workers, seen, offsets):
    """Surface newly written results and in-flight API warnings."""
    for i in range(workers):
        worker=folder/f'worker_{i+1:02}'
        report=worker/'raw_pipeline.csv'
        if report.exists():
            with report.open(newline='',encoding='utf-8') as handle:
                for row in csv.DictReader(handle):
                    key=(i,row['Sample Row ID'])
                    version=(row.get('Started At'),row.get('New Status'),row.get('Elapsed Seconds'))
                    if seen.get(key)==version:continue
                    seen[key]=version
                    prefix=f"[{datetime.now().strftime('%H:%M:%S')}] worker_{i+1:02} query={row['Sample Row ID']} status={row.get('New Status')} elapsed={row.get('Elapsed Seconds')}s"
                    print(prefix,flush=True)
                    if row.get('New Status')!='PIPELINE_SUCCESS':
                        print(f"  ERROR stage={row.get('Failure Stage')} retryable_api={is_transient_failure(row)}: {error_summary(row)}",flush=True)
        log=worker/'pipeline.log'
        if log.exists():
            with log.open('rb') as handle:
                handle.seek(offsets.get(i,0))
                chunk=handle.read()
                offsets[i]=handle.tell()
            for line in chunk.decode('utf-8',errors='replace').splitlines():
                if 'API error:' in line or 'Error code: 429' in line or 'Request timed out' in line:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] API WARNING worker_{i+1:02}: {line.strip()[:900]}",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model',choices=hybrid.MODELS,nargs='?',default='gpt_oss_120b')
    p.add_argument('condition',choices=hybrid.CONDITIONS,nargs='?',default='without_context')
    p.add_argument('--workers',type=int,choices=range(1,9),default=4)
    p.add_argument('--max-active-workers',type=int,choices=range(1,9),default=None,
                   help='Concurrent processes; retain the existing worker shards')
    p.add_argument('--run-tag',default='run_01')
    p.add_argument('--no-retry-api-errors',action='store_true',
                   help='Skip previously saved API failures instead of retrying them')
    p.add_argument('--check',action='store_true',help='Offline input and config checks; no model calls')
    args=p.parse_args()
    def interrupt(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupt)
    signal.signal(signal.SIGHUP,interrupt)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.run_tag):p.error('Invalid run-tag')
    concurrency=args.max_active_workers or args.workers
    if concurrency>args.workers:p.error('max-active-workers cannot exceed workers')
    hybrid.load_local_env_file()
    native=hybrid.parse_args([args.model,args.condition,'--workers','1','--run-tag',args.run_tag])
    env,_,experiment=hybrid.build_environment(native,os.environ)
    folder=BASE/'runs'/args.model/args.condition/args.run_tag
    env.update(SQL_ONLY_RETRY_API_ERRORS='0' if args.no_retry_api_errors else '1',
               PIPELINE_BACKEND_MODE='sql_only',DOMAIN_CONTEXT_CACHE_DIR=str(BASE/'context_cache'/args.model),
               GPT_OSS_LLM_GRADER_PIPELINE_VERSION='ablation-hybrid-sql-only-v1')
    config=json.loads(json.dumps(hybrid.manifest_for(native,env,experiment)))
    config['configuration'].update(backend_mode='sql_only',process_workers=args.workers,
                                  context_cache_dir=env['DOMAIN_CONTEXT_CACHE_DIR'])
    config.pop('signature',None)
    frame=load_input_samples(str(hybrid.SOURCES['INPUT_SAMPLE_FILE']),'ALL_BENCHMARK_SHEETS')
    ids=frame['global_question_id'].astype(str).tolist()
    if len(ids)!=1000 or len(set(ids))!=1000:raise ValueError('Expected 1000 unique questions')
    if args.check:
        print(f'Validated 1000 questions; {args.workers} sequential workers; {args.model}; {args.condition}; SQL only; no Fuseki needed.')
        return 0
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=folder/'run_manifest.json'
        if manifest.exists():
            if json.loads(manifest.read_text())!=config:raise ValueError('Configuration changed; use a new run-tag')
        else:
            for i in range(args.workers):
                worker=folder/f'worker_{i+1:02}';worker.mkdir(exist_ok=True)
                frame.iloc[i::args.workers].to_csv(worker/'questions.csv',index=False)
            atomic(manifest,json.dumps(config,indent=2)+'\n')
        for i in range(args.workers):
            shard=folder/f'worker_{i+1:02}/questions.csv'
            if shard.read_text() != frame.iloc[i::args.workers].to_csv(index=False):
                raise ValueError('Worker input changed: '+str(shard))
        command=[sys.executable,'-u','-B',str(BASE/'run_worker.py'),str(experiment)]
        if args.condition=='with_context':
            prep=folder/'preparation';prep.mkdir(exist_ok=True)
            prep_env=dict(env,DOMAIN_CONTEXT_PREPARE_ONLY='1',PIPELINE_OUTPUT_DIR=str(prep),
                          REPORT_FILE=str(prep/'raw_pipeline.csv'))
            with (prep/'pipeline.log').open('a') as log:
                print('Preparing/reusing SQL-only context; see',prep/'pipeline.log',flush=True)
                subprocess.run(command,cwd=ROOT,env=prep_env,stdout=log,stderr=subprocess.STDOUT,check=True)
        seen={};offsets={}
        for i in range(args.workers):
            worker=folder/f'worker_{i+1:02}'
            report=worker/'raw_pipeline.csv'
            if report.exists():
                with report.open(newline='',encoding='utf-8') as handle:
                    rows=list(csv.DictReader(handle))
                for row in rows:
                    seen[(i,row['Sample Row ID'])]=(row.get('Started At'),row.get('New Status'),row.get('Elapsed Seconds'))
                retry_count=sum(is_transient_failure(row) for row in rows)
                print(f"worker_{i+1:02}: {len(rows)} saved; {retry_count} transient API failures {'will retry' if not args.no_retry_api_errors else 'will skip'}",flush=True)
                if retry_count and not args.no_retry_api_errors:
                    backup=worker/'backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    backup.mkdir(parents=True)
                    atomic(backup/'raw_pipeline.csv',report.read_text())
                    print('  Saved pre-retry backup:',backup/'raw_pipeline.csv',flush=True)
            log=worker/'pipeline.log'
            offsets[i]=log.stat().st_size if log.exists() else 0
        atomic(folder/'execution_options.json',json.dumps({
            'max_active_workers':concurrency,'retry_api_errors':not args.no_retry_api_errors,
            'worker_entry_sha256':hybrid.file_hash(BASE/'run_worker.py'),
            'retry_support_sha256':hybrid.file_hash(BASE/'retry_support.py'),
            'started_at':datetime.now().isoformat()},indent=2)+'\n')
        children=[];handles=[]
        try:
            pending=list(range(args.workers))
            print(f'Maximum active workers: {concurrency}; retaining {args.workers} original shards',flush=True)
            while pending or any(c.poll() is None for c in children):
                while pending and sum(c.poll() is None for c in children)<concurrency:
                    i=pending.pop(0)
                    worker=folder/f'worker_{i+1:02}'
                    worker_env=dict(env,INPUT_SAMPLE_FILE=str(worker/'questions.csv'),INPUT_SAMPLE_SHEET='',
                                    PIPELINE_OUTPUT_DIR=str(worker),REPORT_FILE=str(worker/'raw_pipeline.csv'),
                                    RAW_REPORT_FILE=str(worker/'raw_pipeline.csv'),TEST_QUERY_OFFSET='0',
                                    TEST_QUERY_LIMIT='1000',TEST_MAX_WORKERS='1',DOMAIN_CONTEXT_PREPARE_ONLY='')
                    handle=(worker/'pipeline.log').open('a');handles.append(handle)
                    child=subprocess.Popen(command,cwd=ROOT,env=worker_env,stdout=handle,
                                           stderr=subprocess.STDOUT,start_new_session=True)
                    children.append(child)
                    print(f'Worker {i+1}: PID {child.pid}, {len(frame.iloc[i::args.workers])} questions',flush=True)
                show_progress(folder,args.workers,seen,offsets)
                print(f'{merge(folder,ids,args.workers)}/1000 saved',flush=True)
                time.sleep(2)
        finally:
            for c in children:
                if c.poll() is None:os.killpg(c.pid,signal.SIGINT)
            for c in children:
                try:c.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(c.pid,signal.SIGTERM);c.wait()
            for h in handles:h.close()
            show_progress(folder,args.workers,seen,offsets)
            print(f'{merge(folder,ids,args.workers)}/1000 saved: {folder / "raw_pipeline.csv"}',flush=True)
        if any(c.returncode for c in children):return 1
        if merge(folder,ids,args.workers)!=1000:raise RuntimeError('Run ended without all 1000 rows; inspect worker logs')
        return 0


if __name__=='__main__':raise SystemExit(main())
