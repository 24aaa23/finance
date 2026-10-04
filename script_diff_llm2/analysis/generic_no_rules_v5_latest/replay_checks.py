"""Read-only diagnostic counterfactuals. Never imported by the pipeline.

These probes investigate saved errors against evaluation references; their
expressions are not exported as runtime rules or semantic catalog entries.
"""
import collections
import csv
import json
import sqlite3
from pathlib import Path

csv.field_size_limit(100_000_000)
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5'
rows={r['Sample Row ID'].split(':')[-1]:r for r in csv.DictReader((BASE/'raw_pipeline.csv').open())}
path=ROOT/'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db'
conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
probes={
'WM125-2T-027': '''SELECT AVG(entity_progress) AS avg_progress FROM (
 SELECT g.investor_id, AVG(g.progress_pct) entity_progress
 FROM ATOM_ENTITY_INVESTMENT_GOAL_001 g
 JOIN ATOM_ENTITY_INVESTOR_PROFILE_001 p ON p.investor_id=g.investor_id
 WHERE p.investment_goal='Wealth Preservation' GROUP BY g.investor_id)''',
'EC125-2T-029': '''SELECT p.segment,h.sector,COUNT(DISTINCT p.investor_id) investor_count
 FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h ON h.investor_id=p.investor_id
 GROUP BY p.segment,h.sector''',
'EC125-3T-010': '''SELECT p.risk_tolerance,COUNT(DISTINCT p.investor_id) investor_count
 FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p
 WHERE EXISTS(SELECT 1 FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 h WHERE h.investor_id=p.investor_id AND h.investment_type='Mutual Fund')
 AND EXISTS(SELECT 1 FROM ATOM_ENTITY_INVESTMENT_GOAL_001 g WHERE g.investor_id=p.investor_id AND g.investment_goal='Growth')
 GROUP BY p.risk_tolerance''',
'EC125-2T-018': '''SELECT p.category,AVG(100.0*(h.current_value-h.cost)/NULLIF(h.cost,0)) avg_return_pct
 FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h ON h.investor_id=p.investor_id
 WHERE p.investor_id='INV-009' AND h.cost IS NOT NULL AND h.current_value IS NOT NULL GROUP BY p.category''',
'TT125-053': '''SELECT SUM(amount) total_amount FROM ATOM_EVENT_CASH_FLOW_001 WHERE source='Auto-debit' ''',
'BSQ125-1T-011': '''SELECT goal_id,shortfall FROM ATOM_ENTITY_INVESTMENT_GOAL_001 WHERE progress_pct<30 AND shortfall>0''',
'SQA125-1T-015': '''SELECT goal_id,investor_id,avg_volatility_pct FROM ATOM_ENTITY_INVESTMENT_GOAL_001
 ORDER BY avg_volatility_pct DESC,goal_id ASC LIMIT 10''',
'RC125-002': '''SELECT investor_id,time_horizon FROM ATOM_ENTITY_INVESTOR_PROFILE_001
 WHERE time_horizon NOT IN ('Long-term','Medium-term','Short-term')'''
}
def values(data,keys):return collections.Counter(tuple(row.get(k) for k in keys) for row in data)
result={}
for sample,query in probes.items():
 actual=[dict(r) for r in conn.execute(query)]
 reference=json.loads(rows[sample]['Ground Truth'])
 common=sorted(set(actual[0]) & set(reference[0])) if actual and reference else []
 item={'diagnostic_sql':query,'rows':len(actual),'reference_rows':len(reference),'common_columns':common,
       'exact_common_column_multiset_match':values(actual,common)==values(reference,common) if common else actual==reference,
       'preview':actual[:4],'reference_preview':reference[:4]}
 if sample=='WM125-2T-027':item['absolute_difference']=abs(actual[0]['avg_progress']-reference[0]['avg_progress'])
 result[sample]=item
conn.close()
(OUT/'read_only_replays.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{f:v for f,v in x.items() if f not in ('diagnostic_sql','preview','reference_preview')} for k,x in result.items()},indent=2))
