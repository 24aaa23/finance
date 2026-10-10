#!/usr/bin/env python3
"""Run the four isolated Improvement 10 model experiments concurrently."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import run_raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=run_raw.MODELS, default=list(run_raw.DEFAULT_MODELS))
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--check', action='store_true', help='Run original offline checks only; no model calls')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if len(set(args.models)) != len(args.models):
        parser.error('Do not list a model twice')
    if args.limit < 0:
        parser.error('limit must be nonnegative')
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('run-tag must be a simple folder name')
    run_raw.verify_source()
    run_raw.load_local_env_file()
    # Preflight all credentials and endpoints before any paid work starts.
    connection_args = argparse.Namespace(model_id=None, base_url=None, api_key_env=None,
                                         check=args.check, dry_run=args.dry_run)
    for model in args.models:
        run_raw.connection(model, connection_args, os.environ)
    logs = run_raw.BASE / 'launcher_logs' / args.run_tag
    logs.mkdir(parents=True, exist_ok=True)
    processes = {}
    handles = []
    failures = []
    try:
        for model in args.models:
            command = [sys.executable, '-u', '-B', str(run_raw.BASE / 'run_raw.py'), model,
                       '--run-tag', args.run_tag, '--limit', str(args.limit)]
            if args.check:
                command.append('--check')
            if args.dry_run:
                command.append('--dry-run')
            handle = (logs / f'{model}.log').open('a', encoding='utf-8')
            handles.append(handle)
            process = subprocess.Popen(command, cwd=run_raw.ROOT, stdout=handle,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            processes[model] = process
            print(f'[STARTED] {model}: PID {process.pid}; log {handle.name}', flush=True)
        while processes:
            for model, process in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                print(f'[FINISHED] {model}: exit code {code}', flush=True)
                if code:
                    failures.append(model)
                del processes[model]
            if processes:
                time.sleep(1)
    except KeyboardInterrupt:
        for process in processes.values():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
        for process in processes.values():
            process.wait()  # Wrappers forward interruption to their pipeline children.
        print('Stopped. Repeat the identical command to resume saved rows.', flush=True)
        return 130
    finally:
        for handle in handles:
            handle.close()
    print('No graders were started. Failed experiments: ' + (', '.join(failures) or 'none'), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
