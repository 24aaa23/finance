"""Offline analysis of completed v5 reports. No runtime imports or model calls."""
import collections
import csv
import hashlib
import json
import statistics
from pathlib import Path

csv.field_size_limit(100_000_000)
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/openai_gpt_oss_120b/all/test1000'
OUT = Path(__file__).resolve().parent
FOLDERS = {'v2': 'generic_no_rules_v2_20261003', 'v4': 'generic_no_rules_v4', 'v5': 'generic_no_rules_v5'}

def read(path):
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    result = {r['Sample Row ID']: r for r in rows}
    assert len(result) == len(rows), f'Duplicate IDs: {path}'
    return result

def counts(rows, key='New Status'):
    return dict(collections.Counter(r[key] for r in rows))

def tags(errors):
    needles = {'unresolved': 'Unresolved requirements', 'unknown_source': 'unknown source',
               'unknown_base': 'Unknown base_entity', 'missing_expression': 'derived measure needs an expression',
               'alias_operand': 'unknown or self-referencing formula operand',
               'physical_operand': 'unknown formula operand', 'missing_output': 'output_schema must contain',
               'unparsed_spec': 'could not be parsed', 'missing_measures': 'no measures after recovery',
               'invalid_operand_kind': 'operand_kind must be', 'missing_binding_output': 'Missing downstream binding output',
               'aggregate_alias': 'predicate must reference the owning', 'aggregate_stage': 'explicit entity or final_group'}
    return [tag for tag, needle in needles.items() if any(needle.casefold() in e.casefold() for e in errors)]

def main():
    runs, hashes = {}, {}
    for v, folder in FOLDERS.items():
        rawpath, gradepath = BASE/folder/'raw_pipeline.csv', BASE/folder/'graded_pipeline_tera.csv'
        raw, grade = read(rawpath), read(gradepath)
        assert set(raw) == set(grade), f'Coverage differs: {v}'
        for i, r in raw.items():
            for field in ('Question', 'Ground Truth', 'New Pipeline Result', 'Node Traces', 'Pipeline Version'):
                assert r[field] == grade[i][field], (v,i,field)
        runs[v] = {'raw':raw, 'grade':grade}
        for p in (rawpath,gradepath):
            hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    raw, grade = runs['v5']['raw'], runs['v5']['grade']
    summary = {'rows': len(raw), 'run_comparisons': {}, 'pairs': {}, 'families': {}, 'output_sha256': hashes}
    for v, run in runs.items():
        assert set(run['raw']) == set(raw)
        assert all(run['raw'][i][c] == raw[i][c] for i in raw for c in ('Question','Ground Truth'))
        summary['run_comparisons'][v] = {'raw_status':counts(run['raw'].values()), 'grades':counts(run['grade'].values()),
                                        'versions':counts(run['raw'].values(),'Pipeline Version')}
    for v in ('v2','v4'):
        old, oldraw = runs[v]['grade'], runs[v]['raw']
        gained=[i for i in raw if old[i]['New Status']!='MATCH' and grade[i]['New Status']=='MATCH']
        lost=[i for i in raw if old[i]['New Status']=='MATCH' and grade[i]['New Status']!='MATCH']
        shared=[i for i in raw if oldraw[i]['New Status']==raw[i]['New Status']=='PIPELINE_SUCCESS']
        recovered=[i for i in raw if oldraw[i]['New Status']!='PIPELINE_SUCCESS' and raw[i]['New Status']=='PIPELINE_SUCCESS']
        summary['pairs'][v]={'transitions':dict(collections.Counter(old[i]['New Status']+' -> '+grade[i]['New Status'] for i in raw)),
                            'gains':len(gained),'losses':len(lost),'net_match_gain':len(gained)-len(lost),
                            'lost_match_stages':dict(collections.Counter(raw[i]['Failure Stage'] or 'executed' for i in lost)),
                            'gained_ids':gained,'lost_ids':lost,
                            'recovered_raw_grades':counts([grade[i] for i in recovered]),
                            'shared_success':{'rows':len(shared),'old_matches':sum(old[i]['New Status']=='MATCH' for i in shared),
                                              'v5_matches':sum(grade[i]['New Status']=='MATCH' for i in shared)}}
    families = sorted({r['Source CSV'] for r in raw.values()})
    for family in families:
        summary['families'][family] = {v: counts([g for g in run['grade'].values() if g['Source CSV']==family]) for v,run in runs.items()}
    diagnostics, cases = [], []
    backend, incidence, rawgrade, repairs = collections.Counter(),collections.Counter(),collections.Counter(),collections.Counter()
    multi = collections.Counter()
    for i,r in raw.items():
        g=grade[i]; traces=json.loads(r['Node Traces'] or '{}')
        errors=list(dict.fromkeys(e for n in traces.values() for e in n.get('contract_errors',[])))
        ts=tags(errors);incidence.update(ts)
        backends={n.get('backend','') for n in traces.values() if n.get('operator')=='Subquery' or n.get('backend') in ('SQL','KG')}
        bk=next(iter(backends)) if len(backends)==1 else 'mixed'
        backend[bk+' / '+g['New Status']]+=1
        rawgrade[r['New Status']+' -> '+g['New Status']]+=1
        if len(traces)>1:multi[g['New Status']]+=1
        repair_count=sum(len(n.get('query_spec',{}).get('structural_repairs',[])) for n in traces.values() if isinstance(n.get('query_spec'),dict))
        repairs['rows_with_repairs']+=int(repair_count>0);repairs['repair_records']+=repair_count
        diagnostic={'id':i,'question':r['Question'],'family':r['Source CSV'],'raw_status':r['New Status'],
                    'grade':g['New Status'],'v2_grade':runs['v2']['grade'][i]['New Status'],'v4_grade':runs['v4']['grade'][i]['New Status'],
                    'failure_stage':r['Failure Stage'],'backend':bk,'error_tags':json.dumps(ts),'contract_errors':json.dumps(errors),
                    'grader_reason':g['Original Grade Reason'],'grader_evidence':g['Original Grade Evidence'],
                    'elapsed_seconds':r['Elapsed Seconds'],'repair_count':repair_count}
        diagnostics.append(diagnostic)
        if g['New Status']!='MATCH':
            cases.append({**diagnostic,'reference':r['Ground Truth'],'answer':r['New Pipeline Result'],'scan_rows':r['Scan Raw Rows'],
                          'comments':g['Comparison / Comments'],'traces':traces})
    times=sorted(float(r['Elapsed Seconds']) for r in raw.values())
    slow=[r for r in raw.values() if float(r['Elapsed Seconds'])>300]
    summary.update({'failure_stages':counts(raw.values(),'Failure Stage'),'grader_settings':{c:counts(grade.values(),c) for c in ('Grading Policy','Grader Label','Direct LLM Grader Model')},
                    'raw_grade_transitions':dict(rawgrade),'backends':dict(backend),'overlapping_contract_tags':dict(incidence),
                    'repair_activity':dict(repairs),'node_counts':dict(collections.Counter(len(json.loads(r['Node Traces'] or '{}')) for r in raw.values())),
                    'multi_node_grades':dict(multi),'latency':{'mean':statistics.mean(times),'median':statistics.median(times),
                        'p95':times[int(.95*(len(times)-1))],'p99':times[int(.99*(len(times)-1))], 'cumulative_seconds':sum(times),
                        'over300_rows':len(slow),'over300_seconds':sum(float(r['Elapsed Seconds']) for r in slow)}})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (OUT/'nonmatches.json').write_text(json.dumps(cases,indent=2)+'\n')
    with (OUT/'row_diagnostics.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(diagnostics[0]));writer.writeheader();writer.writerows(diagnostics)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('output_sha256','families','pairs')},indent=2))
    print(json.dumps({v:{k:d for k,d in pair.items() if k not in ('gained_ids','lost_ids','transitions')} for v,pair in summary['pairs'].items()},indent=2))

if __name__=='__main__':main()
