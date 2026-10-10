"""Complete raw runs, merge execution-success repairs, grade one full report."""
import argparse
import collections
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

csv.field_size_limit(10_000_000)
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
RUNS = BASE / 'runs/gemini_3_8_flash'
ORIGINAL = RUNS / 'without_context/run_01/raw_pipeline.csv'
CONTEXT = RUNS / 'with_context/node_errors_context_01'
MERGED = RUNS / 'merged_context_repairs/run_01'


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows, key):
    result = {r[key]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate question IDs: ' + key)
    return result


def expand_context_subset():
    _, original_rows = read_csv(ORIGINAL)
    originals = indexed(original_rows, 'Sample Row ID')
    fields, questions = read_csv(ROOT / 'data/benchmarks/neowealth_test.csv')
    question_map = indexed(questions, 'global_question_id')
    if set(originals) != set(question_map):
        raise ValueError('Original report is not complete; refusing partial merge')
    errors = {key for key, row in originals.items() if row['New Status'] == 'DAG_NODE_ERROR'}
    subset = CONTEXT / 'node_error_questions.csv'
    _, saved_subset = read_csv(subset)
    for row in saved_subset:
        if row != question_map.get(row['global_question_id']):
            raise ValueError('Previously selected question/reference changed')
    selection_path = CONTEXT / 'selection.json'
    selection = json.loads(selection_path.read_text())
    selected = errors | set(selection['selected_ids'])
    rows = [r for r in questions if r['global_question_id'] in selected]
    manifest_path = CONTEXT / 'run_manifest.json'
    previous_hash = sha(subset)
    if set(selection['selected_ids']) != selected:
        # Preserve the old manifest and subset; only input selection/limit changes.
        backup = CONTEXT / 'before_expansion'
        backup.mkdir(exist_ok=True)
        for path in (subset, selection_path, manifest_path):
            if path.exists() and not (backup / path.name).exists():
                (backup / path.name).write_bytes(path.read_bytes())
        write_csv(subset, fields, rows)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            config = manifest['configuration']
            source = config['sources']['INPUT_SAMPLE_FILE']
            if source['sha256'] != previous_hash:
                raise ValueError('Subset manifest hash mismatch')
            source['sha256'] = sha(subset)
            config['settings']['TEST_QUERY_LIMIT'] = str(len(rows))
            manifest['signature'] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        selection.update(snapshot_rows=len(original_rows), selected_error_count=len(rows),
                         selected_ids=sorted(selected), expansion_reason='User requested all final node errors with context, preserving existing retry rows')
        selection_path.write_text(json.dumps(selection, indent=2) + '\n')
    print('[COORDINATOR] Context subset:',len(rows),'questions; saved retry rows retained.',flush=True)


def merge_reports():
    fields, original_rows = read_csv(ORIGINAL)
    _, retry_rows = read_csv(CONTEXT / 'raw_pipeline.csv')
    originals = indexed(original_rows, 'Sample Row ID')
    retries = indexed(retry_rows, 'Sample Row ID')
    _, subset = read_csv(CONTEXT / 'node_error_questions.csv')
    if set(retries) != {r['global_question_id'] for r in subset}:
        raise ValueError('Context retry report is incomplete')
    provenance_fields = ['Answer Run Condition','Context Retry Status','Original Execution Status']
    fields = fields + [f for f in provenance_fields if f not in fields]
    result = []
    recovered = []
    for original in original_rows:
        key = original['Sample Row ID']
        retry = retries.get(key)
        if retry and (retry['Question'] != original['Question'] or retry['Ground Truth'] != original['Ground Truth']):
            raise ValueError('Question/reference mismatch: ' + key)
        use_retry = original['New Status'] != 'PIPELINE_SUCCESS' and retry and retry['New Status'] == 'PIPELINE_SUCCESS'
        row = dict(retry if use_retry else original)
        row['Answer Run Condition'] = 'with_context_retry' if use_retry else 'without_context'
        row['Context Retry Status'] = retry['New Status'] if retry else ''
        row['Original Execution Status'] = original['New Status']
        result.append(row)
        if use_retry: recovered.append(key)
    if len(result) != 768 or len(originals) != 768:
        raise ValueError('Expected exactly 768 unique questions')
    destination = MERGED / 'raw_pipeline.csv'
    write_csv(destination, fields, result)
    (MERGED / 'merge_summary.json').write_text(json.dumps({
        'original_report':str(ORIGINAL),'original_sha256':sha(ORIGINAL),
        'context_report':str(CONTEXT/'raw_pipeline.csv'),'context_sha256':sha(CONTEXT/'raw_pipeline.csv'),
        'merged_rows':len(result),'recovered_execution_successes':len(recovered),'recovered_ids':recovered,
        'statuses':dict(collections.Counter(r['New Status'] for r in result)),
        'policy':'Retain original execution successes; replace failed originals only with successful context retries. No reference-answer-based selection.',
        'evaluation_design':'Adaptive recovery experiment; not a full-dataset with-context ablation.',
    },indent=2)+'\n')
    print('[COORDINATOR] Merged',len(result),'rows; recovered',len(recovered),'execution successes.',flush=True)
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--grader-workers',type=int,default=4)
    args=parser.parse_args()
    if min(args.workers,args.grader_workers)<1:parser.error('Worker counts must be positive')
    MERGED.mkdir(parents=True,exist_ok=True)
    with (MERGED/'coordinator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        _, rows=read_csv(ORIGINAL)
        if len(rows)<768:
            print('[COORDINATOR] Completing original report:',len(rows),'/768 saved. No original grader will launch.',flush=True)
            subprocess.run([sys.executable,'-u','-B',str(BASE/'run_raw.py'),'--run-tag','run_01','--workers',str(args.workers),'--dag-workers','1'],cwd=ROOT,check=True)
        expand_context_subset()
        subprocess.run([sys.executable,'-u','-B',str(BASE/'retry_node_errors_context.py'),'--run-tag','node_errors_context_01','--workers',str(args.workers)],cwd=ROOT,check=True)
        raw=merge_reports()
        subprocess.run([sys.executable,'-u','-B',str(ROOT/'runners/grade_gpt_5_mini.py'),'--raw',str(raw),'--output',str(MERGED/'graded_pipeline_gpt_5_mini.csv'),'--workers',str(args.grader_workers),'--save-every','1'],cwd=ROOT,check=True)
        print('[COORDINATOR] Combined grading finished.',flush=True)

if __name__=='__main__':
    main()
