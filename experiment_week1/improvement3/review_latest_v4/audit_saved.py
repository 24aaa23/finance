"""Offline evidence inventory. No pipeline imports, credentials, or service calls."""
import ast
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[1]
SOURCE = BASE / 'run_pipeline_v4'
REPORTS = BASE / 'pipelien_output'
WORKBOOK = ROOT / 'query_specs_improevemnt/improvement1/dataset/verification_results_v2_sql_correct_442.xlsx'
csv.field_size_limit(100_000_000)

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def parse(value, default=None):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default

def workbook_records():
    # Read source XML only: never instantiate Excel or rewrite the workbook.
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(WORKBOOK) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)]
        records = []
        for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('s:sheetData/s:row', ns):
            values = {}
            for cell in row:
                col = re.sub(r'\d', '', cell.attrib['r'])
                raw = cell.find('s:v', ns)
                value = raw.text if raw is not None else ''.join(cell.itertext())
                values[col] = strings[int(value)] if cell.attrib.get('t') == 's' else value
            records.append(values)
    headers = records.pop(0)
    return [{headers[k]: v for k, v in row.items()} for row in records]

def short_step(step):
    return {k: v for k, v in step.items() if k not in {'strict_aggregation', 'preserve_null_groups', 'stage', 'output_schema'}}

def main():
    refs = workbook_records()
    reference = {r['global_question_id']: r for r in refs}
    cases, manifests = [], []
    for gradefile in sorted(REPORTS.glob('graded_v4_latest*_terra.csv')):
        stem = gradefile.name.removeprefix('graded_').removesuffix('_terra.csv')
        debugrows = read_csv(REPORTS / (stem + '_debug.csv'))
        debug = {r['Sample Row ID']: r for r in debugrows}
        grades = read_csv(gradefile)
        manifest = json.loads((REPORTS / (stem + '.csv.manifest.json')).read_text())
        mismatches = [name for name, expected in manifest['source_files'].items()
                      if not (SOURCE / name).exists() or hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != expected]
        manifests.append({'stem': stem, 'grades': len(grades), 'debug_rows': len(debugrows),
                          'duplicate_debug_ids': len(debugrows) - len(debug), 'source_mismatches': mismatches,
                          'configuration': manifest.get('configuration'), 'run_identity': manifest['run_identity']})
        for grade in grades:
            rid = grade['Sample Row ID']
            trace = debug.get(rid, {})
            ref = reference.get(rid, {})
            decoded = {k: parse(v, {'unparsed': v}) for k, v in trace.items() if k.startswith('Debug ') and v[:1] in '[{'}
            truncations = [k for k, v in decoded.items() if isinstance(v, dict) and v.get('truncated')]
            plan = decoded.get('Debug Final Spec', {})
            branches = decoded.get('Debug Subquestions', [])
            queries = decoded.get('Debug SPARQL', [])
            specs = decoded.get('Debug Query Specs', [])
            accepted = {}
            for entry in specs if isinstance(specs, list) else []:
                spec = entry.get('query_spec', {})
                if not spec.get('contract_errors'):
                    for retrieval in spec.get('retrieval_specs', []):
                        accepted[spec.get('branch_id') or spec.get('id')] = retrieval
            ground = parse(grade['Ground Truth'])
            expected = parse(ref.get('ground_truth_answer'))
            result = parse(grade['New Pipeline Result'])
            case = {'id': rid, 'short_id': rid.split(':')[-1], 'report': stem,
                    'question': grade['Question'], 'grade': grade['Grade Status'],
                    'reason': grade['Grade Reason'], 'status': grade['New Status'],
                    'validation': grade.get('Validation Reason'), 'answer_review': grade.get('Answer Review Status'),
                    'reference_found': bool(ref), 'ground_truth_matches_workbook': grade['Ground Truth'] == ref.get('ground_truth_answer'),
                    'reference_answer_text': ref.get('ground_truth_answer'),
                    'reference_json_parseable': parse(ref.get('ground_truth_answer'), '__INVALID_JSON__') != '__INVALID_JSON__',
                    'question_matches_workbook': grade['Question'] == ref.get('question'),
                    'sql': ref.get('sql_query'), 'expected': expected, 'result': result,
                    'expected_rows': len(expected) if isinstance(expected, list) else None,
                    'result_rows': len(result) if isinstance(result, list) else None,
                    'branches': branches, 'retrieved': decoded.get('Debug Retrieved Classes'),
                    'retrievals': accepted, 'queries': queries,
                    'steps': [short_step(s) for s in plan.get('final_steps', [])] if isinstance(plan, dict) else [],
                    'plan': plan, 'execution': decoded.get('Debug Execution Log'),
                    'repairs': decoded.get('Debug Repair Log'),
                    'requirements': decoded.get('Debug Answer Requirements'),
                    'operator_audit': decoded.get('Debug Operator Audit'), 'truncations': truncations}
            cases.append(case)
    inventory = []
    for path in sorted(SOURCE.rglob('*.py')):
        src = path.read_text(encoding='utf-8-sig')
        tree = ast.parse(src)
        inventory.append({'file': path.relative_to(SOURCE).as_posix(), 'lines': len(src.splitlines()),
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'definitions': [{'name': n.name, 'line': n.lineno} for n in ast.walk(tree)
                                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]})
    mc = [c for c in cases if c['short_id'].startswith('MC-')]
    summary = {'total': len(cases), 'unique_ids': len({c['id'] for c in cases}),
               'workbook_rows': len(refs), 'reference_missing': [c['id'] for c in cases if not c['reference_found']],
               'ground_truth_mismatches': [c['id'] for c in cases if not c['ground_truth_matches_workbook']],
               'reference_json_unparseable': [c['id'] for c in cases if not c['reference_json_parseable']],
               'question_mismatches': [c['id'] for c in cases if not c['question_matches_workbook']],
               'grades': dict(collections.Counter(c['grade'] for c in cases)),
               'statuses': dict(collections.Counter(c['status'] for c in cases)),
               'comparative_count': len(mc), 'comparative_grades': dict(collections.Counter(c['grade'] for c in mc)),
               'comparative_statuses': dict(collections.Counter(c['status'] for c in mc)),
               'truncated_debug_fields': dict(collections.Counter(k for c in cases for k in c['truncations'])),
               'source_inventory': inventory, 'manifests': manifests,
               'workbook_sha256': hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()}
    (HERE / 'evidence.json').write_text(json.dumps({'summary': summary, 'cases': cases}, indent=2), encoding='utf-8')
    for name, subset in [('comparative_digest.txt', mc), ('other_digest.txt', [c for c in cases if c not in mc])]:
        lines = []
        for c in sorted(subset, key=lambda c: c['id']):
            lines += [f"{c['short_id']} | {c['grade']} | expected={c['expected_rows']} actual={c['result_rows']}",
                      c['question'], 'GRADE: ' + c['reason'],
                      'SOURCES: ' + json.dumps([(b.get('id'), b.get('source_class'), b.get('question')) for b in c['branches']] if isinstance(c['branches'], list) else c['branches']),
                      'FILTERS: ' + json.dumps({k: v.get('filters') for k, v in c['retrievals'].items()}),
                      'STEPS: ' + json.dumps(c['steps']),
                      'SQL: ' + str(c['sql']), '']
        (HERE / name).write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'source_inventory'}, indent=2))

if __name__ == '__main__':
    main()
