"""Mechanical execution regressions with synthetic schemas and SQL oracle checks."""
import difflib
import importlib.util
import json
import sys
import unicodedata
import unittest

import duckdb
from support import load, registry, FakeClient, SOURCE, PACKAGE


class MechanicalExecutionTests(unittest.TestCase):
    def test_explicit_logical_spelling_keeps_metadata_and_truth_table(self):
        sql = load('sql_conditions')
        alias = {'id': 'scope', 'source_class': 'items', 'stage': 'scan', 'branch_ids': ['q'],
                 'field': 'flag', 'operator': 'any', 'value': [
                     {'field': 'flag', 'operator': '=', 'value': True},
                     {'field': 'flag', 'operator': 'is_null', 'value': None}]}
        result = sql.normalize_condition(alias)
        self.assertEqual(result['any'], sql.normalize_condition({'any': alias['value']})['any'])
        for key in ('id', 'source_class', 'stage', 'branch_ids'):
            self.assertEqual(result[key], alias[key])
        self.assertEqual(sql.raw_condition_errors(result), [])
        self.assertEqual(alias['operator'], 'any')
        rows = [{'id': 1, 'flag': True}, {'id': 2, 'flag': False}, {'id': 3, 'flag': None}]
        selected = load('llm_operators.filter_aggregate').semantic_filter_aggregate(
            {'data': rows, 'operation': 'filter', 'filters': [result], 'strict_spec': True})
        self.assertEqual([r['id'] for r in selected['data']], [1, 3])
        plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'input': 'raw', 'operation': 'filter',
                'filters': [alias]}], 'projection': ['id']}
        compiled = load('spec_runtime').compile_spec(plan, {'raw': ['id', 'flag']})
        self.assertEqual(compiled['contract_errors'], [])
        data, log = load('execution').execute_spec(compiled, {'raw': rows}, registry())
        self.assertFalse(load('execution').execution_errors(log))
        self.assertEqual(data, [{'id': 1}, {'id': 3}])

    def test_logical_repair_feedback_contains_group_instead_of_none_none(self):
        q = load('llm_operators.query_spec')
        requirement = {'id': 'scope', 'source_class': 'items', 'any': [
            {'field': 'flag', 'operator': '=', 'value': True}, {'field': 'flag', 'operator': 'is_null', 'value': None}]}
        spec = {'id': 'q', 'retrieval_specs': [{'class': 'items', 'fields': ['flag'],
                'filters': [{'field': 'flag', 'operator': 'in', 'value': [True, None]}]}]}
        errors = q._answer_requirement_errors(spec, {'answer_requirements': {'predicates': [requirement]}},
                                              {'items': {'columns': [{'name': 'flag'}]}})
        self.assertTrue(errors)
        self.assertIn('"any"', errors[0])
        self.assertIn('IN containing null', errors[0])
        self.assertNotIn('None None', errors[0])

    def test_queryspec_prompt_teaches_grouped_or_and_keeps_contract(self):
        q = load('llm_operators.query_spec')
        requirement = {'source_class': 'items', 'any': [
            {'field': 'flag', 'operator': '=', 'value': True}, {'field': 'flag', 'operator': 'is_null', 'value': None}]}
        client = FakeClient({'id': 'q', 'retrieval_specs': [{'class': 'items', 'entity_key': ['id'],
            'fields': ['id', 'flag'], 'filters': [requirement]}], 'output_schema': ['id', 'flag']})
        result = q.semantic_build_query_spec({'query': 'Read eligible records', 'subquestion': {'id': 'q', 'source_class': 'items'},
            'global_schema': {'items': {'columns': [{'name': 'id'}, {'name': 'flag'}]}},
            'decomposition': {'answer_requirements': {'predicates': [requirement]}}}, client)
        self.assertEqual(result['query_spec']['contract_errors'], [])
        prompt = client.calls[0]['messages'][-1]['content']
        self.assertIn('Logical filters are supported', prompt)
        self.assertIn('IN [true,null]', prompt)

    def test_date_literals_fail_before_scan_without_changing_boundary(self):
        contracts = load('spec_contracts')
        schema = {'events': {'columns': [{'name': 'id'}, {'name': 'day'}],
            'yaml_metadata': {'attributes': [{'name': 'day', 'type': 'date'}]}}}
        for value in ['CURRENT_DATE', 'latest', '<max_date>', '(SELECT MAX(day) FROM events)', '2026-02-30']:
            spec = {'retrieval_specs': [{'class': 'events', 'entity_key': ['id'], 'fields': ['id', 'day'],
                    'filters': [{'field': 'day', 'operator': '>=', 'value': value, 'value_type': 'string'}]}]}
            errors = contracts.validate_query_spec_contract(spec, schema)
            self.assertTrue(any('date literal' in e or 'subqueries' in e for e in errors), (value, errors))
            self.assertEqual(spec['retrieval_specs'][0]['filters'][0]['value'], value)
        condition = load('sql_conditions')
        self.assertEqual(condition.date_literal_errors({'field': 'day', 'value': ['2024-02-29', '2024-03-31'], 'operator': 'between', 'value_type': 'date'}), [])
        self.assertEqual(condition.date_literal_errors({'field': 'label', 'value': 'latest', 'value_type': 'string'}), [])

    def test_null_comparisons_get_repair_feedback_presence_is_valid(self):
        compiler = load('spec_runtime').compile_spec
        for op in ('=', '!='):
            plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'input': 'raw', 'operation': 'filter',
                    'filters': [{'field': 'label', 'operator': op, 'value': None}]}], 'projection': ['label']}
            self.assertTrue(any('NULL comparisons' in e for e in compiler(plan, {'raw': ['label']})['contract_errors']))
        plan['final_steps'][0]['filters'][0]['operator'] = 'is_not_null'
        self.assertEqual(compiler(plan, {'raw': ['label']})['contract_errors'], [])

    def test_left_right_input_aliases_execute_set_difference(self):
        plan = {'final_steps': [{'operator': 'Set_Difference', 'left_input': 'clients', 'right_input': 'mapped',
                'left_on': ['id'], 'right_on': ['client_id']}], 'projection': ['id']}
        spec = load('spec_runtime').compile_spec(plan, {'clients': ['id'], 'mapped': ['client_id']})
        self.assertEqual(spec['contract_errors'], [])
        result, log = load('execution').execute_spec(spec, {'clients': [{'id': 1}, {'id': 2}, {'id': 3}],
                                                   'mapped': [{'client_id': 2}]}, registry())
        self.assertFalse(load('execution').execution_errors(log))
        self.assertEqual(result, [{'id': 1}, {'id': 3}])
        plan['final_steps'][0]['inputs'] = ['mapped', 'clients']
        self.assertTrue(load('spec_runtime').compile_spec(plan, {'clients': ['id'], 'mapped': ['client_id']})['contract_errors'])

    def test_ilike_and_not_ilike_match_duckdb_with_nulls(self):
        labels = ['Nifty 50 TRI', 'nIfTy 50', 'Nifty 500', 'Other', None]
        op = load('llm_operators.filter_aggregate').semantic_filter_aggregate
        with duckdb.connect() as db:
            db.execute('CREATE TABLE labels(id INTEGER,label VARCHAR)')
            db.executemany('INSERT INTO labels VALUES (?,?)', list(enumerate(labels)))
            for condition, sql in [('ilike', 'ILIKE'), ('not_ilike', 'NOT ILIKE')]:
                expected = [r[0] for r in db.execute(f"SELECT id FROM labels WHERE label {sql} 'nifty 50%' ORDER BY id").fetchall()]
                result = op({'data': [{'id': i, 'label': value} for i, value in enumerate(labels)],
                             'operation': 'filter', 'filters': [{'field': 'label', 'operator': condition, 'value': 'nifty 50%'}]})
                self.assertNotIn('error', result)
                self.assertEqual([r['id'] for r in result['data']], expected)

    def test_throttling_is_transient_but_quota_is_not(self):
        common = sys.modules[PACKAGE + '.common']
        common.difflib, common.unicodedata = difflib, unicodedata
        spec = importlib.util.spec_from_file_location(PACKAGE + '._mechanical_utils', SOURCE / 'utils.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        error = RuntimeError('rate_limit_exceeded: Too many requests'); error.status_code = 429
        self.assertTrue(module.is_transient_connection_error(error))
        service = RuntimeError('Server error'); service.status_code = 503
        self.assertTrue(module.is_transient_connection_error(service))
        quota = RuntimeError('Error code: 429 insufficient_quota'); quota.status_code = 429
        self.assertTrue(module.is_quota_exhaustion_error(quota))
        self.assertFalse(module.is_transient_connection_error(quota))


if __name__ == '__main__':
    unittest.main()
