"""Offline paired audit and saved-plan validation. Never imported by runtime.

Grades/references are evaluation data only. Normalization receives only the
saved plan, its question and independently obtained source schema.
"""
import collections
import copy
import csv
import hashlib
import json
from pathlib import Path

from script_diff_llm.backends.kg import load_rdf_knowledge_graph
from script_diff_llm.backends.sql_schema import load_source_schema
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.specification import cleanup_query_spec

csv.field_size_limit(100_000_000)
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'outputs/openai_gpt_oss_120b/all/test1000'
RUNS = {'v2': BASE / 'generic_no_rules_v2_20261003', 'v4': BASE / 'generic_no_rules_v4'}


def read(path):
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    result = {r['Sample Row ID']: r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f'Duplicate IDs: {path}')
    return result


def main():
    sql = load_source_schema(str(ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db'))
    kg = load_rdf_knowledge_graph(str(ROOT / 'data/kg/wealth_management_diverse_schema.ttl'),
                                  'http://127.0.0.1:3030/wealth/query', 10)
    if not kg or not any(d.get('columns') for d in kg.values()):
        raise RuntimeError('Complete KG metadata unavailable; start Fuseki before auditing.')
    result, diagnostics, raw_runs, grade_runs = {}, [], {}, {}
    hashes = {}
    for version, folder in RUNS.items():
        raw = raw_runs[version] = read(folder / 'raw_pipeline.csv')
        grades = grade_runs[version] = read(folder / 'graded_pipeline_tera.csv')
        if set(raw) != set(grades):
            raise ValueError('Raw/graded ID coverage differs')
        counts, repairs = collections.Counter(), collections.Counter()
        for path in (folder / 'raw_pipeline.csv', folder / 'graded_pipeline_tera.csv'):
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for sample, row in raw.items():
            grade = grades[sample]
            for column in ('Question', 'Ground Truth', 'Node Traces', 'Pipeline Version'):
                if grade[column] != row[column]:
                    raise ValueError(f'Raw/graded content differs: {sample}, {column}')
            traces = json.loads(row['Node Traces'] or '{}')
            old_blocked, new_blocked = False, False
            for node_id, trace in traces.items():
                plan = trace.get('query_spec')
                if not isinstance(plan, dict) or not plan:
                    continue
                old_errors = trace.get('contract_errors', plan.get('contract_errors', []))
                old_blocked |= bool(old_errors)
                backend = trace.get('backend') or ('SQL' if trace.get('generated_sql') else 'KG')
                # Contract-blocked SQL nodes do not have generated_sql. Their
                # execution strategy is recorded in the saved Query_Spec.
                if plan.get('execution_strategy', '').endswith('_sql'):
                    backend = 'SQL'
                schema = sql if backend == 'SQL' else kg
                candidate = copy.deepcopy(plan)
                # Saved diagnostics describe the old validator; recompute them.
                candidate.pop('contract_errors', None)
                candidate.pop('contract_warnings', None)
                normalized = cleanup_query_spec(candidate, row['Question'], list(schema), str.lower,
                                                 schema_kind=backend.lower(), schema=schema)
                errors = split_contract_errors(validate_query_spec(normalized, schema, row['Question']))[0]
                new_blocked |= bool(errors)
                for repair in normalized.get('structural_repairs', []):
                    repairs[repair['evidence']] += 1
                diagnostics.append({'version': version, 'sample': sample, 'node': node_id,
                                    'grade': grade['New Status'], 'backend': backend,
                                    'old_errors': old_errors, 'new_errors': errors,
                                    'repairs': normalized.get('structural_repairs', [])})
            counts[f'{"blocked" if old_blocked else "clear"} -> {"blocked" if new_blocked else "clear"}'] += 1
            if old_blocked and not new_blocked:
                counts['recovered_saved_contracts'] += 1
        result[version] = {'rows': len(raw), 'grades': dict(collections.Counter(g['New Status'] for g in grades.values())),
                           'raw_status': dict(collections.Counter(r['New Status'] for r in raw.values())),
                           'saved_plan_revalidation': dict(counts), 'repair_evidence': dict(repairs)}
    if set(raw_runs['v2']) != set(raw_runs['v4']):
        raise ValueError('v2/v4 IDs differ')
    transitions = collections.Counter()
    lost_by_failure = collections.Counter()
    for sample, old in raw_runs['v2'].items():
        new = raw_runs['v4'][sample]
        if any(old[c] != new[c] for c in ('Question', 'Ground Truth')):
            raise ValueError(f'Questions/references changed: {sample}')
        before, after = grade_runs['v2'][sample]['New Status'], grade_runs['v4'][sample]['New Status']
        transitions[f'{before} -> {after}'] += 1
        if before == 'MATCH' and after != 'MATCH':
            lost_by_failure[new.get('Failure Stage') or 'executed'] += 1
    result['paired_grade_transitions'] = dict(transitions)
    result['lost_matches_by_failure_stage'] = dict(lost_by_failure)
    result['output_sha256'] = hashes
    result['limitation'] = 'Saved-spec acceptance is not execution or accuracy. No fresh model generation or grading was performed.'
    OUT.mkdir(exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    (OUT / 'plan_diagnostics.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'output_sha256'}, indent=2))


if __name__ == '__main__':
    main()
