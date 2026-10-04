"""Full saved-result comparisons and optional read-only RDF diagnostic probes."""
import collections
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

csv.field_size_limit(100_000_000)
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5'
raw={r['Sample Row ID'].split(':')[-1]:r for r in csv.DictReader((BASE/'raw_pipeline.csv').open())}
grade={r['Sample Row ID'].split(':')[-1]:r for r in csv.DictReader((BASE/'graded_pipeline_tera.csv').open())}
result={}
for sample in ('WM125-1T-003','ARC125-1T-004','ARC125-1T-013','SQA125-1T-008','SQA125-3T-002','SQA125-3T-004'):
 r=raw[sample];a=json.loads(r['New Pipeline Result']);g=json.loads(r['Ground Truth'])
 item={'recorded_grade':grade[sample]['New Status'],'answer_rows':len(a),'reference_rows':len(g),
       'answer_chars':len(r['New Pipeline Result']),'reference_chars':len(r['Ground Truth'])}
 if sample=='WM125-1T-003':item['exact_answer_match']=a==g
 else:
  ak=('goalId' if 'goalId' in a[0] else 'goal_id') if sample in ('ARC125-1T-013','SQA125-1T-008') else ('investor_id' if 'investor_id' in a[0] else 'investorId')
  gk='goal_id' if sample in ('ARC125-1T-013','SQA125-1T-008') else 'investor_id'
  aa={r[ak] for r in a};gg={r[gk] for r in g}
  item.update(extra_ids=len(aa-gg),missing_ids=len(gg-aa),exact_id_set_match=aa==gg)
 result[sample]=item

queries={
'SQA125-1T-008': '''PREFIX wm: <https://wealth.example.org/ontology/>
 SELECT ?goalId ?vol WHERE {?g a wm:InvestmentGoal; wm:goalId ?goalId; wm:avgVolatilityPct ?vol. FILTER(?vol>15)}''',
'TT125-020': '''PREFIX wm: <https://wealth.example.org/ontology/>
 PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
 SELECT ?investorId ?date ?amount WHERE {
 ?c a wm:CashFlow; wm:investorId ?investorId; wm:date ?date; wm:amount ?amount; wm:type ?type.
 FILTER(?type="Deposit" && ?amount>3500 && ?date>="2024-01-01"^^xsd:date)}'''
}
for sample,query in queries.items():
 item=result.setdefault(sample,{})
 try:
  req=urllib.request.Request('http://127.0.0.1:3030/wealth/query',data=urllib.parse.urlencode({'query':query}).encode(),headers={'Accept':'application/sparql-results+json'})
  with urllib.request.urlopen(req,timeout=15) as response:bindings=json.load(response)['results']['bindings']
  actual=[{k:v['value'] for k,v in b.items()} for b in bindings]
  gt=json.loads(raw[sample]['Ground Truth'])
  if sample=='SQA125-1T-008':equal={r['goalId'] for r in actual}=={r['goal_id'] for r in gt}
  else:
   def tuples(rows,key):return collections.Counter((r[key],r['date'],float(r['amount'])) for r in rows)
   equal=tuples(actual,'investorId')==tuples(gt,'investor_id')
   saved=json.loads(raw[sample]['New Pipeline Result'])
   item.update(answer_rows=len(saved),reference_rows=len(gt),recorded_grade=grade[sample]['New Status'],
               exact_saved_transaction_multiset_match=tuples(saved,'investorId')==tuples(gt,'investor_id'))
  item['minimal_projection_replay']={'sparql':query,'rows':len(actual),'reference_rows':len(gt),'requested_values_match':equal}
 except Exception as error:item['replay_error']=str(error)
(OUT/'full_result_checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
