"""Snapshot node failures, prepare/approve source-supported context, run raw only."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
csv.field_size_limit(10_000_000)
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-tag',default='node_errors_context_01')
parser.add_argument('--workers',type=int,default=4)
parser.add_argument('--dry-run',action='store_true')
args = parser.parse_args()
if not args.run_tag.replace('_','').replace('-','').isalnum() or args.workers < 1:
    parser.error('Invalid tag or worker count')
output = BASE / 'runs/gemini_3_8_flash/with_context' / args.run_tag
output.mkdir(parents=True,exist_ok=True)
subset = output / 'node_error_questions.csv'
source = BASE / 'runs/gemini_3_8_flash/without_context/run_01/raw_pipeline.csv'
context = ROOT / '01_domain_and_business_rules.md'
if not subset.exists():
    raw = list(csv.DictReader(source.open()))
    ids = {r['Sample Row ID'] for r in raw if r['New Status'] == 'DAG_NODE_ERROR'}
    original = ROOT / 'data/benchmarks/neowealth_test.csv'
    with original.open() as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        rows=[r for r in reader if r['global_question_id'] in ids]
    if len(rows) != len(ids) or not rows: raise ValueError('No errors or question ID mismatch')
    with subset.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    (output/'selection.json').write_text(json.dumps({'source_report':str(source),'snapshot_rows':len(raw),
        'selected_error_count':len(rows),'selected_ids':sorted(ids),'context_source':str(context),
        'context_sha256':hashlib.sha256(context.read_bytes()).hexdigest()},indent=2)+'\n')
selection=json.loads((output/'selection.json').read_text())
if hashlib.sha256(context.read_bytes()).hexdigest()!=selection['context_sha256']:
    raise ValueError('Context document changed; use a new run tag')
print('[CONTEXT RETRY] Frozen error questions:',selection['selected_error_count'],flush=True)
command=[sys.executable,'-u','-B',str(BASE/'run_context_subset.py'),'--subset',str(subset),
         '--run-tag',args.run_tag,'--workers',str(args.workers)]
if args.dry_run:
    raise SystemExit(subprocess.call(command+['--dry-run'],cwd=ROOT))
approval=output/'context_approval.json'
if not approval.exists():
    subprocess.run(command+['--prepare-context-only'],cwd=ROOT,check=True)
    state=json.loads((output/'domain_context_state.json').read_text())
    review=json.loads(Path(state['review_path']).read_text())
    approved={e['id']:e['evidence_hash'] for e in review['review'] if not e['errors']}
    approval.write_text(json.dumps({'fingerprint':state['fingerprint'],'approved':approved,
        'authorization':'User explicitly requested use of this database domain/business-rules file; only entries passing source/schema/conflict validation are approved.'},indent=2)+'\n')
    print('[CONTEXT RETRY] Approved validated document entries:',len(approved),flush=True)
subprocess.run(command+['--approval-file',str(approval)],cwd=ROOT,check=True)
print('[CONTEXT RETRY] Finished raw subset. No grader launched.',flush=True)
