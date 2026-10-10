#!/usr/bin/env python3
"""Raw-only v5 model/context ablations on the fixed 1,000-question benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from script_diff_llm.config.runtime import load_local_env_file

MODELS = {
    'qwen3_coder_480b': ('qwen.qwen3-coder-480b-a35b-instruct', 'BEDROCK_MANTLE_BASE_URL', 'mantle'),
    'deepseek_v3_2': ('deepseek.v3.2', 'BEDROCK_MANTLE_BASE_URL', 'mantle'),
    'gemma_3_27b_it': ('google.gemma-3-27b-it', 'BEDROCK_MANTLE_BASE_URL', 'mantle'),
    'kimi_k2_thinking': ('moonshotai.kimi-k2-thinking', 'BEDROCK_MANTLE_BASE_URL', 'mantle'),
    'gpt_oss_120b': ('openai.gpt-oss-120b-1:0', 'BEDROCK_BASE_URL', 'runtime'),
}
CONDITIONS = ('without_context', 'with_context')
SOURCES = {
    'SQLITE_DB_PATH': ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db',
    'INPUT_SAMPLE_FILE': ROOT / 'wealth_management_1000_test_set_questions.xlsx',
    'GROUND_TRUTH_OVERRIDE_FILE': ROOT / '216_questions_full_results.json',
    'SCHEMA_FILE': ROOT / 'data/kg/wealth_management_diverse_schema.ttl',
    'INSTANCE_FILE': ROOT / 'data/kg/wealth_management_diverse_kg.ttl',
    'RDF_ALIAS_MAP_FILE': ROOT / 'data/kg/rdf_id_alias_map.json',
}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def build_environment(args, parent):
    env = dict(parent)
    identifier, endpoint_var, family = MODELS[args.model]
    identifier = args.model_id or identifier
    region = env.get('BEDROCK_REGION') or env.get('AWS_REGION') or env.get('AWS_DEFAULT_REGION') or 'us-east-1'
    fallback = (f'https://bedrock-mantle.{region}.api.aws/v1' if family == 'mantle'
                else f'https://bedrock-runtime.{region}.amazonaws.com/openai/v1')
    endpoint = args.base_url or env.get('ABLATION_BASE_URL') or env.get(endpoint_var) or fallback
    output = BASE / 'runs' / args.model / args.condition / args.run_tag
    experiment = BASE / 'configs/experiments' / f'{args.model}_{args.condition}.yaml'
    env.update({key: str(value) for key, value in SOURCES.items()})
    env.update({
        'ABLATION_RAW_MODEL': identifier, 'ABLATION_BASE_URL': endpoint,
        'EXPERIMENT_CONFIG': str(experiment),
        'INPUT_SAMPLE_SHEET': 'ALL_BENCHMARK_SHEETS',
        'FUSEKI_ENDPOINT': args.fuseki_endpoint,
        'PIPELINE_OUTPUT_DIR': str(output), 'REPORT_FILE': str(output / 'raw_pipeline.csv'),
        'RAW_REPORT_FILE': str(output / 'raw_pipeline.csv'),
        'GRADED_REPORT_FILE': str(output / 'graded_pipeline_gpt_5_mini.csv'),
        'TEST_QUERY_LIMIT': str(args.limit), 'TEST_QUERY_OFFSET': str(args.offset),
        'TEST_MAX_WORKERS': str(args.workers), 'DAG_LEVEL_MAX_WORKERS': str(args.dag_workers),
        'QUERY_SHUFFLE_SEED': '4043113952',
        'REPORT_SAVE_EVERY': str(args.save_every), 'BENCHMARK_START_DELAY_SECONDS': '0',
        'DETERMINISTIC_EXPLAIN': '1', 'SEMANTIC_CATALOG_FILE': '',
        'DOMAIN_CONTEXT_PREPARE_ONLY': '1' if args.prepare_context_only else '',
        'DOMAIN_CONTEXT_CACHE_DIR': str(BASE / 'context_cache' / args.model),
        'GPT_OSS_LLM_GRADER_PIPELINE_VERSION': 'ablation-generic-reliability-v6',
    })
    if args.model == 'qwen3_coder_480b':
        env.update(DOMAIN_CONTEXT_MAX_TOKENS='16384', DOMAIN_CONTEXT_RETRY_MAX_TOKENS='16384')
    if args.condition == 'without_context':
        env.update(DOMAIN_INTRO_FILE='', BUSINESS_RULES_FILE='', DOMAIN_CONTEXT_APPROVAL_FILE='', DOMAIN_CONTEXT_REQUIRED='')
    else:
        env.update(DOMAIN_INTRO_FILE=str(resolve_path(args.domain_intro)) if args.domain_intro else '',
                   BUSINESS_RULES_FILE=str(resolve_path(args.business_rules)) if args.business_rules else '',
                   DOMAIN_CONTEXT_APPROVAL_FILE=str(resolve_path(args.approval_file)) if args.approval_file else '',
                   DOMAIN_CONTEXT_REQUIRED='1')
    return env, output, experiment


def manifest_for(args, env, experiment):
    sources = {}
    for key in (*SOURCES, 'DOMAIN_INTRO_FILE', 'BUSINESS_RULES_FILE', 'DOMAIN_CONTEXT_APPROVAL_FILE'):
        value = env.get(key, '')
        if value:
            path = Path(value)
            sources[key] = {'path': value, 'sha256': file_hash(path) if path.is_file() else None}
        else:
            sources[key] = None
    implementation = {str(path.relative_to(ROOT)): file_hash(path)
                      for path in sorted((ROOT / 'src/script_diff_llm').rglob('*.py'))}
    payload = {
        'model': args.model, 'condition': args.condition, 'model_id': env['ABLATION_RAW_MODEL'],
        'endpoint': env['ABLATION_BASE_URL'], 'fuseki_endpoint': env['FUSEKI_ENDPOINT'],
        'sources': sources, 'experiment_sha256': file_hash(experiment),
        'model_config_sha256': file_hash(BASE / 'configs/models' / f'{args.model}.yaml'),
        'implementation': implementation,
        'settings': {key: env[key] for key in ('TEST_QUERY_LIMIT', 'TEST_QUERY_OFFSET', 'TEST_MAX_WORKERS',
                    'DAG_LEVEL_MAX_WORKERS', 'QUERY_SHUFFLE_SEED', 'DETERMINISTIC_EXPLAIN',
                    'GPT_OSS_LLM_GRADER_PIPELINE_VERSION', 'REPORT_SAVE_EVERY')},
        'context_preparation': 'per-model; independently reviewed policies only',
        'context_token_budgets': {
            'initial': int(env.get('DOMAIN_CONTEXT_MAX_TOKENS', '16384')),
            'retry': int(env.get('DOMAIN_CONTEXT_RETRY_MAX_TOKENS', '32768')),
        } if args.condition == 'with_context' else None,
        'grader': 'manual only; gpt-5-mini',
    }
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {'signature': signature, 'configuration': payload}


def check_resume(output, manifest):
    previous = output / 'run_manifest.json'
    raw = output / 'raw_pipeline.csv'
    if raw.exists() and raw.stat().st_size:
        if not previous.exists() or json.loads(previous.read_text())['signature'] != manifest['signature']:
            raise ValueError('Run configuration changed or is untracked. Use a fresh --run-tag instead of mixing results.')


def execute_raw(command, env, output):
    with (output / 'pipeline.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            return process.wait()
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
            print('\nStopped raw run; rerun the same command to resume saved rows.')
            return 130


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', choices=MODELS)
    parser.add_argument('condition', choices=CONDITIONS)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--dag-workers', type=int, default=2)
    parser.add_argument('--limit', type=int, default=1000, help='Question window within the fixed 1000-query dataset')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--save-every', type=int, default=1, help='Raw CSV checkpoint interval; 1 preserves every completed row')
    parser.add_argument('--base-url', help='Optional OpenAI-compatible endpoint override')
    parser.add_argument('--model-id', help='Exact model ID on an alternate endpoint')
    parser.add_argument('--fuseki-endpoint', default='http://127.0.0.1:3030/wealth/query')
    parser.add_argument('--domain-intro', default=str(ROOT / 'domain_intro.prompt'))
    parser.add_argument('--business-rules', default=str(ROOT / 'phase0_business_rules.md'))
    parser.add_argument('--approval-file', default='')
    parser.add_argument('--prepare-context-only', action='store_true', help='Prepare/review context without starting benchmark questions')
    parser.add_argument('--dry-run', action='store_true', help='Inspect settings without API calls or starting a pipeline')
    args = parser.parse_args(argv)
    if args.limit < 1 or args.offset < 0 or args.limit + args.offset > 1000:
        parser.error('limit/offset must select a nonempty window within the 1000-query dataset')
    if args.prepare_context_only and args.condition != 'with_context':
        parser.error('--prepare-context-only requires with_context')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('--run-tag must be a simple directory name')
    if args.workers < 1 or args.dag_workers < 1 or args.save_every < 1:
        parser.error('Worker counts must be positive')
    return args


def main(argv=None):
    args = parse_args(argv)
    load_local_env_file()
    env, output, experiment = build_environment(args, os.environ)
    for path in SOURCES.values():
        if not path.is_file():
            raise FileNotFoundError(f'Missing fixed benchmark source: {path}')
    manifest = manifest_for(args, env, experiment)
    check_resume(output, manifest)
    summary = {key: value for key, value in env.items() if key in {
        *SOURCES, 'INPUT_SAMPLE_SHEET', 'FUSEKI_ENDPOINT', 'ABLATION_RAW_MODEL', 'ABLATION_BASE_URL',
        'DOMAIN_INTRO_FILE', 'BUSINESS_RULES_FILE', 'DOMAIN_CONTEXT_APPROVAL_FILE',
        'DOMAIN_CONTEXT_REQUIRED', 'PIPELINE_OUTPUT_DIR', 'REPORT_FILE', 'EXPERIMENT_CONFIG',
        'TEST_QUERY_LIMIT', 'TEST_QUERY_OFFSET', 'TEST_MAX_WORKERS', 'REPORT_SAVE_EVERY'}}
    print(json.dumps(summary, indent=2), flush=True)
    print('[ABLATION] Raw only. The grader will not start.', flush=True)
    if args.dry_run:
        return 0
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'run_manifest.json.tmp'
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    temporary.replace(output / 'run_manifest.json')
    # The normal entry point consumes these model settings before importing core.
    return execute_raw([sys.executable, '-u', str(ROOT / 'runners/train/run_pipeline.py'), str(experiment)], env, output)


if __name__ == '__main__':
    raise SystemExit(main())
