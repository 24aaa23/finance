#!/usr/bin/env python3
"""Read-only run watcher: 30-second checks, desktop alerts and 30-minute reports."""
import argparse
import collections
import csv
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

csv.field_size_limit(sys.maxsize)
BASE = Path(__file__).resolve().parent
MODELS = ('gpt_oss_120b', 'deepseek_v3_2', 'gemma_3_27b_it', 'kimi_k2_thinking')


def rows(path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def live_outputs():
    found = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = (proc / 'cmdline').read_bytes().decode().split('\0')
            if '--output' in args and any(arg.endswith('/run_pipeline_v3_sql _/run.py') for arg in args):
                found.add(args[args.index('--output') + 1])
        except (OSError, UnicodeError, IndexError):
            pass
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--interval', type=int, default=30)
    parser.add_argument('--report-minutes', type=int, default=30)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag) or args.workers < 1 or args.interval < 1 or args.report_minutes < 1:
        parser.error('Invalid monitor configuration')
    folder = BASE / 'monitoring' / args.run_tag
    folder.mkdir(parents=True, exist_ok=True)
    lock = (folder / 'monitor.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (folder / 'monitor.pid').write_text(str(os.getpid()) + '\n')
    next_report = 0
    alerts = {}
    progress = {}
    began = time.monotonic()

    def emit(kind, message):
        stamp = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
        print(f'{stamp} [{kind}] {message}', flush=True)
        with (folder / 'events.jsonl').open('a') as handle:
            handle.write(json.dumps({'time': stamp, 'kind': kind, 'message': message}) + '\n')
        try:
            result = subprocess.run(['notify-send', '--app-name=Pipeline monitor',
                                     '--urgency=' + ('critical' if kind == 'ANOMALY' else 'normal'),
                                     'Improvement 10: ' + kind, message], capture_output=True, text=True, timeout=5)
            if result.returncode:
                print('Desktop notification failed: ' + result.stderr.strip(), flush=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            print('Desktop notification unavailable: ' + str(error), flush=True)

    def alert(key, message, now):
        if now - alerts.get(key, -100000) >= args.report_minutes * 60:
            emit('ANOMALY', message)
            alerts[key] = now

    while True:
        now = time.monotonic()
        active = live_outputs()
        snapshot = {}
        all_done = True
        for model in MODELS:
            d = BASE / 'runs' / model / args.run_tag / f'parallel_workers{args.workers}'
            seed = rows(d / 'seed.csv')
            combined = list(seed)
            model_active = 0
            for index in range(args.workers):
                w = d / f'worker_{index + 1:02}'
                p = w / 'raw_pipeline.csv'
                saved = rows(p)
                combined.extend(saved)
                q = w / 'questions.jsonl'
                expected = len(q.read_text().splitlines()) if q.exists() else 0
                running = str(p) in active
                model_active += int(running)
                key = f'{model}/{w.name}'
                previous, changed = progress.get(key, (len(saved), began))
                if len(saved) != previous:
                    changed = now
                progress[key] = (len(saved), changed)
                if len(saved) < expected:
                    if not running:
                        alert(key + '/stopped', f'{key} stopped before completion: {len(saved)}/{expected} saved.', now)
                    elif now - changed > 600:
                        alert(key + '/stalled', f'{key}: no newly saved row for over 10 minutes; request/retry may still be running.', now)
                if len(saved) >= 10:
                    recent = saved[-10:]
                    errors = sum('API' in r.get('New Status', '').upper() or 'QUOTA' in r.get('Validation Reason', '').upper() for r in recent)
                    if errors >= 2:
                        alert(key + '/api', f'{key}: {errors}/10 recent saved rows indicate API/quota failures.', now)
                log = w / 'launcher.log'
                if log.exists():
                    with log.open('rb') as handle:
                        handle.seek(max(0, log.stat().st_size - 16000))
                        tail = handle.read().decode(errors='replace')
                    if ('[FAILED]' in tail or 'Traceback (most recent call last)' in tail) and not running and len(saved) < expected:
                        alert(key + '/crash', f'{key}: failure/traceback in launcher log. Inspect {log}', now)
            counts = dict(collections.Counter(r.get('New Status', '') for r in combined))
            ids = [r.get('Sample Row ID') for r in combined]
            if len(ids) != len(set(ids)):
                alert(model + '/duplicates', f'{model}: duplicate saved question IDs detected.', now)
            if len(combined) >= 10:
                failures = sum(r.get('New Status') != 'PIPELINE_SUCCESS' for r in combined[-20:])
                window = min(20, len(combined))
                if failures / window >= .5:
                    alert(model + '/failures', f'{model}: {failures}/{window} recently collected rows failed. This includes existing preserved rows at startup.', now)
            snapshot[model] = {'saved': len(combined), 'statuses': counts, 'active_workers': model_active}
            all_done &= len(set(ids)) == 1000 and model_active == 0
        payload = {'time': datetime.datetime.now().astimezone().isoformat(timespec='seconds'), 'models': snapshot}
        temp = folder / 'status.tmp'
        temp.write_text(json.dumps(payload, indent=2) + '\n')
        os.replace(temp, folder / 'status.json')
        if now >= next_report:
            emit('STATUS', '\n'.join(f'{m}: {s["saved"]}/1000; success {s["statuses"].get("PIPELINE_SUCCESS", 0)}; active workers {s["active_workers"]}' for m, s in snapshot.items()))
            next_report = now + args.report_minutes * 60
        if all_done:
            emit('COMPLETED', 'All four experiments have 1000 unique saved rows and their workers have exited. Grading has not been started.')
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
