"""Offline snapshot audit; no pipeline imports, model calls, or output mutations."""
import csv, json, hashlib, collections, statistics, importlib.util
from pathlib import Path
csv.field_size_limit(100_000_000)
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'outputs/openai_gpt_oss_120b/all/test1000'
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prior_audit',ROOT/'analysis/generic_no_rules_v5_latest/analyze.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
def read(p):
 rows=list(csv.DictReader(p.open())); result={r['Sample Row ID']:r for r in rows}
 assert len(rows)==len(result),p
 return result
def count(rs,k='New Status'):return dict(collections.Counter(r[k] for r in rs))
def decode(v):
 try:return json.loads(v)
 except (ValueError,TypeError):return None
rawpath=BASE/'context_v5_01/raw_pipeline.csv';gradepath=BASE/'context_v5_01/graded_pipeline_gpt_5_mini.csv'
raw=read(rawpath);grade=read(gradepath)
assert raw.keys()==grade.keys()
fields=['Question','Ground Truth','New Pipeline Result','Scan Raw Rows','Node Traces','Pipeline Version']
assert all(raw[i][k]==grade[i][k] for i in raw for k in fields)
summary={'rows':len(raw),'raw_grades':count(raw.values()),'grades':count(grade.values()),'paired_payload_fields_verified':fields,
 'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rawpath,gradepath]},
 'settings':{k:count(grade.values(),k) for k in ['Direct LLM Grader Model','Grading Policy','Direct LLM Grading Path','Pipeline Version']},
 'raw_grade_cross':dict(collections.Counter(raw[i]['New Status']+' -> '+grade[i]['New Status'] for i in raw)),
 'failure_stages':count(raw.values(),'Failure Stage')}
diags=[];cases=[];tags=collections.Counter();backends=collections.Counter();nodecounts=collections.Counter();context_rows=0
for i,r in raw.items():
 g=grade[i];traces=decode(r['Node Traces']) or {};errors=list(dict.fromkeys(e for n in traces.values() for e in n.get('contract_errors',[])))
 ts=prior.tags(errors);tags.update(ts);nodecounts[len(traces)]+=1
 bs=sorted({n.get('backend') for n in traces.values() if n.get('backend') in ['SQL','KG']});bk='+'.join(bs) or 'none';backends[bk+' / '+g['New Status']]+=1
 context_rows+=int('domain_context_trace' in r['Node Traces'] or 'domain_context_trace' in r['Query Spec'])
 ref=decode(r['Ground Truth']);ans=decode(r['Scan Raw Rows'])
 d={'id':i,'question':r['Question'],'family':r['Source CSV'],'grade':g['New Status'],'raw_status':r['New Status'],'failure_stage':r['Failure Stage'],'backend':bk,'contract_tags':json.dumps(ts),'contract_errors':json.dumps(errors),'reason':g['Original Grade Reason'],'reference_chars':len(r['Ground Truth']),'answer_chars':len(r['Scan Raw Rows']),'reference_rows':len(ref) if isinstance(ref,list) else '', 'answer_rows':len(ans) if isinstance(ans,list) else ''}
 diags.append(d)
 if g['New Status']!='MATCH':cases.append({**d,'evidence':g['Original Grade Evidence'],'reference':ref,'answer':ans,'traces':traces})
summary.update(contract_tag_incidence=dict(tags),backends=dict(backends),node_counts=dict(nodecounts),context_trace_rows=context_rows)
summary['families']={f:{'grades':count([g for g in grade.values() if g['Source CSV']==f]),'raw_status':count([r for r in raw.values() if r['Source CSV']==f])} for f in sorted({r['Source CSV'] for r in raw.values()})}
summary['long_payload_grades']=count([grade[d['id']] for d in diags if max(d['reference_chars'],d['answer_chars'])>60000])
summary['grader_error_ids']=[d['id'] for d in diags if d['grade'] not in ['MATCH','PARTIAL','MISMATCH']]
oldraw=read(BASE/'generic_no_rules_v5/raw_pipeline.csv');oldgrade=read(BASE/'generic_no_rules_v5/graded_pipeline_tera.csv')
assert raw.keys()==oldraw.keys()==oldgrade.keys()
assert all(raw[i][k]==oldraw[i][k] for i in raw for k in ['Question','Ground Truth'])
unchanged=[i for i in raw if raw[i]['Scan Raw Rows']==oldraw[i]['Scan Raw Rows'] and raw[i]['New Status']=='PIPELINE_SUCCESS']
summary['prior_v5_comparison']={'grades':count(oldgrade.values()),'raw_status':count(oldraw.values()),'models':count(oldgrade.values(),'Direct LLM Grader Model'),'transitions':dict(collections.Counter(oldgrade[i]['New Status']+' -> '+grade[i]['New Status'] for i in raw)), 'unchanged_successful_scan_payloads':len(unchanged),'unchanged_payload_grade_transitions':dict(collections.Counter(oldgrade[i]['New Status']+' -> '+grade[i]['New Status'] for i in unchanged)), 'new_raw_failures':sum(oldraw[i]['New Status']=='PIPELINE_SUCCESS' and raw[i]['New Status']!='PIPELINE_SUCCESS' for i in raw),'recovered_raw_failures':sum(oldraw[i]['New Status']!='PIPELINE_SUCCESS' and raw[i]['New Status']=='PIPELINE_SUCCESS' for i in raw)}
checks={}
for suffix,field in [('ARC125-1T-013','goal_id'),('ARC125-1T-015','goal_id'),('ARC125-1T-016','goal_id'),('WM125-3T-026','investor_id'),('ARC125-4T-002','investor_id'),('ARC125-4T-003','investor_id'),('ARC125-4T-025','investor_id')]:
 r=next(r for r in raw.values() if r['Sample Row ID'].endswith(suffix));a=decode(r['Scan Raw Rows']);b=decode(r['Ground Truth'])
 if not isinstance(a,list) or not isinstance(b,list) or not a or not b or not all(field in x for x in a+b):continue
 sa={str(x[field]) for x in a};sb={str(x[field]) for x in b}
 checks[suffix]={'question':r['Question'],'grade':grade[r['Sample Row ID']]['New Status'],'field':field,'answer_rows':len(a),'reference_rows':len(b),'extra_ids':len(sa-sb),'missing_ids':len(sb-sa),'answer_duplicate_ids':len(a)-len(sa),'exact_entity_set':sa==sb,'reference_chars':len(r['Ground Truth']),'answer_chars':len(r['Scan Raw Rows'])}
(OUT/'entity_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'nonmatches.json').write_text(json.dumps(cases,indent=2)+'\n')
with (OUT/'row_diagnostics.csv').open('w',newline='') as h:
 w=csv.DictWriter(h,fieldnames=list(diags[0]));w.writeheader();w.writerows(diags)
print(json.dumps(summary,indent=2));print(json.dumps(checks,indent=2))
