"""Offline audit of saved reports; never called by the production pipeline.

Run with /usr/bin/python3 analysis/pipeline_audit_2026_10_02/reproduce.py.
Use --replay-sql to repeat bounded read-only NULL-group diagnostics.
No model or grader calls. Existing reports are never modified.
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import sqlite3
import time

csv.field_size_limit(100_000_000)
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
RUN = ROOT / 'outputs/openai_gpt_oss_120b/all/test1000'


def read(name):
    with (RUN / name).open() as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-sql', action='store_true')
    args = parser.parse_args()
    current = read('graded_pipeline_openai_gpt_oss_120b_all_test1000_rerun_grader2.csv')
    raw_rows = read('raw_pipeline_openai_gpt_oss_120b_all_test1000_rerun.csv')
    previous = read('graded_pipeline_1000_test_direct_llm_terra.csv')
    raw = {row['Sample Row ID']: row for row in raw_rows}
    old = {row['Sample Row ID']: row for row in previous}
    assert len(raw) == len(raw_rows) == 1000
    assert len(old) == len(previous) == 1000
    assert len({row['Sample Row ID'] for row in current}) == len(current) == 1000
    assert set(raw) == set(old) == {row['Sample Row ID'] for row in current}
    for key in ('Question', 'Ground Truth', 'New Pipeline Result', 'Generated SPARQL'):
        assert all(row[key] == raw[row['Sample Row ID']][key] for row in current), key
    print('Current:', dict(collections.Counter(row['New Status'] for row in current)))
    print('Previous:', dict(collections.Counter(row['New Status'] for row in previous)))
    for key in ('DAG Sequence', 'Source CSV', 'Difficulty', 'Query Type', 'Validation Is Valid'):
        counts = collections.defaultdict(collections.Counter)
        for row in current:
            counts[row[key]][row['New Status']] += 1
        print(key, json.dumps(counts, indent=2))
    transitions = collections.Counter((old[row['Sample Row ID']]['New Status'], row['New Status']) for row in current)
    print('Transitions:', dict(transitions))
    print('Political reinterpretation:', dict(collections.Counter(
        row['New Status'] for row in current if 'political' in row['Node Traces'].lower())))
    print('Question traces with placeholder namespace:', sum(
        any('http://example.org/' in trace.get('generated_sparql', '')
            for trace in json.loads(row['Node Traces'] or '{}').values()) for row in current))
    if not args.replay_sql:
        return
    db = ROOT / 'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db'
    results = []
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        for row in current:
            if not (row['New Status'] == 'PARTIAL' and row['DAG Sequence'] == 'Q1:Subquery(SQL)'
                    and 'null' in row['Original Grade Reason'].lower()):
                continue
            deadline = time.monotonic() + 2
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            try:
                rows = [dict(value) for value in conn.execute(row['Generated SPARQL'])]
                answer = json.loads(row['New Pipeline Result'])
                gt = json.loads(row['Ground Truth'])
                spec = json.loads(row['Query Spec'])
                groups = [group['output_name'] for group in spec.get('group_by', [])]
                keys = list(gt[0]) if gt and isinstance(gt[0], dict) else []

                def projection(data):
                    if not keys or not all(all(key in value for key in keys) for value in data):
                        return None
                    return collections.Counter(json.dumps({key: value[key] for key in keys}, sort_keys=True)
                                               for value in data)

                actual, expected = projection(rows), projection(gt)
                results.append({'id': row['Sample Row ID'], 'query_rows': len(rows),
                                'saved_answer_rows': len(answer), 'gt_rows': len(gt),
                                'query_null_groups': sum(any(value.get(group) is None for group in groups) for value in rows),
                                'strict_projected_equal': actual is not None and actual == expected, 'error': ''})
            except (sqlite3.Error, ValueError, TypeError, KeyError) as error:
                results.append({'id': row['Sample Row ID'], 'error': str(error)})
    (OUTPUT / 'sql_null_replay.json').write_text(json.dumps(results, indent=2))
    print('SQL replay:', len(results), 'exact projected results:', sum(
        row.get('strict_projected_equal', False) for row in results))
    print('Queries with more rows than saved answer:', sum(
        row.get('query_rows', 0) > row.get('saved_answer_rows', 0) for row in results))


if __name__ == '__main__':
    main()
