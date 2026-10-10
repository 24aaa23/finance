#!/usr/bin/env python3
"""Parallel execution of grader 3's original row workflow, with safe resume."""
import argparse
import concurrent.futures
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

csv.field_size_limit(sys.maxsize)
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    os.replace(temp, path)


def input_key(row, answer_column):
    return hashlib.sha256(json.dumps([row.get(k, '') for k in
        ('Sample Row ID', 'Question', 'Ground Truth', answer_column)] + ['gpt-5-mini'], ensure_ascii=False).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--answer-column', default='New Pipeline Result')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    args.raw, args.output = args.raw.resolve(), args.output.resolve()
    if args.workers < 1 or args.raw == args.output:
        p.error('Positive workers and distinct input/output paths required')
    rows = read(args.raw)
    if not rows or not {'Question', 'Ground Truth', args.answer_column} <= rows[0].keys():
        p.error('Missing grading inputs')
    keys = [input_key(r, args.answer_column) for r in rows]
    if len(set(keys)) != len(keys):
        p.error('Duplicate grading inputs')
    print(f'Grader 3 / gpt-5-mini; {len(rows)} rows; {args.workers} workers; output {args.output}', flush=True)
    if args.dry_run:
        return
    spec = importlib.util.spec_from_file_location('grader3', ROOT / 'grader_3.py')
    grader = importlib.util.module_from_spec(spec); spec.loader.exec_module(grader)
    grader.LLM_GRADER_MODEL = 'gpt-5-mini'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    grader.api_logger = grader.APILogger(str(args.output.parent))
    # Keep request format/prompts unchanged; disable compressed transport and bound retries.
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY missing after environment loading')
    client = grader.LLMClient(api_key=key, base_url=os.getenv('OPENAI_BASE_URL') or None,
        default_headers={'Accept-Encoding': 'identity'},
        timeout=float(os.getenv('GRADER_API_TIMEOUT_SECONDS', '60')),
        max_retries=int(os.getenv('GRADER_OPENAI_MAX_RETRIES', '2')))
    with args.output.with_suffix(args.output.suffix + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = read(args.output) if args.output.exists() else []
        by_key = {}
        for row in prior:
            if row.get('Direct LLM Grader Model') == 'gpt-5-mini':
                by_key[row.get('Grader 3 Input Key') or input_key(row, args.answer_column)] = row
        results = {i: by_key[k] for i, k in enumerate(keys) if k in by_key}
        def save():
            write(args.output, [results[i] for i in sorted(results)])
        with tempfile.TemporaryDirectory(prefix='.grader3_', dir=args.output.parent) as directory:
            def one(index):
                folder = Path(directory) / str(index);folder.mkdir()
                raw, output = folder / 'raw.csv', folder / 'graded.csv'
                write(raw, [rows[index]])
                if keys[index] in by_key:
                    write(output, [by_key[keys[index]]])
                grader.regrade_existing_report(str(raw), str(output), client, 'gpt-5-mini', args.answer_column)
                result = read(output)[0]
                result.update({'Grader Label': 'grader_3', 'Grader 3 Input Key': keys[index]})
                return result
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
            pending = {};next_index = 0
            try:
                while next_index < len(rows) or pending:
                    while next_index < len(rows) and len(pending) < args.workers:
                        pending[pool.submit(one, next_index)] = next_index;next_index += 1
                    ready, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in ready:
                        index = pending.pop(future);results[index] = future.result();save()
                        print(f'[GRADER 3] row {index+1}/{len(rows)}: {results[index]["New Status"]}', flush=True)
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
                for future, index in pending.items():
                    if future.done() and not future.cancelled() and future.exception() is None:
                        results[index] = future.result()
                save();grader.api_logger.save();client.close()


if __name__ == '__main__':
    main()
