"""Read-only replay of the new projection compiler on saved QuerySpecs.

Compare against saved scan rows, never use reference answers to build SQL.
"""
import csv,json,sqlite3,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from script_diff_llm.backends.sql import _deterministic_projection_sql, _deterministic_single_source_aggregate_sql
csv.field_size_limit(100_000_000)
c=sqlite3.connect((ROOT/'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db').as_uri()+'?mode=ro',uri=True)
c.row_factory=sqlite3.Row
schema={r[0]:{'column_names':[x[1] for x in c.execute('PRAGMA table_info("'+r[0]+'")')]} for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
paths=list((ROOT/'ablations/v5_test1000/runs').rglob('raw_pipeline.csv'))
paths += [ROOT/'outputs/openai_gpt_oss_120b/all/test1000'/folder/'raw_pipeline.csv' for folder in ['generic_no_rules_v5','context_v5_01']]
summary={};cases=[]
for p in sorted(paths):
 if not p.exists():continue
 rows=list(csv.DictReader(p.open()));counts=collections.Counter()
 for r in rows:
  for nid,node in json.loads(r['Node Traces'] or '{}').items():
   if node.get('backend')!='SQL':continue
   qs=node.get('query_spec',{})
   if not isinstance(qs,dict):continue
   inputs={'query_spec':qs,'sql_schema':schema,'bound_inputs':node.get('bound_inputs',{})}
   sql=_deterministic_projection_sql(inputs) or _deterministic_single_source_aggregate_sql(inputs)
   if not sql:continue
   counts['eligible_nodes']+=1
   try:replay=[dict(x) for x in c.execute(sql)]
   except sqlite3.Error as e:
    counts['preparation_errors']+=1;cases.append({'run':str(p.parent.relative_to(ROOT)),'id':r['Sample Row ID'],'node':nid,'compiler':qs.get('query_type'),'error':str(e)});continue
   counts['executable_nodes']+=1
   saved=json.loads(node.get('scan_raw_rows') or 'null')
   if node.get('scan_status')!='success' or not isinstance(saved,list):continue
   outputs=qs['output_schema']
   if not all(set(outputs)<=x.keys() for x in saved):
    counts['saved_aliases_differ']+=1;continue
   normalize=lambda arr:collections.Counter(json.dumps({k:x[k] for k in outputs},sort_keys=True,ensure_ascii=False) for x in arr)
   exact=normalize(replay)==normalize(saved)
   counts['same_saved_requested_values' if exact else 'different_saved_requested_values']+=1
   if not exact:cases.append({'run':str(p.parent.relative_to(ROOT)),'id':r['Sample Row ID'],'node':nid,'replay_rows':len(replay),'saved_rows':len(saved),'compiler':qs.get('query_type'),'sql':sql})
 summary[str(p.parent.relative_to(ROOT))]=dict(counts)
c.close()
out=Path(__file__).resolve().parent/'compiler_replay.json';out.write_text(json.dumps({'summary':summary,'differences':cases},indent=2)+'\n');print(json.dumps(summary,indent=2))
