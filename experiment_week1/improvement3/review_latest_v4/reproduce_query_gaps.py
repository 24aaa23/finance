"""Offline diagnostic examples of currently accepted invalid retrieval semantics."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'run_pipeline_v4/tests'))
from support import load
from rdflib import Graph, Literal, Namespace, RDF

validate = load('llm_operators.pre_scan_validate').semantic_pre_scan_validate
ex = Namespace('urn:example:')
g = Graph()
g.add((ex.a, RDF.type, ex.Fact))
g.add((ex.a, ex.value, Literal(5)))
g.add((ex.b, RDF.type, ex.Fact))
g.add((ex.b, ex.value, Literal(20)))
queries = {
    'correct_outer_filter': 'PREFIX ex:<urn:example:> SELECT ?id ?value WHERE {?id a ex:Fact . OPTIONAL {?id ex:value ?value} FILTER(?value < 10)}',
    'optional_filter_retains_nonqualifying_row': 'PREFIX ex:<urn:example:> SELECT ?id ?value WHERE {?id a ex:Fact . OPTIONAL {?id ex:value ?value FILTER(?value < 10)}}',
    'wrong_expanded_class': 'PREFIX ex:<urn:example:Fact> SELECT ?id ?value WHERE {?id a ex:Fact . OPTIONAL {?id <urn:example:value> ?value} FILTER(?value < 10)}',
    'unbound_selected_field': 'PREFIX ex:<urn:example:> SELECT ?id ?value WHERE {?id a ex:Fact}',
}
results = {}
for name, query in queries.items():
    inputs = {'sparql': query, 'retrieval_spec': {'source_class': 'Fact', 'fields': ['id', 'value'], 'filters': [{'field': 'value', 'operator': '<', 'value': 10}]}}
    result = validate(inputs, None)['pre_scan_validation']
    rows = [{str(k): str(v) for k, v in row.asdict().items()} for row in g.query(query)]
    results[name] = {'accepted_by_current_pre_scan': result['is_valid'], 'actual_rows': rows}
assert all(r['accepted_by_current_pre_scan'] for r in results.values())
assert len(results['correct_outer_filter']['actual_rows']) == 1
assert len(results['optional_filter_retains_nonqualifying_row']['actual_rows']) == 2
assert len(results['wrong_expanded_class']['actual_rows']) == 0
assert all('value' not in r for r in results['unbound_selected_field']['actual_rows'])
(HERE / 'query_gap_reproductions.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
