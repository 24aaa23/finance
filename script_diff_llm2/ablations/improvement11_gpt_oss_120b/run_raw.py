#!/usr/bin/env python3
"""Configure paths and credentials for the unchanged Improvement 11 pipeline."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import fcntl

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
SOURCE = BASE / 'source' / 'improvemnt11kgfixed'
PACKAGE = SOURCE / 'run_pipeline_v2_kg'
sys.dont_write_bytecode = True


def verify():
    manifest = json.loads((BASE / 'source_manifest.json').read_text())
    for name, expected in manifest['files'].items():
        actual = hashlib.sha256((BASE / 'source' / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Original source changed: {name}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--check-kg', action='store_true')
    parser.add_argument('--prepare-knowledge', action='store_true')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('Use a simple run-tag folder name')
    if sum([args.check, args.check_kg, args.prepare_knowledge, args.retry]) > 1:
        parser.error('Choose one mode')
    original = verify()
    # Read credentials only. No data or workflow settings are inherited from older runs.
    env = dict(os.environ)
    candidates = [ROOT / '.env', ROOT / 'env/.env',
                  ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/.env']
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if key not in {'AWS_BEDROCK_API_KEY', 'AWS_Bedrock_API_gpt_oss_120b',
                           'BEDROCK_API_KEY', 'BEDROCK_BASE_URL', 'BEDROCK_REGION',
                           'AWS_REGION', 'AWS_DEFAULT_REGION'}:
                continue
            value = value.strip()
            if value.startswith(('"', "'")):
                value = value[1:].split(value[0], 1)[0]
            else:
                value = value.split('#', 1)[0].strip()
            env.setdefault(key, value)
    key = next((env.get(k) for k in ['AWS_BEDROCK_API_KEY', 'AWS_Bedrock_API_gpt_oss_120b', 'BEDROCK_API_KEY'] if env.get(k)), '')
    if not args.check and not args.check_kg and not key:
        raise RuntimeError('Missing Bedrock credential in environment or local .env')
    folder = BASE / 'runs' / 'gpt_oss_120b' / args.run_tag
    folder.mkdir(parents=True, exist_ok=True)
    with (BASE / '.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('An Improvement 11 launcher is already running')
        # Use the original dataset preparation, including all reference overrides.
        sys.path.insert(0, str(SOURCE))
        spec = importlib.util.spec_from_file_location('original_prepare', PACKAGE / 'prepare_dataset.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        questions = folder / 'input_questions.jsonl'
        count = module.prepare_dataset(SOURCE / 'datatset/wealth_management_1000_test_set_questions.xlsx',
                                       SOURCE / 'datatset/216_questions_full_results.json',
                                       questions, folder / 'dataset_parts')
        if count != 1000:
            raise RuntimeError(f'Expected 1000 questions, got {count}')
        # Keep only credentials and system settings; discard stale pipeline configuration.
        allowed = {'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'JAVA_HOME', 'LD_LIBRARY_PATH',
                   'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'}
        clean = {k: v for k, v in os.environ.items() if k in allowed}
        endpoint = env.get('BEDROCK_BASE_URL') or 'https://bedrock-runtime.' + (env.get('BEDROCK_REGION') or env.get('AWS_REGION') or 'us-east-1') + '.amazonaws.com/openai/v1'
        clean.update(AWS_BEDROCK_API_KEY=key, BEDROCK_BASE_URL=endpoint,
                     BEDROCK_GPT_OSS_MODEL='openai.gpt-oss-120b-1:0',
                     TEST_MAX_WORKERS='1', TEST_QUERY_OFFSET='0', RETRY_QUERY_SPEC_ERRORS_ONLY='0',
                     PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-u', '-B', str(PACKAGE / 'run.py'),
                   '--ontology', str(SOURCE / 'kg_output_fixed/wealth_management_diverse_schema.ttl'),
                   '--kg-data', str(SOURCE / 'kg_output_fixed/wealth_management_diverse_kg.ttl'),
                   '--domain-intro', str(SOURCE / 'domain_intro_latest.prompt'),
                   '--business-rules', str(SOURCE / 'business_rules_addendum.md'),
                   '--sparql-endpoint', 'http://127.0.0.1:3041/improvemnt11kgfixed/query',
                   '--questions', str(questions), '--output', str(folder / 'raw_pipeline.csv'),
                   '--knowledge-mode', 'simple']
        mode = '--check-inputs' if args.check else '--check-kg' if args.check_kg else '--prepare-knowledge' if args.prepare_knowledge else '--retry-errors-in-place' if args.retry else None
        if mode:
            command.append(mode)
        manifest = {'snapshot_commit': original['commit'], 'model': clean['BEDROCK_GPT_OSS_MODEL'],
                    'endpoint': endpoint, 'workers': 1, 'questions': count, 'command': command[:],
                    'grader': 'not launched'}
        stable = dict(manifest, command=[s for s in command if s not in ['--check-inputs', '--check-kg', '--prepare-knowledge', '--retry-errors-in-place']])
        manifest_file = folder / 'launcher_manifest.json'
        if manifest_file.exists() and json.loads(manifest_file.read_text()) != stable:
            raise RuntimeError('Configuration changed; use a fresh run-tag')
        manifest_file.write_text(json.dumps(stable, indent=2) + '\n')
        print(json.dumps(manifest, indent=2), flush=True)
        try:
            result = subprocess.run(command, cwd=SOURCE, env=clean)
        finally:
            verify()
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
