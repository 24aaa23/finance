"""Snapshot saved reports without invoking the pipeline or grader."""
import csv,json,collections,statistics,hashlib
from pathlib import Path
csv.field_size_limit(100_000_000)
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
paths=list((ROOT/'ablations/v5_test1000/runs').rglob('raw_pipeline.csv'))
base=ROOT/'outputs/openai_gpt_oss_120b/all/test1000'
paths += [base/folder/'raw_pipeline.csv' for folder in ['generic_no_rules_v5','context_v5_01']]
summary={};details=[];datasets={}
for p in sorted(paths):
 if not p.is_file():continue
 rs=list(csv.DictReader(p.open()));byid={r['Sample Row ID']:r for r in rs};assert len(rs)==len(byid)
 name=str(p.parent.relative_to(ROOT));datasets[name]=byid
 failure=collections.Counter();errors=collections.Counter();operators=collections.Counter();selected=0;nodes=collections.Counter();times=[];single_outputs=0
 for r in rs:
  traces=json.loads(r['Node Traces'] or '{}');nodes[len(traces)]+=1
  if r['Elapsed Seconds']:times.append(float(r['Elapsed Seconds']))
  selected+=int('domain_context_trace' in r['Node Traces'])
  for n in traces.values():
   if n.get('status')=='error':
    stage=n.get('failure_stage') or 'unknown';failure[stage]+=1
    if stage=='unknown':operators[str(n.get('operator'))]+=1
    for error in n.get('contract_errors',[]):
     key=error.split(':',1)[0];errors[key]+=1
    details.append({'run':name,'id':r['Sample Row ID'],'question':r['Question'],'node':n.get('node_id'),'operator':n.get('operator'),'stage':stage,'errors':json.dumps(n.get('contract_errors',[])),'validation_reason':n.get('pre_scan_validation_reason',''),'description':n.get('description','')})
  if len(traces)==1 and next(iter(traces.values()),{}).get('declared_outputs'):single_outputs+=1
 grades={}
 for gp in sorted(p.parent.glob('graded*.csv')):
  gs=list(csv.DictReader(gp.open()));gd={r['Sample Row ID']:r for r in gs}
  grades[gp.name]={'rows':len(gs),'statuses':dict(collections.Counter(r['New Status'] for r in gs)),'model':dict(collections.Counter(r.get('Direct LLM Grader Model','') for r in gs)),'missing_raw_ids':len(byid.keys()-gd.keys()),'sha256':hashlib.sha256(gp.read_bytes()).hexdigest()}
 summary[name]={'raw_rows':len(rs),'statuses':dict(collections.Counter(r['New Status'] for r in rs)),'failure_nodes':dict(failure),'contract_error_prefixes':dict(errors),'unsupported_operators':dict(operators),'nodes':dict(nodes),'rows_with_context_trace':selected,'single_nodes_with_declared_outputs':single_outputs,'latency_seconds':{'mean':statistics.mean(times),'median':statistics.median(times),'p95':sorted(times)[int(.95*(len(times)-1))]} if times else {},'families':{f:dict(collections.Counter(r['New Status'] for r in rs if r['Source CSV']==f)) for f in sorted({r['Source CSV'] for r in rs})},'graded_reports':grades,'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
pairs={}
for name,rs in datasets.items():
 if '/with_context/' not in name:continue
 other=name.replace('/with_context/','/without_context/')
 if other not in datasets:continue
 old=datasets[other];common=rs.keys()&old.keys();assert all(rs[i][k]==old[i][k] for i in common for k in ['Question','Ground Truth'])
 pairs[name]={'shared_rows':len(common),'raw_status_transitions':dict(collections.Counter(old[i]['New Status']+' -> '+rs[i]['New Status'] for i in common))}
caches={}
for p in (ROOT/'ablations/v5_test1000/context_cache').rglob('*.json'):
 if '.failure.' in p.name:continue
 d=json.loads(p.read_text());es=d.get('review',[])
 caches[str(p.relative_to(ROOT))]={'active':sum(e.get('active',False) for e in es),'active_kinds':dict(collections.Counter(e.get('kind') for e in es if e.get('active'))),'inactive_errors':dict(collections.Counter(x for e in es for x in e.get('errors',[]))),'quarantined':d.get('quarantined_documents',[])}
(OUT/'summary.json').write_text(json.dumps({'runs':summary,'paired_raw_comparisons':pairs,'context_cache_review':caches},indent=2)+'\n')
with (OUT/'failure_nodes.csv').open('w',newline='') as h:
 w=csv.DictWriter(h,fieldnames=list(details[0]));w.writeheader();w.writerows(details)
for name,d in summary.items():print(name,d['raw_rows'],d['statuses'],'grades',d['graded_reports'],'operators',d['unsupported_operators'],'latency',d['latency_seconds'])
print('cache',json.dumps(caches,indent=2))
