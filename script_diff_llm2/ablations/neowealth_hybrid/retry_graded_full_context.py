"""Wait for complete grading; retry PARTIAL/MISMATCH using every context file."""
import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
csv.field_size_limit(10_000_000)
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
GRADED=BASE/'runs/gemini_3_8_flash/merged_context_repairs/run_01/graded_pipeline_gpt_5_mini.csv'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-tag',default='partial_mismatch_full_context_01')
parser.add_argument('--workers',type=int,default=12)
parser.add_argument('--dry-run',action='store_true')
args=parser.parse_args()
if not args.run_tag.replace('_','').replace('-','').isalnum() or args.workers<1:parser.error('Invalid run tag/workers')
output=BASE/'runs/gemini_3_8_flash/with_context'/args.run_tag
output.mkdir(parents=True,exist_ok=True)
with (output/'supervisor.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    subset=output/'partial_mismatch_questions.csv'
    bundle_path=output/'full_context_bundle.json'
    if not subset.exists():
        previous=-1
        while True:
            try:
                with GRADED.open() as f:graded=list(csv.DictReader(f))
            except (FileNotFoundError,csv.Error):graded=[]
            if len(graded)==768:break
            if len(graded)!=previous:
                print('[FULL CONTEXT] Waiting for completed grading:',len(graded),'/768',flush=True);previous=len(graded)
            if args.dry_run:raise SystemExit('Dry-run selection requires complete grading first')
            time.sleep(15)
        ids={r['Sample Row ID'] for r in graded if r.get('Original Grade','').strip().upper() in {'PARTIAL','MISMATCH'} and r.get('New Status')!='SKIPPED_BY_USER'}
        with (ROOT/'data/benchmarks/neowealth_test.csv').open() as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r['global_question_id'] in ids]
        if not rows or len(rows)!=len(ids):raise ValueError('Selected question IDs missing or duplicated')
        files=[ROOT/'01_domain_and_business_rules.md',*sorted((ROOT/'primitves_updated_final').glob('*.yaml'))]
        if len(files)!=22:raise ValueError('Expected domain/rules document and all 21 primitive YAMLs')
        documents=[];manifest=[]
        for p in files:
            content=p.read_text(encoding='utf-8');digest=hashlib.sha256(p.read_bytes()).hexdigest()
            documents.append({'name':p.name,'content':content})
            manifest.append({'path':str(p),'name':p.name,'sha256':digest,'bytes':p.stat().st_size})
        bundle_path.write_text(json.dumps({'documents':documents,'manifest':manifest,'mode':'full_documents_no_quarantine'},ensure_ascii=False,indent=2)+'\n')
        with subset.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        (output/'selection.json').write_text(json.dumps({'graded_source':str(GRADED),'graded_sha256':hashlib.sha256(GRADED.read_bytes()).hexdigest(),
            'labels':['PARTIAL','MISMATCH'],'selected_count':len(rows),'selected_ids':sorted(ids),'excluded_user_skipped':True,
            'context_files':manifest,'quarantined_documents':[],
            'evaluation_design':'Adaptive context recovery on graded failures; not a fresh full-dataset ablation. Grader reasons and reference answers are not context.'},indent=2)+'\n')
    selection=json.loads((output/'selection.json').read_text())
    print('[FULL CONTEXT] Selected',selection['selected_count'],'partial/mismatch questions; 22 complete context files.',flush=True)
    cmd=[sys.executable,'-u','-B',str(BASE/'run_full_context_subset.py'),'--subset',str(subset),'--context-bundle',str(bundle_path),'--run-tag',args.run_tag,'--workers',str(args.workers)]
    if args.dry_run:cmd+=['--dry-run']
    subprocess.run(cmd,cwd=ROOT,check=True)
    print('[FULL CONTEXT] Raw subset finished. No grader launched.',flush=True)
