"""Generic execution regressions using only synthetic source data."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from script_diff_llm.backends.sql import _deterministic_entity_group_sql
from script_diff_llm.backends.sql_schema import load_source_schema
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.specification import cleanup_query_spec, semantic_build_query_spec
from tests.unit.test_portable_contracts import SCHEMA, QUESTION, spec


class ContractCompatibilityV2(unittest.TestCase):
    def test_cyclic_intermediates_and_invented_final_columns_still_block(self):
        plan = spec()
        plan['measures'] += [
            {'source_class': 'derived', 'output_name': 'a', 'formula': 'b + 1', 'formula_fields': ['b']},
            {'source_class': 'derived', 'output_name': 'b', 'formula': 'a + 1', 'formula_fields': ['a']}]
        errors, _ = split_contract_errors(validate_query_spec(plan, SCHEMA))
        self.assertIn('Derived measure dependencies contain a cycle.', errors)
        plan = spec()
        plan['output_schema'].append('invented_result')
        self.assertIn('Unknown output column: invented_result', validate_query_spec(plan, SCHEMA))

    def test_typed_date_string_comparison_is_rejected_before_model_validation(self):
        from script_diff_llm.backends.sparql_contract import date_comparison_errors
        from script_diff_llm.pipeline.kg_pipeline import semantic_pre_scan_validate
        schema = {'Event': {'columns': [{'name': 'day', 'uri': 'https://example/day'}],
                             'literal_datatypes': {'day': ['http://www.w3.org/2001/XMLSchema#date']}}}
        query = 'SELECT ?day WHERE { ?s <https://example/day> ?day . FILTER(?day > "2025-01-01") }'
        self.assertTrue(date_comparison_errors(query, schema))
        typed = query.replace('"2025-01-01"', '"2025-01-01"^^<http://www.w3.org/2001/XMLSchema#date>')
        self.assertEqual(date_comparison_errors(typed, schema), [])
        cast = query.replace('?day >', 'STR(?day) >')
        self.assertEqual(date_comparison_errors(cast, schema), [])
        self.assertEqual(date_comparison_errors(query, {}), [])
        result = semantic_pre_scan_validate({'sparql': query, 'global_schema': schema}, None, 'fake',
            parse_json_fn=lambda *_: None, log_call_fn=lambda *_: None)
        self.assertFalse(result['pre_scan_validation']['is_valid'])

    def test_independent_metric_filters_hidden_operands_and_fractional_ratio(self):
        schema = copy.deepcopy(SCHEMA)
        schema['charges']['column_names'].append('kind')
        plan = spec()
        plan['filters'] = []
        plan['measures'] = [
            {'source_class': 'charges', 'field': 'amount', 'output_name': 'eligible',
             'per_entity_operation': 'SUM', 'final_operation': 'SUM',
             'population_filters': [{'field': 'kind', 'operator': '=', 'value': 'Service'}]},
            {'source_class': 'charges', 'field': 'amount', 'output_name': 'total',
             'per_entity_operation': 'SUM', 'final_operation': 'SUM'},
            # Intentionally before its dependency to test topological evaluation.
            {'source_class': 'derived', 'output_name': 'percent', 'formula': 'ratio * 100',
             'formula_stage': 'final_group', 'formula_fields': ['ratio']},
            {'source_class': 'derived', 'output_name': 'ratio', 'formula': 'eligible / total',
             'formula_stage': 'final_group', 'formula_fields': ['eligible', 'total']},
        ]
        plan['output_schema'] = ['region', 'percent']
        plan.pop('requirements')
        self.assertEqual(split_contract_errors(validate_query_spec(plan, schema, QUESTION))[0], [])
        sql = _deterministic_entity_group_sql({'query_spec': plan, 'sql_schema': schema})
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE customers(customer_id INTEGER, region TEXT, active INTEGER);'
                               'CREATE TABLE charges(customer_id INTEGER, amount INTEGER, charge_id INTEGER, kind TEXT);'
                               "INSERT INTO customers VALUES(1, 'east', 1), (2, 'zero', 1);"
                               "INSERT INTO charges VALUES(1, 2, 1, 'Service'), (1, 3, 2, 'Other'), (2, 0, 3, 'Service');")
            cursor = conn.execute(sql)
            self.assertEqual([c[0] for c in cursor.description], ['region', 'percent'])
            self.assertEqual(dict(cursor.fetchall()), {'east': 40.0, 'zero': None})

    def test_compiler_does_not_ignore_upstream_or_boolean_scope(self):
        self.assertIsNone(_deterministic_entity_group_sql({'query_spec': spec(), 'sql_schema': SCHEMA,
                                                          'bound_inputs': {'customer_id': [1]}}))
        plan = spec()
        plan['predicate_tree'] = {'operator': 'OR', 'children': [0, 1]}
        self.assertIsNone(_deterministic_entity_group_sql({'query_spec': plan, 'sql_schema': SCHEMA}))

    def test_alias_ledger_and_operator_spelling_normalize_without_new_predicates(self):
        plan = spec()
        plan['filters'][0].update(operator='not_null')
        plan['requirements'][-1]['implemented_by'] = ['measures.average_total']
        result = cleanup_query_spec(plan, QUESTION, list(SCHEMA), str.lower, schema_kind='sql', schema=SCHEMA)
        self.assertEqual(result['requirements'][-1]['implemented_by'], ['measures.0'])
        self.assertEqual(result['filters'][0]['operator'], 'is_not_null')
        self.assertEqual(len(result['filters']), 1)

    def test_derived_filter_checks_alias_instead_of_demanding_another_formula(self):
        plan = spec()
        plan.pop('requirements')
        plan['filters'] = [{'source_class': 'derived', 'field': 'average_total', 'operator': '>', 'value': 5}]
        self.assertEqual(split_contract_errors(validate_query_spec(plan, SCHEMA))[0], [])
        plan['filters'][0]['field'] = 'unknown_total'
        self.assertTrue(any('unknown derived alias' in e for e in validate_query_spec(plan, SCHEMA)))

    def test_unknown_population_fields_still_block(self):
        plan = spec()
        plan['measures'][0]['population_filters'] = [{'field': 'imaginary', 'operator': '=', 'value': 1}]
        self.assertTrue(any('imaginary' in e for e in split_contract_errors(validate_query_spec(plan, SCHEMA))[0]))

    def test_provenance_wording_is_warning_and_does_not_trigger_paid_repair(self):
        plan = spec()
        plan['requirements'][2]['text'] = 'distinct normalized calculation identifier'
        calls = []
        def create(**request):
            calls.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(plan)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec({'query': QUESTION, 'schema_kind': 'sql', 'global_schema': SCHEMA},
            client, 'fake', parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)['query_spec']
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['contract_errors'], [])
        self.assertTrue(result['contract_warnings'])

    def test_declared_primary_key_resolves_logical_base_among_multiple_sources(self):
        schema = copy.deepcopy(SCHEMA)
        schema['customers']['primary_keys'] = ['customer_id']
        plan = spec()
        plan['base_entity'] = 'customer'
        plan['required_classes'] = ['customer', 'customers', 'charges']
        result = cleanup_query_spec(plan, QUESTION, list(schema), str.lower, schema_kind='sql', schema=schema)
        self.assertEqual(result['base_entity'], 'customers')

    def test_source_profile_is_bounded_complete_and_preserves_exact_case(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.db'
            with sqlite3.connect(path) as conn:
                conn.executescript('CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, region TEXT, active INTEGER);'
                                   'CREATE TABLE charges(charge_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(customer_id), amount INTEGER, kind TEXT);')
                conn.executemany('INSERT INTO customers VALUES (?, ?, 1)', [(i, f'region-{i}') for i in range(40)])
                conn.execute("INSERT INTO charges VALUES (1, 1, 5, 'Service')")
            schema = load_source_schema(str(path))
            self.assertEqual(schema['customers']['primary_keys'], ['customer_id'])
            self.assertEqual(schema['charges']['foreign_keys'][0]['table'], 'customers')
            region = next(c for c in schema['customers']['columns'] if c['name'] == 'region')
            self.assertNotIn('allowed_values', region)
            plan = spec()
            plan['filters'] = [{'source_class': 'charges', 'field': 'kind', 'operator': '=', 'value': 'service'}]
            result = cleanup_query_spec(plan, QUESTION, list(schema), str.lower, schema_kind='sql', schema=schema)
            self.assertEqual(result['filters'][0]['value'], 'Service')
            # Unseen values are not relocated or replaced by a guess.
            plan['filters'][0]['value'] = 'Unknown'
            result = cleanup_query_spec(plan, QUESTION, list(schema), str.lower, schema_kind='sql', schema=schema)
            self.assertEqual(result['filters'][0]['value'], 'Unknown')
            bounded = load_source_schema(str(path), profile_steps=0)
            self.assertTrue(all('allowed_values' not in c for table in bounded.values() for c in table['columns']))


if __name__ == '__main__':
    unittest.main()
