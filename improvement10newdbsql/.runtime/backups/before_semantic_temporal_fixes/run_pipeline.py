"""Run this folder's NeoWealth DuckDB question bank with four question workers."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'run_pipeline_v3_sql _'
MODEL_PRESETS = {
    'gpt-oss': {'id': 'openai.gpt-oss-120b-1:0', 'output': 'full_run',
                'cache': 'knowledge_neowealth'},
    'deepseek-v3.1': {'id': 'deepseek.v3-v1:0', 'output': 'deepseek_v3_1',
                     'cache': 'knowledge_neowealth_deepseek_v3_1'},
    'deepseek-v3.2': {'id': 'deepseek.v3.2', 'output': 'deepseek_v3_2',
                     'cache': 'knowledge_neowealth_deepseek_v3_2'},
}


def prepare_questions(destination):
    import pandas as pd
    workbook = ROOT / 'datatset/neowealth-master-question-bank_FINAL_DELIVERABLE.xlsx'
    frame = pd.read_excel(workbook, sheet_name='questions', keep_default_na=False)
    full_answers = None
    records, seen = [], set()
    for row in frame.to_dict('records'):
        identity = str(row['task_id'])
        if not identity or identity in seen or not str(row['question']).strip():
            raise ValueError('Question IDs must be unique and questions nonempty.')
        seen.add(identity)
        truth = row['ground_truth_answer']
        try:
            decoded = json.loads(truth) if isinstance(truth, str) else truth
        except json.JSONDecodeError:
            # Six large answer cells exceed Excel's cell-text limit. The normalized
            # gold_answers sheet contains their complete row/column values.
            if full_answers is None:
                full_answers = {}
                gold = pd.read_excel(workbook, sheet_name='gold_answers', keep_default_na=False)
                for cell in gold.itertuples():
                    task = full_answers.setdefault(str(cell.task_id), {})
                    answer_row = task.setdefault(int(cell.row_no), {})
                    if cell.column_name in answer_row:
                        raise ValueError('Duplicate gold-answer cell.')
                    answer_row[cell.column_name] = None if cell.value_text == 'null' else cell.value
            rows = full_answers.get(identity, {})
            if sorted(rows) != list(range(1, int(row['gold_row_count']) + 1)):
                raise ValueError(f'Question {identity} has incomplete full gold rows.')
            decoded = [rows[index] for index in sorted(rows)]
        if not isinstance(decoded, (list, dict)):
            raise ValueError(f'Question {identity} has no structured ground truth.')
        if isinstance(decoded, list) and len(decoded) != int(row['gold_row_count']):
            raise ValueError(f'Question {identity} answer row count differs from gold_row_count.')
        records.append({'Sample Row ID': identity, 'Question': str(row['question']),
                        'Ground Truth': json.dumps(decoded, ensure_ascii=False),
                        'Difficulty': str(row['difficulty']), 'Category': str(row['tier_name']),
                        'Query Type': str(row['tier']), 'Dataset Type': 'NeoWealth'})
    content = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_text(encoding='utf-8') != content:
        raise ValueError('Question data changed. Choose a fresh output folder.')
    if not destination.exists():
        destination.write_text(content, encoding='utf-8')
    return len(records)


def environment(model=None):
    values = dict(os.environ)
    local_values = {}
    env_file = ROOT / '.env'
    for raw_line in env_file.read_text(encoding='utf-8-sig').splitlines():
        line = raw_line.strip()
        if line and not line.startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            local_values[name.strip()] = value.strip().strip('"').strip("'")
    values.update(local_values)
    values.update(PIPELINE_ENV_FILE=str(env_file), PIPELINE_ENV_OVERRIDE='0',
                  KNOWLEDGE_CACHE_DIR=str(ROOT / '.runtime/knowledge_neowealth'),
                  KNOWLEDGE_CACHE_FILE='', DOMAIN_COMPILATION_MODE='simple',
                  TEST_QUERY_OFFSET='0', QUERY_SHUFFLE_SEED='',
                  PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1')
    if model is not None:
        preset = MODEL_PRESETS[model]
        region = (local_values.get('BEDROCK_REGION') or local_values.get('AWS_REGION')
                  or local_values.get('AWS_DEFAULT_REGION'))
        api_key = (local_values.get('AWS_BEDROCK_API_KEY')
                   or local_values.get('AWS_Bedrock_API_gpt_oss_120b')
                   or local_values.get('BEDROCK_API_KEY'))
        if not region or not api_key:
            raise ValueError('The local .env must contain an AWS Bedrock region and API key.')
        # Override only this child process, after reading .env. Every agent uses
        # BEDROCK_GPT_OSS_MODEL despite the legacy name of that setting.
        values.update(BEDROCK_GPT_OSS_MODEL=preset['id'], BEDROCK_REGION=region,
                      BEDROCK_BASE_URL=f'https://bedrock-runtime.{region}.amazonaws.com/openai/v1',
                      AWS_BEDROCK_API_KEY=api_key,
                      KNOWLEDGE_CACHE_DIR=str(ROOT / '.runtime' / preset['cache']))
        if model in {'deepseek-v3.1', 'deepseek-v3.2'}:
            # Bedrock V3.1/V3.2 allow at most 8K output tokens, including knowledge
            # compilation (the GPT-OSS configuration otherwise requests 32K).
            values['DOMAIN_MAX_OUTPUT_TOKENS'] = '8192'
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--check-inputs', action='store_true')
    parser.add_argument('--prepare-knowledge', action='store_true')
    parser.add_argument('--retry-errors-in-place', action='store_true',
                        help='Back up the report and retry saved execution errors, keeping successful rows.')
    parser.add_argument('--include-pending', action='store_true',
                        help='Also complete unsaved questions during an in-place error retry.')
    parser.add_argument('--model', choices=MODEL_PRESETS,
                        help='AWS Bedrock model preset; otherwise use the local .env model.')
    parser.add_argument('--output-dir', type=Path,
                        help='Results directory; defaults to a separate folder per model preset.')
    args = parser.parse_args(argv)
    if args.workers < 1 or args.limit < 0:
        parser.error('Workers must be positive and limit nonnegative.')
    if args.check_inputs and args.prepare_knowledge:
        parser.error('Choose check-inputs or prepare-knowledge.')
    if args.retry_errors_in_place and (args.limit or args.check_inputs or args.prepare_knowledge):
        parser.error('Retry errors cannot be combined with limit, check-inputs or prepare-knowledge.')
    if args.include_pending and not args.retry_errors_in_place:
        parser.error('include-pending requires retry-errors-in-place.')
    preset = MODEL_PRESETS.get(args.model, MODEL_PRESETS['gpt-oss'])
    output = (args.output_dir or ROOT / 'outputs' / preset['output']).resolve()
    if output != ROOT and ROOT not in output.parents:
        parser.error('Keep outputs inside this experiment folder.')
    try:
        env = environment(args.model)
    except ValueError as error:
        parser.error(str(error))
    count = prepare_questions(output / 'input_questions.jsonl')
    print(f'[INPUT] {count} NeoWealth questions; workers: {args.workers}', flush=True)
    if args.model:
        print(f"[MODEL] {args.model}: {env['BEDROCK_GPT_OSS_MODEL']}", flush=True)
        print(f"[CACHE] {env['KNOWLEDGE_CACHE_DIR']}", flush=True)
    command = [sys.executable, '-u', '-B', str(PACKAGE / 'run.py'),
               '--env-file', str(ROOT / '.env'), '--db', str(ROOT / 'newdb/neowealth.duckdb'),
               '--yaml-dir', str(ROOT / 'newdb/primitves_updated_final'),
               '--domain-intro', str(ROOT / 'newdb/01_domain_and_business_rules.md'),
               '--business-rules', str(ROOT / 'newdb/ALL_RULES_COMPILED/01_domain_and_business_rules.md'),
               '--questions', str(output / 'input_questions.jsonl'), '--output', str(output / 'raw_pipeline.csv'),
               '--workers', str(args.workers), '--limit', str(args.limit), '--knowledge-mode', 'simple']
    if args.check_inputs:
        command.append('--check-inputs')
    if args.prepare_knowledge:
        command.append('--prepare-knowledge')
    if args.retry_errors_in_place:
        command.append('--retry-errors-in-place')
    if args.include_pending:
        command.append('--include-pending')
    return subprocess.run(command, env=env, cwd=ROOT, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
