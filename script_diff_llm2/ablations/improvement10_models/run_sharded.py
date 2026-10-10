#!/usr/bin/env python3
"""Run unchanged Improvement 10 processes on isolated resumable question shards."""
import argparse
import csv
import fcntl
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import run_raw
sys.set_int_max_str_digits(0)
csv.field_size_limit(sys.maxsize)


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def atomic(path, content):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    os.replace(temporary, path)


def merge(folder, questions, workers):
    rows = read_csv(folder / 'seed.csv')
    for index in range(workers):
        rows.extend(read_csv(folder / f'worker_{index + 1:02}' / 'raw_pipeline.csv'))
    by_id = {}
    allowed = {str(q['Sample Row ID']) for q in questions}
    for row in rows:
        identity = str(row['Sample Row ID'])
        if identity not in allowed or identity in by_id:
            raise ValueError(f'Unknown or duplicate output ID: {identity}')
        by_id[identity] = row
    ordered = [by_id[str(q['Sample Row ID'])] for q in questions if str(q['Sample Row ID']) in by_id]
    if ordered:
        fields = list(dict.fromkeys(k for row in ordered for k in row))
        out = io.StringIO(newline='')
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ordered)
        atomic(folder / 'raw_pipeline.csv', out.getvalue())
    return len(ordered)


def active_original_runs():
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = (proc / 'cmdline').read_bytes().decode().split('\0')
        except (OSError, UnicodeError):
            continue
        if str(run_raw.PIPELINE / 'run.py') in args or any(
                arg.endswith('improvement10_models/run_raw.py') or arg.endswith('improvement10_models/run_parallel.py')
                for arg in args):
            found.append(proc.name)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--check', action='store_true', help='Verify source, existing caches and inputs; no API calls')
    parser.add_argument('--models', nargs='+', choices=run_raw.MODELS, default=list(run_raw.DEFAULT_MODELS))
    args = parser.parse_args()
    if len(set(args.models)) != len(args.models):
        parser.error('Duplicate models')
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('Invalid run tag')
    run_raw.verify_source()
    run_raw.load_local_env_file()
    plans = []
    for model in args.models:
        parent = run_raw.BASE / 'runs' / model / args.run_tag
        settings = json.loads((parent / 'launcher_manifest.json').read_text())
        questions = [json.loads(line) for line in (parent / 'input_questions.jsonl').read_text().splitlines() if line.strip()]
        ids = [str(q['Sample Row ID']) for q in questions]
        if len(set(ids)) != len(ids) or len(ids) != 1000:
            raise ValueError(f'{model}: expected 1000 unique questions')
        # Only compiler pack files; coverage and explicit-cache input bindings are sidecars.
        caches = [p for p in (parent / 'knowledge_cache').glob('*.json')
                  if re.fullmatch(r'[0-9a-f]{64}\.json', p.name)]
        if len(caches) != 1:
            raise ValueError(f'{model}: expected one completed context cache')
        cache = caches[0]
        payload = json.loads(cache.read_text())
        if payload.get('pack', {}).get('review_status') != 'completed':
            raise ValueError(f'{model}: context review is incomplete')
        connection_args = argparse.Namespace(model_id=settings['model_id'], base_url=settings['endpoint'],
                                             api_key_env=None, check=args.check, dry_run=False)
        model_id, endpoint, key = run_raw.connection(model, connection_args, os.environ)
        folder = parent / f'parallel_workers{args.workers}'
        print(f'{model}: {len(read_csv(parent / "raw_pipeline.csv"))} original rows; '
              f'{len(payload["pack"]["rules"])} cached rules; output {folder / "raw_pipeline.csv"}', flush=True)
        plans.append((model, parent, folder, questions, cache, model_id, endpoint, key))
    if args.check:
        print('Checks passed. No model calls or live-run changes.')
        return 0
    active = active_original_runs()
    if active:
        raise RuntimeError('Stop existing Improvement 10 pipeline processes before switching. Active PIDs: ' + ', '.join(active))
    lock_path = run_raw.BASE / f'.sharded_{args.run_tag}.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        children = []
        handles = []
        try:
            for model, parent, folder, questions, cache, model_id, endpoint, key in plans:
                folder.mkdir(parents=True, exist_ok=True)
                identity = {'workers': args.workers, 'source_commit': run_raw.verify_source()['commit'],
                            'input_sha256': run_raw.digest(parent / 'input_questions.jsonl'),
                            'cache_sha256': run_raw.digest(cache), 'model_id': model_id, 'endpoint': endpoint}
                if model == 'llama_3_1_405b':
                    identity.update(api='bedrock-converse', adapter_sha256=run_raw.digest(run_raw.BASE / 'bedrock_converse.py'),
                                    adapter_entry_sha256=run_raw.digest(run_raw.BASE / 'run_converse.py'), domain_max_output_tokens=4096)
                if model == 'qwen3_coder_480b':
                    identity['domain_max_output_tokens'] = 16384
                manifest = folder / 'sharding_manifest.json'
                if manifest.exists():
                    if json.loads(manifest.read_text()) != identity:
                        raise ValueError('Sharding configuration changed: ' + str(folder))
                else:
                    # Freeze existing rows; worker inputs remain identical on every resume.
                    seed = parent / 'raw_pipeline.csv'
                    atomic(folder / 'seed.csv', seed.read_text() if seed.exists() else '')
                    completed = {str(r['Sample Row ID']) for r in read_csv(folder / 'seed.csv')}
                    if len(completed) != len(read_csv(folder / 'seed.csv')):
                        raise ValueError('Duplicate original rows')
                    if not completed.issubset({str(q['Sample Row ID']) for q in questions}):
                        raise ValueError('Unknown original rows')
                    pending = [q for q in questions if str(q['Sample Row ID']) not in completed]
                    for index in range(args.workers):
                        worker = folder / f'worker_{index + 1:02}'
                        worker.mkdir(exist_ok=True)
                        atomic(worker / 'questions.jsonl', ''.join(json.dumps(q, ensure_ascii=False) + '\n' for q in pending[index::args.workers]))
                    atomic(manifest, json.dumps(identity, indent=2) + '\n')
                for index in range(args.workers):
                    worker = folder / f'worker_{index + 1:02}'
                    if not (worker / 'questions.jsonl').read_text().strip():
                        continue
                    env = dict(os.environ)
                    env.update(PIPELINE_ENV_FILE='', PIPELINE_ENV_OVERRIDE='0',
                               KNOWLEDGE_CACHE_DIR=str(parent / 'knowledge_cache'), KNOWLEDGE_CACHE_FILE=str(cache),
                               TEST_QUERY_OFFSET='0', TEST_MAX_WORKERS='1', QUERY_SHUFFLE_SEED='',
                               RETRY_QUERY_SPEC_ERRORS_ONLY='0', DOMAIN_COMPILATION_MODE='simple',
                               BEDROCK_GPT_OSS_MODEL=model_id, BEDROCK_BASE_URL=endpoint, AWS_BEDROCK_API_KEY=key,
                               PYTHONDONTWRITEBYTECODE='1', RESULT_JSONL_FILE=str(worker / 'raw_pipeline.jsonl'),
                               DEBUG_JSONL_FILE=str(worker / 'raw_pipeline_debug.jsonl'))
                    command = [sys.executable, '-u', '-B', str(run_raw.PIPELINE / 'run.py'),
                               '--db', str(run_raw.SOURCE / 'wealth_management_diverse.db'),
                               '--yaml-dir', str(run_raw.SOURCE / 'table_medatada'),
                               '--domain-intro', str(run_raw.SOURCE / 'domain_intro_latest.prompt'),
                               '--business-rules', str(run_raw.SOURCE / 'business_rules_addendum.md'),
                               '--questions', str(worker / 'questions.jsonl'), '--output', str(worker / 'raw_pipeline.csv'),
                               '--knowledge-cache', str(cache), '--knowledge-mode', 'simple', '--agent-consultation', 'on']
                    if model == 'llama_3_1_405b':
                        env['DOMAIN_MAX_OUTPUT_TOKENS'] = '4096'
                        command[3] = str(run_raw.BASE / 'run_converse.py')
                    if model == 'qwen3_coder_480b':
                        env['DOMAIN_MAX_OUTPUT_TOKENS'] = '16384'
                    handle = (worker / 'launcher.log').open('a')
                    handles.append(handle)
                    child = subprocess.Popen(command, cwd=run_raw.SOURCE, env=env, stdout=handle,
                                             stderr=subprocess.STDOUT, start_new_session=True)
                    children.append(child)
                    print(f'Started {model} worker {index + 1}: PID {child.pid}', flush=True)
            while any(c.poll() is None for c in children):
                for model, parent, folder, questions, *_ in plans:
                    print(f'{model}: {merge(folder, questions, args.workers)}/1000 saved', flush=True)
                time.sleep(10)
        except (KeyboardInterrupt, Exception):
            for child in children:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)
            for child in children:
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait()
            raise
        finally:
            for handle in handles:
                handle.close()
            for model, parent, folder, questions, *_ in plans:
                if (folder / 'seed.csv').exists():
                    print(f'{model}: {merge(folder, questions, args.workers)}/1000 saved', flush=True)
            run_raw.verify_source()
        return 1 if any(c.returncode for c in children) else 0


if __name__ == '__main__':
    raise SystemExit(main())
