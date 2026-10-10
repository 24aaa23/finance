"""Read-only result aggregation; no inference or grading changes."""
import csv,json,sys,hashlib,collections,math
from pathlib import Path
csv.field_size_limit(sys.maxsize)
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
runs={}
def read(p):
 with p.open() as f:return list(csv.DictReader(f))
def count(rows,key):return dict(collections.Counter(r.get(key,'') for r in rows))
def groups(raw,graded,key):
 out={}
 for r in raw:
  g=r.get(key,'');o=out.setdefault(g,{'n':0,'match':0,'partial':0,'execution_success':0})
  o['n']+=1;o['match']+=graded[r['Sample Row ID']]['New Status']=='MATCH';o['partial']+=graded[r['Sample Row ID']]['New Status']=='PARTIAL';o['execution_success']+=r['New Status']=='PIPELINE_SUCCESS'
 return out
for family,paths in [('improvement10', (ROOT/'ablations/improvement10_models/runs').glob('*/run_01/parallel_workers4/graded_pipeline_gpt_5_mini.csv')),('main_hybrid',(ROOT/'ablations/v5_test1000/runs').glob('*/*/reliability_v6_01/graded_pipeline_gpt_5_mini.csv'))]:
 for p in sorted(paths):
  raw=read(p.with_name('raw_pipeline.csv'));graded=read(p)
  if len(raw)!=1000 or len(graded)!=1000:continue
  model=p.relative_to(ROOT/'ablations').parts[2];condition='with_context' if family=='improvement10' else p.relative_to(ROOT/'ablations').parts[3]
  key=f'{family}/{model}/{condition}'
  rb={r['Sample Row ID']:r for r in raw};gb={r['Sample Row ID']:r for r in graded}
  assert len(rb)==len(gb)==1000 and rb.keys()==gb.keys()
  assert all(rb[k]['Question']==gb[k]['Question'] for k in rb)
  elapsed=sum(float(r.get('Elapsed Seconds') or 0) for r in raw)
  calls=sum(float(r.get('Model Calls') or 0) for r in raw)
  inp=sum(float(r.get('Generation Input Tokens') or 0) for r in raw);output=sum(float(r.get('Generation Output Tokens') or 0) for r in raw)
  latency=sum(float(r.get('Generation Latency Seconds') or 0) for r in raw)
  matches=sum(r['New Status']=='MATCH' for r in graded)
  backend=collections.Counter();single=0;contract=0
  for r in raw:
   if r.get('Node Backends'):
    values=set(json.loads(r['Node Backends']).values()) & {'SQL','KG'}
    backend['+'.join(sorted(values)) or 'none']+=1
    single+=len(json.loads(r['Node Backends']))==1
   if 'query_spec_contract' in (r.get('Failure Stage','')+' '+r.get('Node Traces','')).lower() and r['New Status']!='PIPELINE_SUCCESS':contract+=1
  runs[key]={'raw_path':str(p.with_name('raw_pipeline.csv').relative_to(ROOT)),'graded_path':str(p.relative_to(ROOT)),
   'raw_sha256':hashlib.sha256(p.with_name('raw_pipeline.csv').read_bytes()).hexdigest(),'graded_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
   'raw_statuses':count(raw,'New Status'),'grades':count(graded,'New Status'),'grader_labels':count(graded,'Grader Label'),'grader_models':count(graded,'Direct LLM Grader Model'),
   'n':1000,'mean_seconds':elapsed/1000,'summed_seconds':elapsed,'efficiency':matches/elapsed,
   'matches_among_successes':sum(gb[k]['New Status']=='MATCH' for k in rb if rb[k]['New Status']=='PIPELINE_SUCCESS'),
   'types':groups(raw,gb,'Query Type'),'difficulty':groups(raw,gb,'Difficulty'),'sources':groups(raw,gb,'Source CSV'),
   'node_backends':dict(backend),'single_node':single,'contract_failures':contract,
   'tokens':{'input':inp,'output':output,'calls':calls,'latency_s':latency,'missing_usage_calls':sum(float(r.get('Calls Missing Token Usage') or 0) for r in raw),'failed_calls':sum(float(r.get('Failed Model Calls') or 0) for r in raw)},
   'failure_stages':dict(collections.Counter(r.get('Failure Stage','') for r in raw if r['New Status']!='PIPELINE_SUCCESS'))}
  runs[key]['_raw']=rb;runs[key]['_graded']=gb
pairs={}
for model in ['gpt_oss_120b','deepseek_v3_2','gemma_3_27b_it']:
 for left,right,label in [(f'main_hybrid/{model}/without_context',f'main_hybrid/{model}/with_context',f'context/{model}'),(f'improvement10/{model}/with_context',f'main_hybrid/{model}/without_context',f'architecture/{model}/without'),(f'improvement10/{model}/with_context',f'main_hybrid/{model}/with_context',f'architecture/{model}/with')]:
  a=runs[left];b=runs[right];ar=a['_graded'];br=b['_graded'];assert ar.keys()==br.keys()
  gain=[k for k in ar if ar[k]['New Status']!='MATCH' and br[k]['New Status']=='MATCH'];loss=[k for k in ar if ar[k]['New Status']=='MATCH' and br[k]['New Status']!='MATCH']
  pairs[label]={'gain':len(gain),'loss':len(loss),'both_match':sum(ar[k]['New Status']==br[k]['New Status']=='MATCH' for k in ar),'question_text_differences':sum(ar[k]['Question']!=br[k]['Question'] for k in ar),'ground_truth_text_differences':sum(ar[k]['Ground Truth']!=br[k]['Ground Truth'] for k in ar),'gain_ids':gain,'loss_ids':loss}
for r in runs.values():r.pop('_raw');r.pop('_graded')
(OUT/'summary.json').write_text(json.dumps({'runs':runs,'pairs':pairs},indent=2))
for k,r in runs.items():print(k,r['grades'],'raw',r['raw_statuses'],'seconds',round(r['mean_seconds'],3),'tokens',r['tokens'])
for k,p in pairs.items():print(k,{a:b for a,b in p.items() if not a.endswith('_ids')})
