"""Portable recovery tests: synthetic plans and source data only."""
import copy
import sqlite3
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from script_diff_llm.backends.sparql_contract import typed_projection_evidence
from script_diff_llm.backends.sql import _deterministic_entity_group_sql
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.specification import cleanup_query_spec
from script_diff_llm.pipeline.specification import semantic_build_query_spec
from tests.unit.test_portable_contracts import SCHEMA, QUESTION, spec


class ContractRecoveryV5(unittest.TestCase):
    def clean(self, plan, schema=SCHEMA):
        return cleanup_query_spec(plan, QUESTION, list(schema), str.lower, schema_kind='sql', schema=schema)

    def test_physical_placeholder_resolves_unique_owner_without_changing_predicate(self):
        plan = spec()
        plan['required_classes'] = ['customers', 'charges', 'physical']
        plan['measures'][0]['source_class'] = 'physical'
        original = copy.deepcopy(plan)
        clean = self.clean(plan)
        self.assertEqual(plan, original)
        self.assertEqual(clean['measures'][0]['source_class'], 'charges')
        self.assertNotIn('physical', clean['required_classes'])
        self.assertEqual(clean['filters'], plan['filters'])
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])
        self.assertEqual(self.clean(clean), clean)

    def test_ambiguous_field_ownership_stays_blocked(self):
        plan = spec()
        plan['required_classes'] = ['customers', 'charges']
        plan['measures'][0].update(source_class='physical', field='customer_id')
        clean = self.clean(plan)
        self.assertEqual(clean['measures'][0]['source_class'], 'physical')
        self.assertTrue(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0])

    def test_derived_row_expression_is_repaired_and_executes_at_row_grain(self):
        plan = spec()
        plan['measures'][0].update(source_class='derived', field=None, formula='amount / 2',
                                   formula_fields=['amount'], operand_kind='derived', formula_stage='final_group')
        clean = self.clean(plan)
        measure = clean['measures'][0]
        self.assertEqual((measure['source_class'], measure['operand_kind'], measure['formula_stage']),
                         ('charges', 'physical', 'row'))
        sql = _deterministic_entity_group_sql({'query_spec': clean, 'sql_schema': SCHEMA})
        self.assertIsNotNone(sql)
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE customers(customer_id INTEGER, region TEXT, active INTEGER);'
                               'CREATE TABLE charges(customer_id INTEGER, amount INTEGER, charge_id INTEGER);'
                               "INSERT INTO customers VALUES(1,'west',1),(2,'west',1);"
                               'INSERT INTO charges VALUES(1,3,1),(1,5,2),(2,7,3);')
            self.assertEqual(conn.execute(sql).fetchall(), [('west', 3.75)])

    def test_nested_alias_shorthand_and_single_stage(self):
        for predicate in ({'output_name': 'average_total', 'operator': '>', 'value': 2},
                          {'operator': '>', 'value': 2}):
            plan = spec()
            plan['measures'][0]['final_operation'] = None
            plan['measures'][0]['aggregate_filters'] = [predicate]
            clean = self.clean(plan)
            self.assertEqual(clean['measures'][0]['aggregate_filters'][0]['field'], 'average_total')
            self.assertEqual(clean['measures'][0]['aggregate_filters'][0]['stage'], 'entity')
            self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])

    def test_two_stage_threshold_remains_ambiguous_and_explicit_conflicts_block(self):
        for predicate in ({'operator': '>', 'value': 2},
                          {'output_name': 'another_metric', 'operator': '>', 'value': 2, 'stage': 'entity'},
                          {'field': 'another_metric', 'operator': '>', 'value': 2, 'stage': 'entity'}):
            plan = spec()
            plan['measures'][0]['aggregate_filters'] = [predicate]
            clean = self.clean(plan)
            self.assertTrue(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0])

    def test_unknown_operand_is_not_repaired(self):
        plan = spec()
        plan['measures'][0].update(source_class='derived', field=None, formula='invented * 2',
                                  formula_fields=['invented'])
        self.assertTrue(split_contract_errors(validate_query_spec(self.clean(plan), SCHEMA, QUESTION))[0])

    def test_distinct_entity_count_binds_declared_identity_but_row_count_does_not(self):
        plan = spec()
        plan['required_classes'] = ['customers', 'charges']
        plan['measures'] = [{'source_class': 'derived', 'field': None, 'output_name': 'customer_count',
                             'final_operation': 'COUNT', 'requires_distinct': True}]
        plan['output_schema'] = ['region', 'customer_count']
        clean = self.clean(plan)
        self.assertEqual(clean['measures'][0]['source_class'], 'customers')
        self.assertEqual(clean['measures'][0]['field'], 'customer_id')
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])
        plan['measures'][0]['requires_distinct'] = False
        self.assertEqual(self.clean(plan)['measures'][0]['source_class'], 'derived')

    def test_logical_base_requires_explicit_key_ownership(self):
        plan = spec()
        plan['base_entity'] = 'logical_customer'
        plan['required_classes'] = ['logical_customer', 'customers', 'charges']
        # Two real sources carry the same key: this alone must stay ambiguous.
        self.assertEqual(self.clean(plan)['base_entity'], 'logical_customer')
        plan['group_by'].append({'source_class': 'customers', 'field': 'customer_id', 'output_name': 'customer_id'})
        clean = self.clean(plan)
        self.assertEqual(clean['base_entity'], 'customers')
        self.assertNotIn('logical_customer', clean['required_classes'])
        self.assertEqual(clean['join_policy'], plan['join_policy'])

    def test_logical_source_requires_all_fields_to_have_one_owner(self):
        plan = spec()
        plan['filters'][0]['source_class'] = 'logical_source'
        plan['required_classes'] = ['logical_source', 'customers', 'charges']
        clean = self.clean(plan)
        self.assertEqual(clean['filters'][0]['source_class'], 'customers')
        plan['filters'].append({'source_class': 'logical_source', 'field': 'amount', 'operator': '>', 'value': 3})
        clean = self.clean(plan)
        self.assertEqual(clean['filters'][0]['source_class'], 'logical_source')

    def test_legacy_final_expression_with_physical_source_keeps_alias_operands(self):
        plan = spec()
        plan['measures'].append({'source_class': 'charges', 'field': 'amount', 'output_name': 'positive_average',
                                 'formula': 'ABS(average_total)', 'formula_fields': ['average_total'],
                                 'formula_stage': 'final_group'})
        plan['output_schema'] = ['region', 'positive_average']
        clean = self.clean(plan)
        self.assertEqual(clean['measures'][1]['source_class'], 'derived')
        self.assertEqual(clean['measures'][1]['operand_kind'], 'aliases')
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])

    def test_redundant_projection_collapses_without_losing_requirement_references(self):
        plan = spec()
        plan['measures'].insert(0, {'source_class': 'customers', 'field': 'region', 'output_name': 'region'})
        plan['requirements'][1]['implemented_by'] = ['measures.0']
        plan['requirements'][2]['implemented_by'] = ['measures.1']
        clean = self.clean(plan)
        self.assertEqual(len(clean['measures']), 1)
        self.assertEqual(clean['requirements'][1]['implemented_by'], ['group_by.0'])
        self.assertEqual(clean['requirements'][2]['implemented_by'], ['measures.0'])
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])
        # Same alias with a different computation is a real conflict.
        plan['measures'][0]['final_operation'] = 'COUNT'
        self.assertTrue(any('Duplicate output alias' in e for e in validate_query_spec(self.clean(plan), SCHEMA, QUESTION)))

    def test_typed_literal_carrier_evidence_keeps_negative_and_optional_scopes_separate(self):
        prefix = 'PREFIX ex: <https://example.test/> '
        valid = prefix + 'SELECT ?id WHERE { ?c a ex:Customer; ex:id ?id. FILTER NOT EXISTS {?c ex:missing ?v} }'
        evidence = typed_projection_evidence(valid)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['carrier_classes'], ['https://example.test/Customer'])
        self.assertEqual(evidence[0]['projected_variable'], 'id')
        for query in ('SELECT ?id WHERE {?c ex:id ?id. FILTER NOT EXISTS {?c a ex:Customer}}',
                      'SELECT ?id WHERE {?c ex:id ?id. OPTIONAL {?c a ex:Customer}}',
                      'SELECT ?id WHERE {{?c a ex:Customer; ex:id ?id} UNION {?c ex:id ?id}}',
                      'SELECT ?id WHERE {{SELECT ?id WHERE {?c a ex:Customer; ex:id ?id}}}'):
            self.assertEqual(typed_projection_evidence(prefix + query), [])

    def test_repaired_candidate_does_not_inherit_old_validator_errors(self):
        broken = spec()
        broken['measures'][0]['field'] = 'unknown'
        repaired = spec()
        repaired['contract_errors'] = ["measures.0: field 'unknown' is not in 'charges'."]
        responses, calls = [broken, repaired], []
        def create(**request):
            calls.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(responses.pop(0))))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec(
            {'query': QUESTION, 'schema_kind': 'sql', 'global_schema': SCHEMA,
             'expected_outputs': [{'name': 'average_total', 'type': 'numeric[]'}]}, client, 'fake',
            parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
        self.assertEqual(result['query_spec']['contract_errors'], [])
        self.assertIn('Downstream binding output contract:', calls[0]['messages'][0]['content'])

    def test_executor_passes_consumer_output_contract_to_subquery(self):
        import networkx as nx
        from script_diff_llm.pipeline.dag.executor import AOPExecutor
        executor = AOPExecutor({}, None)
        dag = nx.DiGraph()
        outputs = [{'name': 'customer_id', 'type': 'entity_id[]'}]
        dag.add_node('Q1', operator='Subquery', backend='SQL', outputs=outputs)
        dag.add_node('Q2', operator='Subquery', backend='SQL')
        dag.add_edge('Q1', 'Q2')
        with patch.object(executor, '_run_sql_subquery', return_value={'status': 'success', 'data': [], 'trace': {}}) as run:
            executor._execute_node('Q1', dag, QUESTION, {})
            self.assertEqual(run.call_args.args[-1]['expected_outputs'], outputs)

    def test_missing_downstream_projection_triggers_contract_repair(self):
        repaired = spec()
        repaired['measures'][0]['output_name'] = 'bound_total'
        repaired['output_schema'] = ['region', 'bound_total']
        responses, calls = [spec(), repaired], []
        def create(**request):
            calls.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(responses.pop(0))))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec(
            {'query': QUESTION, 'schema_kind': 'sql', 'global_schema': SCHEMA,
             'expected_outputs': [{'name': 'bound_total', 'type': 'numeric[]'}]}, client, 'fake',
            parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
        self.assertEqual(result['query_spec']['contract_errors'], [])
        self.assertIn('Missing downstream binding output: bound_total', calls[1]['messages'][0]['content'])

    def test_stored_field_lookup_does_not_force_a_new_aggregate(self):
        initial = spec()
        initial['query_type'] = 'aggregation'
        initial['measures'] = []
        initial['output_schema'] = ['region']
        repaired = copy.deepcopy(initial)
        repaired['query_type'] = 'point_lookup'
        responses = [initial, repaired]
        def create(**request):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(responses.pop(0))))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec(
            {'query': 'List the region of active customers.', 'schema_kind': 'sql', 'global_schema': SCHEMA}, client, 'fake',
            parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None)
        self.assertEqual(result['query_spec']['query_type'], 'point_lookup')
        self.assertEqual(result['query_spec']['contract_errors'], [])
        self.assertNotIn('measure_recovery_failed', result['query_spec'])


if __name__ == '__main__':
    unittest.main()
