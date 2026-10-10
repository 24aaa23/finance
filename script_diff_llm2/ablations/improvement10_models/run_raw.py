#!/usr/bin/env python3
"""Launch the unchanged Improvement 10 SQL pipeline on four models, raw only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
SOURCE = BASE / 'source' / 'improvement10'
PIPELINE = SOURCE / 'run_pipeline_v3_sql _'
DEFAULT_MODELS = ('gpt_oss_120b', 'deepseek_v3_2', 'gemma_3_27b_it', 'kimi_k2_thinking')
MODELS = DEFAULT_MODELS + ('llama_3_1_405b', 'qwen3_coder_480b')
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
from script_diff_llm.config.runtime import load_local_env_file


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_source():
    manifest = json.loads((BASE / 'source_manifest.json').read_text())
    for name, metadata in manifest['files'].items():
        path = BASE / 'source' / name
        if not path.is_file() or digest(path) != metadata['sha256']:
            raise ValueError(f'Original source or asset changed: {path}. Restore the snapshot before running.')
    return manifest


def connection(model, args, env):
    region = env.get('BEDROCK_REGION') or env.get('AWS_REGION') or env.get('AWS_DEFAULT_REGION') or 'us-east-1'
    if model == 'llama_3_1_405b':
        model_id = args.model_id or env.get('BEDROCK_LLAMA_405B_MODEL') or 'meta.llama3-1-405b-instruct-v1:0'
        endpoint = args.base_url or env.get('BEDROCK_LLAMA_405B_BASE_URL') or 'https://bedrock-runtime.us-west-2.amazonaws.com'
        key_names = [args.api_key_env] if args.api_key_env else ['AWS_BEARER_TOKEN_BEDROCK', 'AWS_BEDROCK_API_KEY', 'AWS_Bedrock_API_gpt_oss_120b', 'BEDROCK_API_KEY']
    elif model == 'gpt_oss_120b':
        model_id = args.model_id or 'openai.gpt-oss-120b-1:0'
        endpoint = args.base_url or env.get('BEDROCK_BASE_URL') or f'https://bedrock-runtime.{region}.amazonaws.com/openai/v1'
        key_names = [args.api_key_env] if args.api_key_env else ['AWS_BEDROCK_API_KEY', 'AWS_Bedrock_API_gpt_oss_120b', 'BEDROCK_API_KEY']
    else:
        model_id = args.model_id or {'deepseek_v3_2': 'deepseek.v3.2',
                                    'gemma_3_27b_it': 'google.gemma-3-27b-it',
                                    'kimi_k2_thinking': 'moonshotai.kimi-k2-thinking',
                                    'qwen3_coder_480b': 'qwen.qwen3-coder-480b-a35b-instruct'}[model]
        endpoint = args.base_url or env.get('BEDROCK_MANTLE_BASE_URL') or f'https://bedrock-mantle.{region}.api.aws/v1'
        key_names = [args.api_key_env] if args.api_key_env else ['BEDROCK_MANTLE_API_KEY', 'AWS_BEDROCK_API_KEY', 'BEDROCK_API_KEY']
    key = next((env.get(k) for k in key_names if env.get(k)), '')
    if not args.check and not args.dry_run:
        if not model_id or not endpoint:
            raise ValueError('Missing model ID or endpoint')
        if not key:
            raise ValueError('Missing API key. Set one of: ' + ', '.join(key_names))
    return model_id, endpoint, key


def execute(command, env, folder):
    with (folder / 'launcher.log').open('a', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=SOURCE, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        try:
            for line in child.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            return child.wait()
        except KeyboardInterrupt:
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait()
            print('Stopped. Repeat the same command to use the original pipeline resume logic.')
            return 130


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', choices=MODELS)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--limit', type=int, default=0, help='0 means the complete dataset; use a fresh tag for a pilot')
    parser.add_argument('--base-url', help='OpenAI-compatible endpoint override')
    parser.add_argument('--model-id', help='Exact model ID on the selected provider')
    parser.add_argument('--api-key-env', help='Name of credential environment variable; never pass a key value')
    parser.add_argument('--check', action='store_true', help='Original offline input validation; no model calls')
    parser.add_argument('--dry-run', action='store_true', help='Print resolved configuration without launching')
    parser.add_argument('--prepare-knowledge', action='store_true', help='Prepare the original model-specific context and exit')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('run-tag must be a simple folder name')
    if args.limit < 0:
        parser.error('limit must be nonnegative')
    source = verify_source()
    load_local_env_file()
    env = dict(os.environ)
    model_id, endpoint, key = connection(args.model, args, env)
    folder = BASE / 'runs' / args.model / args.run_tag
    paths = {'db': SOURCE / 'wealth_management_diverse.db', 'yaml-dir': SOURCE / 'table_medatada',
             'domain-intro': SOURCE / 'domain_intro_latest.prompt',
             'business-rules': SOURCE / 'business_rules_addendum.md'}
    workbook = SOURCE / 'datatset' / 'wealth_management_1000_test_set_questions.xlsx'
    answers = SOURCE / 'datatset' / '216_questions_full_results.json'
    settings = {'snapshot_commit': source['commit'], 'model_alias': args.model,
                'model_id': model_id, 'endpoint': endpoint, 'limit': args.limit,
                'sources': {k: str(v) for k, v in paths.items()},
                'workbook': str(workbook), 'full_answers': str(answers),
                'output': str(folder), 'workers': 1, 'knowledge_mode': 'simple',
                'agent_consultation': 'on', 'grader': 'not launched'}
    if args.model == 'llama_3_1_405b':
        settings.update(api='bedrock-converse', adapter_sha256=digest(BASE / 'bedrock_converse.py'),
                        adapter_entry_sha256=digest(BASE / 'run_converse.py'), domain_max_output_tokens=4096)
    if args.model == 'qwen3_coder_480b':
        settings['domain_max_output_tokens'] = 16384
    print(json.dumps(settings, indent=2), flush=True)
    if args.dry_run:
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'launcher_manifest.json'
    if (folder / 'raw_pipeline.csv').exists():
        if not manifest.exists() or json.loads(manifest.read_text()) != settings:
            raise ValueError('Launch configuration changed. Use a fresh --run-tag.')
    manifest.write_text(json.dumps(settings, indent=2) + '\n')
    # Use the original dataset preparer, preserving IDs and reference overrides.
    spec = importlib.util.spec_from_file_location('improvement10_dataset_launcher', SOURCE / 'run_all.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    questions, summary = original.prepare_dataset(workbook, answers, folder)
    print(f"[DATASET] {summary['questions']} questions; {summary['full_answer_overrides']} reference overrides.", flush=True)
    # Match run_all.py settings, except the explicitly selected model/endpoint and
    # isolated output paths. All prompts and pipeline operators remain original.
    env.update(PIPELINE_ENV_FILE='', PIPELINE_ENV_OVERRIDE='0',
               KNOWLEDGE_CACHE_DIR=str(folder / 'knowledge_cache'), KNOWLEDGE_CACHE_FILE='',
               PIPELINE_RUNTIME_DIR=str(folder / 'runtime'), TEST_QUERY_OFFSET='0', TEST_MAX_WORKERS='1',
               QUERY_SHUFFLE_SEED='', RETRY_QUERY_SPEC_ERRORS_ONLY='0',
               RESULT_JSONL_FILE=str(folder / 'raw_pipeline.jsonl'),
               DEBUG_JSONL_FILE=str(folder / 'raw_pipeline_debug.jsonl'), PYTHONDONTWRITEBYTECODE='1',
               DOMAIN_COMPILATION_MODE='simple', BEDROCK_GPT_OSS_MODEL=model_id,
               BEDROCK_BASE_URL=endpoint, AWS_BEDROCK_API_KEY=key)
    command = [sys.executable, '-u', '-B', str(PIPELINE / 'run.py')]
    if args.model == 'llama_3_1_405b':
        env['DOMAIN_MAX_OUTPUT_TOKENS'] = '4096'
        command = [sys.executable, '-u', '-B', str(BASE / 'run_converse.py')]
    if args.model == 'qwen3_coder_480b':
        env['DOMAIN_MAX_OUTPUT_TOKENS'] = '16384'
    for flag, path in paths.items():
        command.extend(['--' + flag, str(path)])
    command.extend(['--questions', str(questions), '--output', str(folder / 'raw_pipeline.csv'),
                    '--limit', str(args.limit), '--knowledge-mode', 'simple', '--agent-consultation', 'on'])
    if args.check:
        command.append('--check-inputs')
    elif args.prepare_knowledge:
        command.append('--prepare-knowledge')
    code = execute(command, env, folder)
    verify_source()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
