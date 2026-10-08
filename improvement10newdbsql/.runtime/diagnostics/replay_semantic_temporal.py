"""Offline plan replay; preserves reports and never uses reference answers."""
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'run_pipeline_v3_sql _/tests'))
from support import load, registry

csv.field_size_limit(100000000)
folder = ROOT / 'outputs/full_run'
with (folder / 'raw_pipeline.csv').open(encoding='utf-8-sig', newline='') as handle:
    failed = {row['Sample Row ID'] for row in csv.DictReader(handle) if row['New Status'] == 'FINAL_SPEC_ERROR'}
replayed = []
for line in (folder / 'raw_pipeline_debug.jsonl').read_text(encoding='utf-8').splitlines():
    row = json.loads(line)
    if row['Sample Row ID'] not in failed:
        continue
    repairs = json.loads(row.get('Debug Repair Log') or '{}').get('stage_repairs', [])
    candidates = [a['spec'] for a in repairs if a.get('stage') == 'Final_Spec' and isinstance(a.get('spec'), dict)]
    profiles = json.loads(row.get('Debug Branch Profiles') or '[]')
    schemas = {p['id']: p['fields'] for p in profiles}
    contract = json.loads(row.get('Debug Query Understanding') or '{}')
    item = {'id': row['Sample Row ID'], 'candidates': []}
    for index, plan in enumerate(candidates):
        spec = load('spec_runtime').compile_spec(plan, schemas)
        errors = spec['contract_errors'] + load('query_understanding').final_contract_errors(spec, contract)
        entry = {'attempt': index + 1, 'errors': errors}
        if not errors:
            datasets = {}
            for profile in profiles:
                result = load('duckdb_backend').run_sql(profile['executed_sparql'], ROOT / 'newdb/neowealth.duckdb')
                if result['status'] != 'success':
                    raise RuntimeError(result)
                datasets[profile['id']] = result['data']
            result, log = load('execution').execute_spec(spec, datasets, registry(), dataset_schemas=schemas)
            entry.update(execution_errors=load('execution').execution_errors(log), row_count=len(result))
        item['candidates'].append(entry)
    replayed.append(item)
summary = {'scope': 'Offline saved-plan replay with saved retrieval SQL on read-only database; no reference answers used, model calls or report edits.',
           'failures': len(failed), 'replayed': len(replayed),
           'contract_clear': sum(any(not a['errors'] for a in r['candidates']) for r in replayed),
           'execution_clear': sum(any(not a['errors'] and not a.get('execution_errors', []) for a in r['candidates']) for r in replayed),
           'rows': replayed}
Path(__file__).with_name('semantic_temporal_saved_plan_replay.json').write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}))
for row in replayed:
    print(row['id'], [(a['attempt'], len(a['errors']), len(a.get('execution_errors', [])), a.get('row_count')) for a in row['candidates']])
