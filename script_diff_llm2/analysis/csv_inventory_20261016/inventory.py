"""Read-only CSV audit. Writes inventory reports; never deletes source files."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import re
import datetime

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
csv.field_size_limit(100_000_000)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def audit(p):
    rel=str(p.relative_to(ROOT));parts=p.relative_to(ROOT).parts
    record={'path':rel,'absolute_path':str(p),'bytes':p.stat().st_size,'size_mb':round(p.stat().st_size/1e6,3),
            'area':parts[0] if len(parts)>1 else '(root)','family':parts[1] if len(parts)>2 else '',
            'role':'other','kind':'other_csv','rows':0,'unique_ids':'','expected_rows':'','row_status':'unknown',
            'matches':0,'partials':0,'mismatches':0,'grader_errors':0,'execution_successes':0,
            'status_counts':{},'sha256':'','duplicate_group':'','recommendation':'inspect','notes':[]}
    if record['area']=='analysis':record['role']='analysis'
    if any(s in rel.lower() for s in ('/shards/','/workers/','/worker_','/shard_')):record['role']='worker/shard'
    if any(s in rel.lower() for s in ('before_','backup','transient_rows','retry_rows')):record['role']='backup/retry subset'
    if '/source/' in rel:record['role']='source snapshot'
    if p.name == 'seed.csv':record['role']='backup/retry subset'
    if '/measurement/' in rel:record['role']='measurement sample'
    if 'raw_pipeline_debug' in p.name and record['role']=='other':record['role']='debug report'
    try:
        with p.open(newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f);columns=reader.fieldnames or []
            record['columns']=columns
            if any(x in columns for x in ('New Pipeline Result','Pipeline Result','pipeline_result')):
                record['kind']='graded' if any(x in columns for x in ('Original Grade','Grader Label','Grader Reason','Grading Reason')) or 'graded' in p.name.lower() else 'raw'
            elif any(x in columns for x in ('Grader Label','Original Grade')) or p.name.lower().startswith('graded'):
                record['kind']='graded'
            elif 'pipeline' in p.name.lower() or 'debug_report' in p.name.lower():record['kind']='raw'
            elif any(x in columns for x in ('question','global_question_id','ground_truth_answer','Question')) and record['role']=='other':record['role']='input/subset'
            if record['kind'] in ('raw','graded') and record['role']=='other':record['role']='primary report'
            counts=collections.Counter();gradecounts=collections.Counter();ids=set();ids_available=False
            for row in reader:
                record['rows']+=1
                for key in ('Sample Row ID','global_question_id','question_id','Question ID','Question'):
                    if row.get(key):ids.add(row[key]);ids_available=True;break
                status=row.get('New Status') or row.get('Status') or row.get('status') or ''
                counts[status]+=1
                grade=row.get('Original Grade') or row.get('Grading Status') or ''
                if not grade and str(status).upper() in ('MATCH','PARTIAL','MISMATCH'):grade=status
                gradecounts[str(grade).upper()]+=1
                if record['kind']=='graded' and (re.search(r'GRADER.*ERROR|API_ERROR|QUOTA_EXHAUST|TOKEN_LIMIT',str(status),re.I)
                    or re.search(r'insufficient_quota|quota.exhaust',row.get('Original Grade Reason') or '',re.I)):
                    record['grader_errors']+=1
            record['unique_ids']=len(ids) if ids_available else ''
            record['status_counts']=dict(counts)
            record['matches']=gradecounts['MATCH'];record['partials']=gradecounts['PARTIAL'];record['mismatches']=gradecounts['MISMATCH']
            record['execution_successes']=sum(n for k,n in counts.items() if k.upper() in ('PIPELINE_SUCCESS','SUCCESS'))
            record['graded_decisions']=record['matches']+record['partials']+record['mismatches']
    except Exception as e:record['notes'].append('Read error: '+str(e));record['row_status']='read_error'
    record['sha256']=digest(p)
    if record['kind'] in ('raw','graded'):
        # Restrict target inference to clear benchmark family paths or saved configuration.
        if record['role'] not in ('worker/shard','backup/retry subset'):
            for parent in p.parents:
                if parent==ROOT:break
                m=parent/'run_manifest.json'
                if m.is_file():
                    try:
                        c=json.loads(m.read_text()).get('configuration',{})
                        limit=c.get('settings',{}).get('TEST_QUERY_LIMIT')
                        if limit is not None:record['expected_rows']=int(limit)
                    except Exception:pass
                    break
            if record['expected_rows']=='':
                if 'test1000' in rel or 'improvement10_models/runs/' in rel or 'improvement11_gpt_oss_120b/runs/' in rel or 'improvement10_11_hybrid/runs/' in rel or 'hybrid_sql_only/runs/' in rel:record['expected_rows']=1000
                elif 'merged_context_repairs/' in rel or 'merged_full_context_repairs/' in rel:record['expected_rows']=768
                elif re.search(r'605',p.name):record['expected_rows']=605
                elif re.search(r'442',p.name):record['expected_rows']=442
        if record['role']=='measurement sample' and 'sample40' in rel:
            record['expected_rows']=40
        if record['row_status']!='read_error':
            expected=record['expected_rows']
            record['row_status']=('complete_rows' if record['rows']==expected else 'partial_rows' if record['rows']<expected else 'more_than_expected') if expected!='' else 'unknown_target'
        if record['unique_ids']!='' and record['unique_ids']<record['rows']:record['notes'].append('Repeated row IDs/question text: inspect before interpreting totals')
        if record['role']=='measurement sample':record['recommendation']='keep measurement evidence'
        elif record['role']=='debug report':record['recommendation']='archive/review debug report'
        elif record['role']=='worker/shard':record['recommendation']='review shard redundancy'
        elif record['role']=='backup/retry subset':record['recommendation']='archive/review backup'
        elif record['row_status']=='partial_rows':record['recommendation']='archive/review incomplete'
        else:record['recommendation']='keep pending review'
        if record['grader_errors']:record['notes'].append('Contains grader errors; not fully resolved')
    return record

records=[]
for p in sorted(ROOT.rglob('*.csv')):
    if OUT in p.parents or '.git' in p.parts:continue
    records.append(audit(p))
byhash=collections.defaultdict(list)
for r in records:byhash[r['sha256']].append(r)
duplicates=[]
for h,group in byhash.items():
    if len(group)<2:continue
    group.sort(key=lambda r:(r['role']!='primary report',r['row_status']!='complete_rows',len(r['path']),r['path']))
    number='D'+str(len(duplicates)+1).zfill(3)
    for r in group:r['duplicate_group']=number
    for r in group[1:]:
        if r['kind'] in ('raw','graded'):
            r['recommendation']='exact duplicate candidate'
            r['notes'].append('Byte-identical retained reference: '+group[0]['path'])
    duplicates.append({'id':number,'bytes_each':group[0]['bytes'],'recoverable_bytes':group[0]['bytes']*(len(group)-1),'paths':[r['path'] for r in group]})
primary=[r for r in records if r['kind'] in ('raw','graded')]
summary={'scope':str(ROOT),'date':'2026-10-16','csv_count':len(records),'csv_bytes':sum(r['bytes'] for r in records),
         'pipeline_csv_count':len(primary),'pipeline_bytes':sum(r['bytes'] for r in primary),
         'exact_duplicate_groups':duplicates,'duplicate_recoverable_bytes':sum(g['recoverable_bytes'] for g in duplicates),
         'counts_by_area':dict(collections.Counter(r['area'] for r in primary)),
         'roles':dict(collections.Counter(r['role'] for r in primary))}
(OUT/'inventory.json').write_text(json.dumps({'summary':summary,'files':records},indent=2))
fields=['path','kind','role','rows','unique_ids','expected_rows','row_status','size_mb','matches','partials','mismatches','grader_errors','execution_successes','recommendation','duplicate_group','sha256','notes']
for name,rows in [('all_csv_inventory.csv',records),('pipeline_csv_inventory.csv',primary),('cleanup_candidates.csv',[r for r in primary if r['recommendation'] not in ('keep pending review','keep measurement evidence')])]:
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for r in rows:w.writerow({**r,'notes':' | '.join(r['notes'])})
lines=['# Raw and graded CSV inventory — 16 October 2026','',
       f"Scope: `{ROOT}`. No source file was deleted or modified.",
       f"Found **{len(records)} CSVs ({summary['csv_bytes']/1e9:.2f} GB)**, including **{len(primary)} pipeline reports ({summary['pipeline_bytes']/1e9:.2f} GB)**. Sizes use decimal units.",'',
       'Targets inferred from filenames are provisional. Complete rows means the expected row count was reached, not that all executions or grades succeeded. Primary reports, individual workers, backups, source snapshots and evaluation inputs are distinguished. Grader labels/counts are reported as stored; graders and datasets are not interchangeable.','',
       '## Cleanup decisions','',
       '- Preserve final raw/graded pairs, manifests, logs, context bundles and source configuration for paper experiments.',
       '- Keep the NeoWealth original, retry, combined and grading reports together: the final 74.61% report is an adaptive recovery result whose provenance depends on those source reports.',
       '- Exact duplicate candidates have identical full-file SHA-256 hashes. Keep one copy and check scripts/manifests for path dependencies before removing the other.',
       '- Shard outputs, backups and incomplete runs are review candidates, not automatic deletions: some are the only record of a stopped experiment or needed for resume.',
       '- Do not delete question datasets, source snapshot assets, or primary reports solely because their accuracy is low.',
       '', '## Area summary','', '| Area | Raw | Graded | Size (MB) |','|---|---:|---:|---:|']
for area in sorted({r['area'] for r in primary}):
    group=[r for r in primary if r['area']==area];lines.append(f"| {area} | {sum(r['kind']=='raw' for r in group)} | {sum(r['kind']=='graded' for r in group)} | {sum(r['bytes'] for r in group)/1e6:.1f} |")
lines+=['','## Exact duplicate groups','',f"Potential space reclaimed by retaining one file per identical group: **{summary['duplicate_recoverable_bytes']/1e6:.1f} MB** across all CSVs.",'']
for g in duplicates:
    lines.append(f"### {g['id']} — {g['bytes_each']/1e6:.2f} MB each")
    lines.append('')
    for path in g['paths']:lines.append(f"- [{path}]({ROOT/path})")
    lines.append('')
lines+=['## All raw and graded reports','']
for area in ('ablations','outputs','historical_models','analysis'):
    group=[r for r in primary if r['area']==area]
    if not group:continue
    lines += ['### '+area,'','| File | Kind / role | Rows / target | MATCH / PARTIAL / MISMATCH | Grader errors | MB | Recommendation |','|---|---|---:|---:|---:|---:|---|']
    for r in group:
        labels=f"{r['matches']} / {r['partials']} / {r['mismatches']}" if r['kind']=='graded' else '—'
        target=f" / {r['expected_rows']}" if r['expected_rows']!='' else ''
        lines.append(f"| [{r['path']}]({r['absolute_path']}) | {r['kind']} / {r['role']} | {r['rows']}{target} | {labels} | {r['grader_errors']} | {r['size_mb']:.2f} | {r['recommendation']} |")
    lines.append('')
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))
