#!/usr/bin/env python3
"""Run unchanged Improvement 11 on isolated question shards."""
import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import run_raw

sys.dont_write_bytecode = True
csv.field_size_limit(sys.maxsize)
BASE, SOURCE, PACKAGE = run_raw.BASE, run_raw.SOURCE, run_raw.PACKAGE


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, text):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


def read_rows(path):
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def merge(folder, questions, workers):
    rows = read_rows(folder / 'seed.csv')
    for i in range(workers):
        rows += read_rows(folder / f'worker_{i+1:02}' / 'raw_pipeline.csv')
    allowed = {q['global_question_id'] for q in questions}
    by_id = {}
    for row in rows:
        key = row['Sample Row ID']
        if key not in allowed or key in by_id:
            raise ValueError('Unknown or duplicate question ID: ' + key)
        by_id[key] = row
    ordered = [by_id[q['global_question_id']] for q in questions if q['global_question_id'] in by_id]
    if ordered:
        out = io.StringIO(newline='')
        writer = csv.DictWriter(out, fieldnames=list(dict.fromkeys(k for row in ordered for k in row)))
        writer.writeheader()
        writer.writerows(ordered)
        atomic(folder / 'raw_pipeline.csv', out.getvalue())
    return len(ordered)


def active_runs():
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = (proc / 'cmdline').read_bytes().decode().split('\0')
        except (OSError, UnicodeError):
            continue
        if str(PACKAGE / 'run.py') in args or str(BASE / 'run_raw.py') in args:
            found.append(proc.name)
    return found


def environment(endpoint):
    # Only system settings and explicitly selected credentials are inherited.
    allowed = {'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'JAVA_HOME', 'LD_LIBRARY_PATH',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}
    env = {k:v for k,v in os.environ.items() if k in allowed}
    keys = ['AWS_BEDROCK_API_KEY', 'AWS_Bedrock_API_gpt_oss_120b', 'BEDROCK_API_KEY']
    credentials = {k:os.environ[k] for k in keys if os.environ.get(k)}
    for path in [run_raw.ROOT / '.env', run_raw.ROOT / 'env/.env',
                 run_raw.ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/.env']:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            key, value = line.split('=',1)
            if key.strip() in keys:
                value = value.strip()
                value = value[1:].split(value[0],1)[0] if value.startswith(('"', "'")) else value.split('#',1)[0].strip()
                credentials.setdefault(key.strip(),value)
    key = next((credentials[k] for k in keys if credentials.get(k)),None)
    if not key:
        raise RuntimeError('Missing Bedrock credentials')
    env.update(AWS_BEDROCK_API_KEY=key, BEDROCK_BASE_URL=endpoint,
               BEDROCK_GPT_OSS_MODEL='openai.gpt-oss-120b-1:0', TEST_MAX_WORKERS='1',
               TEST_QUERY_OFFSET='0', RETRY_QUERY_SPEC_ERRORS_ONLY='0', PYTHONDONTWRITEBYTECODE='1')
    return env


def command(questions, output, cache):
    return [sys.executable, '-u', '-B', str(PACKAGE / 'run.py'),
            '--ontology', str(SOURCE / 'kg_output_fixed/wealth_management_diverse_schema.ttl'),
            '--kg-data', str(SOURCE / 'kg_output_fixed/wealth_management_diverse_kg.ttl'),
            '--domain-intro', str(SOURCE / 'domain_intro_latest.prompt'),
            '--business-rules', str(SOURCE / 'business_rules_addendum.md'),
            '--sparql-endpoint', 'http://127.0.0.1:3041/improvemnt11kgfixed/query',
            '--questions', str(questions), '--output', str(output),
            '--knowledge-mode', 'simple', '--knowledge-cache', str(cache)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--workers', type=int, choices=range(1,9), default=4)
    parser.add_argument('--max-active-workers', type=int, choices=range(1,9), default=None,
                        help='Limit concurrently running shards without changing existing assignments')
    parser.add_argument('--check', action='store_true', help='Offline cache, source and merge checks; no API calls')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('Invalid run-tag')
    concurrency = args.max_active_workers or args.workers
    if concurrency > args.workers:
        parser.error('max-active-workers cannot exceed workers')
    source = run_raw.verify()
    if not args.check and active_runs():
        raise RuntimeError('Stop the sequential Improvement 11 run first. Active PIDs: ' + ', '.join(active_runs()))
    parent = BASE / 'runs/gpt_oss_120b' / args.run_tag
    if not args.check:
        # Original compiler prepares/reuses the cache once, before any workers start.
        subprocess.run([sys.executable, '-u', '-B', str(BASE / 'run_raw.py'),
                        '--run-tag', args.run_tag, '--prepare-knowledge'], check=True)
    questions_file = parent / 'input_questions.jsonl'
    questions = [json.loads(line) for line in questions_file.read_text().splitlines() if line.strip()]
    ids = [q['global_question_id'] for q in questions]
    if len(ids) != 1000 or len(set(ids)) != 1000:
        raise ValueError('Expected 1000 unique questions')
    cache_dir = SOURCE / '.runtime/knowledge_v3_kg'
    caches = [p for p in cache_dir.glob('*.json') if re.fullmatch(r'[0-9a-f]{64}\.json',p.name)]
    if len(caches) != 1:
        raise ValueError('Expected exactly one prepared cache; inspect ' + str(cache_dir))
    cache = caches[0]
    payload = json.loads(cache.read_text())
    if not isinstance(payload.get('pack'), dict):
        raise ValueError('Prepared cache has no knowledge pack')
    # Preserve the original acceptance policy, including advisory review status.
    # The native explicit-cache validator checks its hash and schema binding.
    print('Knowledge review status:', payload['pack'].get('review_status', 'not_recorded'), flush=True)
    settings = json.loads((parent / 'launcher_manifest.json').read_text())
    folder = parent / f'parallel_workers{args.workers}'
    identity = {'workers':args.workers, 'source_commit':source['commit'],
                'input_sha256':digest(questions_file), 'cache_sha256':digest(cache),
                'model':settings['model'], 'endpoint':settings['endpoint']}
    if args.check:
        rows = read_rows(parent / 'raw_pipeline.csv')
        if len({r['Sample Row ID'] for r in rows}) != len(rows):
            raise ValueError('Duplicate sequential output IDs')
        if not {r['Sample Row ID'] for r in rows}.issubset(set(ids)):
            raise ValueError('Unknown sequential output IDs')
        print(f'Checks passed: 1000 questions, prepared cache, {len(rows)} sequential rows. No model calls.')
        return 0
    with (BASE / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = environment(settings['endpoint'])
        folder.mkdir(parents=True,exist_ok=True)
        manifest = folder / 'sharding_manifest.json'
        if manifest.exists():
            if json.loads(manifest.read_text()) != identity:
                raise ValueError('Sharding configuration changed; use a fresh run-tag')
        else:
            seed = parent / 'raw_pipeline.csv'
            atomic(folder / 'seed.csv',seed.read_text() if seed.exists() else '')
            # Validate seed identity before creating immutable worker assignments.
            merge(folder,questions,args.workers)
            completed = {r['Sample Row ID'] for r in read_rows(folder / 'seed.csv')}
            pending = [q for q in questions if q['global_question_id'] not in completed]
            for i in range(args.workers):
                worker = folder / f'worker_{i+1:02}'
                worker.mkdir(exist_ok=True)
                atomic(worker / 'questions.jsonl',''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in pending[i::args.workers]))
            atomic(manifest,json.dumps(identity,indent=2)+'\n')
        # Bind the selected cache using original validation before concurrent readers.
        subprocess.run(command(questions_file,folder/'preparation.csv',cache)+['--prepare-knowledge'],
                       env=env,cwd=SOURCE,check=True)
        children, handles = [], []
        try:
            pending_workers = []
            for i in range(args.workers):
                worker = folder / f'worker_{i+1:02}'
                assigned = [line for line in (worker/'questions.jsonl').read_text().splitlines() if line.strip()]
                if not assigned or len(read_rows(worker/'raw_pipeline.csv')) == len(assigned):
                    continue
                pending_workers.append((i,worker))
            print(f'Maximum active workers: {concurrency}; retaining {args.workers} original shards',flush=True)
            while pending_workers or any(c.poll() is None for c in children):
                while pending_workers and sum(c.poll() is None for c in children) < concurrency:
                    i,worker = pending_workers.pop(0)
                    handle = (worker/'launcher.log').open('a')
                    handles.append(handle)
                    child = subprocess.Popen(command(worker/'questions.jsonl',worker/'raw_pipeline.csv',cache),
                                             env=env,cwd=SOURCE,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                    children.append(child)
                    print(f'Started worker {i+1}: PID {child.pid}',flush=True)
                print(f'{merge(folder,questions,args.workers)}/1000 saved',flush=True)
                time.sleep(10)
        finally:
            for child in children:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGINT)
            for child in children:
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM)
                    child.wait()
            for handle in handles:
                handle.close()
            print(f'{merge(folder,questions,args.workers)}/1000 saved; {folder / "raw_pipeline.csv"}',flush=True)
            run_raw.verify()
        return int(any(c.returncode for c in children))


if __name__ == '__main__':
    raise SystemExit(main())
