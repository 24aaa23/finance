#!/usr/bin/env python3
"""Continue unchanged Improvement 11 on Azure with successful Bedrock rows retained."""
import argparse
import csv
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import run_parallel as parallel

BASE, SOURCE, PACKAGE = parallel.BASE, parallel.SOURCE, parallel.PACKAGE
ROOT = parallel.run_raw.ROOT
spec = importlib.util.spec_from_file_location('azure_settings', ROOT / 'ablations/azure_gpt_oss_120b/run_raw.py')
azure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(azure)


def write_rows(path, rows):
    import io
    out = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)
    parallel.atomic(path, out.getvalue())


def pending_rows(worker):
    records = [json.loads(line) for line in (worker / 'questions.jsonl').read_text().splitlines() if line.strip()]
    successes = {row['Sample Row ID'] for row in parallel.read_rows(worker / 'raw_pipeline.csv')
                 if row.get('New Status') == 'PIPELINE_SUCCESS'}
    return len(records) - len(successes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run-tag', default='run_01', help='Previous Bedrock report to continue')
    parser.add_argument('--source-report', action='append', default=[],
                        help='Explicit stopped-run CSV to continue; repeat to retain successes from multiple reports')
    parser.add_argument('--run-tag', default='azure_run_01')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--max-active-workers', type=int, choices=range(1, 9), default=2)
    parser.add_argument('--check', action='store_true', help='Inspect sources and pending counts; no model calls or output changes')
    parser.add_argument('--prepare-only', action='store_true', help='Copy and validate existing cache/shards; no query inference')
    args = parser.parse_args()
    for tag in [args.source_run_tag, args.run_tag]:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', tag):
            parser.error('Invalid run tag')
    if args.max_active_workers > args.workers:
        parser.error('max-active-workers exceeds workers')
    original = parallel.run_raw.verify()
    if not args.check and parallel.active_runs():
        raise RuntimeError('Stop the existing Improvement 11 workers before switching to Azure')
    azure.load_azure_env()
    azure.launcher.load_local_env_file()
    key = os.getenv('AZURE_OPENAI_API_KEY')
    deployment = os.getenv('AZURE_GPT_OSS_DEPLOYMENT')
    endpoint = azure.inference_url(os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('AZURE_FOUNDRY_ENDPOINT') or '')
    if not key or not deployment:
        raise RuntimeError('Fill azure_gpt_oss_120b/azure.env first')
    previous = BASE / 'runs/gpt_oss_120b' / args.source_run_tag
    questions_file = previous / 'input_questions.jsonl'
    questions = [json.loads(line) for line in questions_file.read_text().splitlines() if line.strip()]
    ids = [q['global_question_id'] for q in questions]
    if len(ids) != 1000 or len(set(ids)) != 1000:
        raise ValueError('Expected 1000 unique source questions')
    old_report = previous / f'parallel_workers{args.workers}/raw_pipeline.csv'
    if not old_report.exists():
        old_report = previous / 'raw_pipeline.csv'
    reports = [Path(p).expanduser().resolve() for p in args.source_report] if args.source_report else [old_report]
    merged = {}
    question_text = {q['global_question_id']: q.get('question', q.get('Question')) for q in questions}
    for report in reports:
        if not report.is_file():
            raise FileNotFoundError(report)
        rows = parallel.read_rows(report)
        report_ids = [r['Sample Row ID'] for r in rows]
        if len(report_ids) != len(set(report_ids)):
            raise ValueError('Duplicate source IDs: ' + str(report))
        for row in rows:
            identifier = row['Sample Row ID']
            if identifier not in question_text or row.get('Question') != question_text[identifier]:
                raise ValueError('Invalid source question: ' + identifier)
            # Keep the first successful answer; later successes replace failures.
            if identifier not in merged or merged[identifier].get('New Status') != 'PIPELINE_SUCCESS':
                merged[identifier] = row
    old_rows = [merged[k] for k in ids if k in merged]
    by_id = {row['Sample Row ID']: row for row in old_rows}
    if len(by_id) != len(old_rows) or not set(by_id) <= set(ids):
        raise ValueError('Invalid IDs in source report')
    for question in questions:
        row = by_id.get(question['global_question_id'])
        if row and row.get('Question') != question.get('question', question.get('Question')):
            raise ValueError('Source question text differs: ' + question['global_question_id'])
    seed = [row for row in old_rows if row.get('New Status') == 'PIPELINE_SUCCESS']
    failed = {row['Sample Row ID'] for row in old_rows if row.get('New Status') != 'PIPELINE_SUCCESS'}
    completed = {row['Sample Row ID'] for row in seed}
    pending = [q for q in questions if q['global_question_id'] in failed]
    pending += [q for q in questions if q['global_question_id'] not in completed | failed]
    caches = [p for p in (SOURCE / '.runtime/knowledge_v3_kg').glob('*.json')
              if re.fullmatch(r'[0-9a-f]{64}\.json', p.name)]
    if len(caches) != 1:
        raise ValueError('Expected one existing Improvement 11 knowledge cache')
    source_cache = caches[0]
    folder = BASE / 'runs/azure_gpt_oss_120b' / args.run_tag / f'parallel_workers{args.workers}'
    identity = {'source_commit': original['commit'], 'workers': args.workers,
                'source_report': str(old_report), 'source_report_sha256': parallel.digest(old_report),
                'input_sha256': parallel.digest(questions_file), 'deployment': deployment,
                'endpoint': endpoint, 'provider': 'azure-openai-v1',
                'retained_provider': 'bedrock', 'retained_successes': len(seed),
                'knowledge_origin': 'copied unchanged from existing Bedrock-prepared Improvement 11 cache',
                'knowledge_sha256': parallel.digest(source_cache), 'launcher_sha256': parallel.digest(Path(__file__))}
    if args.source_report:
        identity['source_report'] = str(reports[0])
        identity['source_report_sha256'] = parallel.digest(reports[0])
        identity['source_reports'] = [{'path': str(p), 'sha256': parallel.digest(p)} for p in reports]
        identity['retained_provider'] = 'as recorded by source run manifests; may include Bedrock and Azure'
    manifest = folder / 'azure_manifest.json'
    if manifest.exists() and json.loads(manifest.read_text()) != identity:
        raise RuntimeError('Source/configuration changed; use a new Azure run tag')
    print(f'[AZURE KG] Retain {len(seed)} successful rows; retry {len(failed)} errors; '
          f'run {1000-len(old_rows)} previously unanswered queries.', flush=True)
    print(f'[WORKERS] {args.workers} fixed shards, {args.max_active_workers} active; one sequential query per worker.', flush=True)
    print('[OUTPUT]', folder / 'raw_pipeline.csv', flush=True)
    if args.check:
        print('[CHECK] Source hashes, question IDs, Azure settings and continuation plan verified; no inference.')
        return 0
    with (BASE / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        folder.mkdir(parents=True, exist_ok=True)
        cache = folder / 'runtime/knowledge' / source_cache.name
        if not manifest.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_cache, cache)
            write_rows(folder / 'seed.csv', seed)
            for i in range(args.workers):
                worker = folder / f'worker_{i+1:02}'
                worker.mkdir(exist_ok=True)
                parallel.atomic(worker / 'questions.jsonl', ''.join(json.dumps(q, ensure_ascii=False)+'\n' for q in pending[i::args.workers]))
            parallel.atomic(manifest, json.dumps(identity, indent=2)+'\n')
        if parallel.digest(cache) != identity['knowledge_sha256']:
            raise RuntimeError('Copied context cache changed')
        allowed = {'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'JAVA_HOME', 'LD_LIBRARY_PATH',
                   'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}
        env = {k: v for k, v in os.environ.items() if k in allowed}
        # Native client uses these variable names; their values here are exclusively Azure.
        env.update(AWS_BEDROCK_API_KEY=key, BEDROCK_BASE_URL=endpoint,
                   BEDROCK_GPT_OSS_MODEL=deployment, TEST_MAX_WORKERS='1', TEST_QUERY_OFFSET='0',
                   RETRY_QUERY_SPEC_ERRORS_ONLY='0', PYTHONDONTWRITEBYTECODE='1',
                   KNOWLEDGE_CACHE_DIR=str(cache.parent))
        questions_copy = folder / 'input_questions.jsonl'
        if not questions_copy.exists():
            shutil.copy2(questions_file, questions_copy)
        subprocess.run(parallel.command(questions_copy, folder/'preparation.csv', cache)+['--prepare-knowledge'],
                       env=env, cwd=SOURCE, check=True)
        if args.prepare_only:
            parallel.merge(folder, questions, args.workers)
            parallel.run_raw.verify()
            print('[PREPARED] Context cache validated and shards ready. No benchmark queries started.', flush=True)
            return 0
        queue = []
        for i in range(args.workers):
            worker = folder / f'worker_{i+1:02}'
            expected = ''.join(json.dumps(q, ensure_ascii=False)+'\n' for q in pending[i::args.workers])
            if (worker/'questions.jsonl').read_text() != expected:
                raise RuntimeError('Immutable question shard changed')
            report = worker/'raw_pipeline.csv'
            rows = parallel.read_rows(report)
            failures = [r for r in rows if r.get('New Status') != 'PIPELINE_SUCCESS']
            if failures:
                backup = worker/'backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                backup.mkdir(parents=True)
                for artifact in worker.glob('raw_pipeline*'):
                    if artifact.is_file():
                        shutil.copy2(artifact, backup/artifact.name)
                write_rows(report, [r for r in rows if r.get('New Status') == 'PIPELINE_SUCCESS'])
                print(f'[RETRY worker {i+1}] {len(failures)} saved errors queued; backup: {backup}', flush=True)
            if pending_rows(worker):
                queue.append((i, worker))
        children, handles = [], []
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGHUP, stop)
        try:
            while queue or any(c.poll() is None for c in children):
                while queue and sum(c.poll() is None for c in children) < args.max_active_workers:
                    i, worker = queue.pop(0)
                    handle = (worker/'launcher.log').open('a'); handles.append(handle)
                    child = subprocess.Popen(parallel.command(worker/'questions.jsonl', worker/'raw_pipeline.csv', cache),
                        env=env, cwd=SOURCE, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                    children.append(child)
                    print(f'[WORKER {i+1}] PID {child.pid}', flush=True)
                print(f'[PROGRESS] {parallel.merge(folder, questions, args.workers)}/1000 saved', flush=True)
                time.sleep(10)
        finally:
            for child in children:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)
            for child in children:
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM);child.wait()
            for handle in handles:handle.close()
            parallel.merge(folder, questions, args.workers)
            parallel.run_raw.verify()
        return int(any(c.returncode for c in children))


if __name__ == '__main__':
    raise SystemExit(main())
