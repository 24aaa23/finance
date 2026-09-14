import json
import sys
from pathlib import Path

data = json.loads(Path(__file__).with_name('evidence.json').read_text())
kind, start, stop = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
cases = sorted([c for c in data['cases'] if c['short_id'].startswith('MC-') == (kind == 'mc')], key=lambda c: c['id'])
for c in cases[start:stop]:
    print('\n' + c['short_id'], c['grade'], 'rows', c['expected_rows'], '->', c['result_rows'])
    print(c['question'])
    print('GRADE', c['reason'])
    print('SOURCES', [(b.get('id'), b.get('source_class')) for b in c['branches']])
    for k, v in c['retrievals'].items():
        if v.get('filters'):
            print('FILTER', k, v['filters'])
    for s in c['steps']:
        op = s.get('operator')
        body = dict(s)
        for key in ['operator', 'id', 'input', 'inputs']:
            body.pop(key, None)
        if body.get('aggregations'):
            body['aggregations'] = [f"{a.get('operation')}({a.get('input_column') or a.get('target_column')})=>{a.get('output_column')}" for a in body['aggregations']]
        print(s.get('id', '?'), op, s.get('inputs', s.get('input', 'previous')), json.dumps(body, separators=(',', ':')))
    print('SQL', ' '.join(c['sql'].split()))
