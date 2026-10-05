"""Hand-authored read-only SQL probes of semantic failure hypotheses."""
import json,sqlite3,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
csv.field_size_limit(100000000)
rows=list(csv.DictReader((ROOT/'outputs/openai_gpt_oss_120b/all/test1000/context_v5_01/graded_pipeline_gpt_5_mini.csv').open()))
c=sqlite3.connect((ROOT/'historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
queries={
'WM125-2T-026':"WITH per_inv AS (SELECT investor_id, AVG(progress_pct) v FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id) SELECT AVG(v) avg_progress FROM per_inv g JOIN ATOM_ENTITY_INVESTOR_PROFILE_001 p ON g.investor_id=p.investor_id WHERE p.investment_goal='Retirement Planning'",
'WM125-2T-023':"WITH per_inv AS (SELECT investor_id, AVG(progress_pct) v FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id) SELECT AVG(v) avg_progress FROM per_inv g JOIN ATOM_ENTITY_INVESTOR_PROFILE_001 p ON g.investor_id=p.investor_id WHERE p.investment_goal='Emergency Fund'",
'TT125-055':"SELECT SUM(amount) total_amount FROM ATOM_EVENT_CASH_FLOW_001 WHERE source='Bank Transfer'",
'EC125-3T-010':"SELECT p.risk_tolerance,COUNT(DISTINCT p.investor_id) investor_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p WHERE EXISTS(SELECT 1 FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 h WHERE h.investor_id=p.investor_id AND h.investment_type='Mutual Fund') AND EXISTS(SELECT 1 FROM ATOM_ENTITY_INVESTMENT_GOAL_001 g WHERE g.investor_id=p.investor_id AND g.investment_goal='Growth') GROUP BY p.risk_tolerance",
'EC125-2T-029':"SELECT p.segment,h.sector,COUNT(DISTINCT p.investor_id) investor_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h ON p.investor_id=h.investor_id GROUP BY p.segment,h.sector",
'SQA125-3T-009':"SELECT p.investor_id, AVG(g.avg_annual_return_pct) goal_metric FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HEALTH_001 h ON p.investor_id=h.investor_id JOIN ATOM_ENTITY_INVESTMENT_GOAL_001 g ON p.investor_id=g.investor_id WHERE p.risk_tolerance='Aggressive' AND h.risk_score>50 GROUP BY p.investor_id HAVING AVG(g.avg_annual_return_pct)>35",
'TT125-004':"SELECT investor_id,SUM(amount) net_cash_flow FROM ATOM_EVENT_CASH_FLOW_001 WHERE date>='2024-01-01' AND date<'2025-01-01' GROUP BY investor_id HAVING SUM(amount)<0"}
queries.update({
'MC125-007':"WITH g AS(SELECT investor_id,AVG(shortfall) v FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id) SELECT risk_tolerance,AVG(v) avg_goal_shortfall FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p LEFT JOIN g ON p.investor_id=g.investor_id GROUP BY risk_tolerance",
'MC125-003':"WITH r AS(SELECT investor_id,AVG(target_allocation_pct-current_allocation_pct) v FROM ATOM_EVENT_REBALANCING_ACTION_001 GROUP BY investor_id) SELECT risk_tolerance,AVG(v) avg_rebalance_shift FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p LEFT JOIN r ON p.investor_id=r.investor_id GROUP BY risk_tolerance",
'MC125-032':"WITH h AS(SELECT investor_id,AVG(100.0*(current_value-cost)/NULLIF(cost,0)) v FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 WHERE cost IS NOT NULL AND current_value IS NOT NULL GROUP BY investor_id) SELECT risk_tolerance,AVG(v) avg_holding_return FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p LEFT JOIN h ON p.investor_id=h.investor_id GROUP BY risk_tolerance"
})
checks={}
for suffix,sql in queries.items():
 r=next(r for r in rows if r['Sample Row ID'].endswith(suffix));ref=json.loads(r['Ground Truth']);probe=[dict(x) for x in c.execute(sql)]
 if len(probe)==len(ref)==1 and len(probe[0])==len(ref[0])==1:
  x=next(iter(probe[0].values()));y=next(iter(ref[0].values()));comp={'probe_value':x,'reference_value':y,'absolute_difference':abs(x-y)}
 elif suffix.startswith('MC125-'):
  metric=next(k for k in probe[0] if k!='risk_tolerance')
  expected={x['risk_tolerance']:x[metric] for x in ref}
  differences=[abs(x[metric]-expected[x['risk_tolerance']]) for x in probe]
  comp={'metric':metric,'max_absolute_difference':max(differences),'all_groups_match_to_reference_rounding':all(d<0.0051 for d in differences)}
 elif suffix in ['SQA125-3T-009','TT125-004']:
  sa={x['investor_id'] for x in probe};sb={x['investor_id'] for x in ref};comp={'exact_investor_set':sa==sb,'extra_ids':len(sa-sb),'missing_ids':len(sb-sa)}
 else:
  normalize=lambda arr: sorted(json.dumps(x,sort_keys=True) for x in arr)
  comp={'exact_group_records':normalize(probe)==normalize(ref)}
 checks[suffix]={'question':r['Question'],'recorded_grade':r['New Status'],'sql':sql,'probe_rows':len(probe),'reference_rows':len(ref),**comp,'probe_sample':probe[:4]}
c.close()
(Path(__file__).resolve().parent/'sql_checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))
