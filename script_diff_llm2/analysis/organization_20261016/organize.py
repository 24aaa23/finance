"""One-time local organization; preserve retained reports and runtime interfaces."""
from pathlib import Path
import csv
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
AUDIT=ROOT/'analysis/csv_inventory_20261016'
retained=json.loads((AUDIT/'cleanup_keep_selected_result.json').read_text())['preserved_files']
changes=[]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()

# Record source and credentials integrity without writing credential content/hashes.
code={str(p.relative_to(ROOT)):sha(p) for folder in ('src','runners') for p in (ROOT/folder).rglob('*.py')}
secrets={p:sha(p) for p in ROOT.rglob('*.env') if p.is_file()}
for p,h in retained.items():
    if not Path(p).is_file() or sha(Path(p))!=h:raise RuntimeError('Retained report changed: '+p)

def move_alias(old,new):
    source=ROOT/old;target=ROOT/new
    if source.is_symlink():return
    if not source.exists():return
    if target.exists():raise RuntimeError('Destination exists: '+str(target))
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.move(str(source),str(target))
    source.symlink_to(os.path.relpath(target,source.parent),target_is_directory=target.is_dir())
    changes.append({'action':'move_with_compatibility_link','from':old,'to':new})

assets=[
('wealth_management_1000_test_set_questions.xlsx','data/benchmarks/wmi/questions_1000.xlsx'),
('final_605_question.csv','data/benchmarks/wmi/questions_development_605.csv'),
('216_questions_full_results.json','data/benchmarks/wmi/full_answers_216.json'),
('neowealth-master-question-bank_FINAL_DELIVERABLE.xlsx','data/benchmarks/neowealth/questions.xlsx'),
('neowealth.duckdb','data/sql/neowealth/neowealth.duckdb'),
('kg_output_neowealth','data/kg/neowealth'),
('domain_intro.prompt','data/context/wmi/domain_intro.prompt'),
('phase0_business_rules.md','data/context/wmi/phase0_business_rules.md'),
('01_domain_and_business_rules.md','data/context/neowealth/domain_and_business_rules.md'),
('primitves_updated_final','data/context/neowealth/primitives'),
('README_V5_RUN_GUIDE.md','docs/guides/v5_run_guide.md'),
('README_RELIABILITY_V6.md','docs/guides/reliability_v6.md'),
('CHANGES.md','docs/history/CHANGES.md'),
('run','runtime/fuseki'),
('pipelien_output','outputs/legacy_grader_logs'),
]
for old,new in assets:move_alias(old,new)
# Remove the verified duplicate workbook, leaving a compatibility alias.
duplicate=ROOT/'neowealth-master-question-bank_FINAL_DELIVERABLE (1).xlsx'
original=ROOT/'data/benchmarks/neowealth/questions.xlsx'
if duplicate.is_file() and not duplicate.is_symlink():
    if sha(duplicate)!=sha(original):raise RuntimeError('Duplicate workbook is different; refusing removal')
    size=duplicate.stat().st_size;duplicate.unlink()
    duplicate.symlink_to(os.path.relpath(original,ROOT))
    changes.append({'action':'deduplicate_workbook_with_alias','path':duplicate.name,'bytes_reclaimed':size})
# Preserve old navigation before replacing it.
for name in ('README.md','structure.md'):
    p=ROOT/name;dest=ROOT/'docs/history'/f'{p.stem}_before_organization_20261016.md'
    dest.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and not dest.exists():dest.write_bytes(p.read_bytes())
# Archive only abandoned run directories; selected-run ancestors remain in place.
keep_paths=[Path(p) for p in retained]
for family in sorted((ROOT/'ablations').iterdir()):
    runs=family/'runs'
    if not runs.is_dir():continue
    depth=3 if family.name in ('v5_test1000','hybrid_sql_only','gemini_3_8_flash','azure_gpt_oss_120b','neowealth_hybrid') else 2
    candidates=[runs]
    for _ in range(depth):candidates=[child for parent in candidates for child in parent.iterdir() if child.is_dir() and not child.is_symlink()]
    for run in candidates:
        if any(run in p.parents for p in keep_paths):continue
        destination=ROOT/'archive/experiments'/run.relative_to(ROOT/'ablations')
        if destination.exists():raise RuntimeError('Archive destination exists: '+str(destination))
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(run),str(destination))
        changes.append({'action':'archive_unretained_run','from':str(run.relative_to(ROOT)),'to':str(destination.relative_to(ROOT))})
    for name in ('launcher_logs',):
        p=family/name
        if p.is_dir():
            dest=ROOT/'archive/launcher_logs'/family.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(p),str(dest))
            changes.append({'action':'archive_launcher_logs','from':str(p.relative_to(ROOT)),'to':str(dest.relative_to(ROOT))})
# Remove reproducible Python/test caches, keeping source files untouched.
cache_bytes=0;cache_count=0
for p in sorted(ROOT.rglob('*'),key=lambda p:len(p.parts),reverse=True):
    if p.is_dir() and not p.is_symlink() and p.name in ('__pycache__','.pytest_cache'):
        cache_bytes+=sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
        shutil.rmtree(p);cache_count+=1
stub=ROOT/'init'
if stub.is_file() and not stub.read_bytes().strip():
    stub.unlink();changes.append({'action':'remove_empty_placeholder','path':'init'})
# Prune empty directories left by the earlier CSV cleanup, outside source/tools.
empty_count=0
for top in ('ablations','outputs','historical_models'):
    for p in sorted((ROOT/top).rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if p.is_dir() and not p.is_symlink() and '/source/' not in str(p) and not any(p.iterdir()):
            p.rmdir();empty_count+=1
# Make a compact retained-results view without duplicating or relocating CSVs.
with (AUDIT/'RETAINED_RUNS.csv').open() as f:run_records=list(csv.DictReader(f))
for r in run_records:
    directory=ROOT/'results/retained'/r['id'];directory.mkdir(parents=True,exist_ok=True)
    for kind in ('raw','graded'):
        target=Path(r[kind]);link=directory/(kind+'.csv')
        if not link.exists():link.symlink_to(os.path.relpath(target,link.parent))
# Verify all protected content and compatibility aliases.
for p,h in retained.items():
    if sha(Path(p))!=h:raise RuntimeError('Retained data integrity failure: '+p)
for p,h in secrets.items():
    if not p.is_file() or sha(p)!=h:raise RuntimeError('Credential file changed: '+str(p))
for rel,h in code.items():
    if sha(ROOT/rel)!=h:raise RuntimeError('Pipeline source changed: '+rel)
result={'scope':str(ROOT),'changes':changes,'cache_directories_removed':cache_count,'cache_bytes_removed':cache_bytes,
        'empty_directories_removed':empty_count,'retained_reports_verified':len(retained),'source_python_files_verified':len(code),
        'credential_files_verified':len(secrets),'pipeline_workflow_changed':False}
(OUT/'organization_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('changes',)},indent=2))
print('Assets/compatibility moves:',sum(x['action']=='move_with_compatibility_link' for x in changes))
print('Archived runs:',sum(x['action']=='archive_unretained_run' for x in changes))
