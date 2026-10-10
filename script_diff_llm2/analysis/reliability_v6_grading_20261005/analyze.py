"""Snapshot existing grades; never invoke models or modify saved run outputs."""
import collections
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys

csv.field_size_limit(sys.maxsize)
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def parsed(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def main():
    snapshot = {'time_ist': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat(),
                'run_tag': 'reliability_v6_01', 'runs': []}
    nonmatches, identity_checks = [], []
    for path in sorted((ROOT / 'ablations/v5_test1000/runs').glob('*/*/reliability_v6_01/graded_pipeline_gpt_5_mini.csv')):
        contents = path.read_bytes()
        rows = list(csv.DictReader(contents.decode().splitlines(keepends=True)))
        summary = {'model': path.parts[-4], 'condition': path.parts[-3], 'path': str(path),
                   'sha256_at_snapshot': hashlib.sha256(contents).hexdigest(), 'rows': len(rows),
                   'complete_row_coverage': len(rows) == 1000,
                   'grades': dict(collections.Counter(row['New Status'] for row in rows))}
        snapshot['runs'].append(summary)
        if len(rows) != 1000:
            continue
        summary['execution'] = dict(collections.Counter(row['Final Query Status'] for row in rows))
        summary['failure_stages'] = dict(collections.Counter(row['Failure Stage'] for row in rows if row['Final Query Status'] == 'error'))
        summary['grade_by_execution'] = {}
        for execution in sorted(summary['execution']):
            summary['grade_by_execution'][execution] = dict(collections.Counter(row['New Status'] for row in rows if row['Final Query Status'] == execution))
        summary['groups'] = {}
        for field in ('Difficulty', 'Query Type', 'sheet'):
            counts = collections.defaultdict(collections.Counter)
            for row in rows:
                key = row['Sample Row ID'].split(':')[0] if field == 'sheet' else row[field]
                counts[key][row['New Status']] += 1
            summary['groups'][field] = dict(counts)
        for row in rows:
            if row['New Status'] == 'MATCH':
                continue
            nonmatches.append({'model': summary['model'], 'condition': summary['condition'],
                               'id': row['Sample Row ID'], 'grade': row['New Status'],
                               'execution': row['Final Query Status'], 'failure_stage': row['Failure Stage'],
                               'question': row['Question'], 'reason': row['Comparison / Comments']})
            ground, answer = parsed(row['Ground Truth']), parsed(row['New Pipeline Result'])
            if not isinstance(ground, list) or not isinstance(answer, list) or not ground or not answer:
                continue
            if not all(isinstance(item, dict) for item in ground + answer):
                continue
            fields = [key for key in ground[0] if key.endswith('_id')
                      and all(key in item for item in ground + answer)]
            full_rows_equal = collections.Counter(json.dumps(item, sort_keys=True) for item in ground) == collections.Counter(json.dumps(item, sort_keys=True) for item in answer)
            for field in fields:
                left, right = (collections.Counter(str(item[field]) for item in data) for data in (ground, answer))
                identity_checks.append({'id': row['Sample Row ID'], 'grade': row['New Status'], 'key': field,
                    'ground_rows': len(ground), 'answer_rows': len(answer),
                    'same_key_multiset': left == right, 'same_key_set': set(left) == set(right),
                    'same_full_row_multiset': full_rows_equal,
                    'missing_unique_keys': len(set(left) - set(right)), 'extra_unique_keys': len(set(right) - set(left)),
                    'ground_chars': len(row['Ground Truth']), 'answer_chars': len(row['New Pipeline Result'])})
    (OUT / 'summary.json').write_text(json.dumps(snapshot, indent=2))
    for name, records in [('nonmatches.csv', nonmatches), ('identity_checks.csv', identity_checks)]:
        with (OUT / name).open('w', newline='') as handle:
            if records:
                writer = csv.DictWriter(handle, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    print(json.dumps([{k: run[k] for k in ('model', 'condition', 'rows', 'grades')} for run in snapshot['runs']]))
    print('Exact full-row multisets among identity audits:', sorted({row['id'] for row in identity_checks if row['same_full_row_multiset']}))


if __name__ == '__main__':
    main()
