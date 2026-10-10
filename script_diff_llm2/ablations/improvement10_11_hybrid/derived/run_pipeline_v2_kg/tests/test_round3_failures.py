import unittest
from copy import deepcopy

from support import load, FakeClient, registry
from test_final_plan_repairs import contract, metric


SCHEMA = {
    'Owners': {'columns': [{'name': 'id', 'predicate_iri': 'urn:property:ownerId'},
                           {'name': 'tier', 'predicate_iri': 'urn:property:tier'}]},
    'Facts': {'columns': [{'name': 'ownerId', 'predicate_iri': 'urn:property:ownerId'},
                          {'name': 'factId', 'predicate_iri': 'urn:property:factId'}]},
}


class Round3Failures(unittest.TestCase):
    def build(self, plan, branches, value, schema=SCHEMA):
        return load('llm_operators.final_spec').semantic_build_final_spec(
            {'query': 'Use declared conditions and grouping', 'global_schema': schema,
             'processed_datasets': branches, 'answer_requirements': {'query_understanding': value}},
            FakeClient(plan))['final_spec']

    def test_null_units_are_normalized_and_nontext_units_rejected_before_semantic_checks(self):
        value = contract(required_projection=['n'], metrics=[metric('n', 'Facts', 'factId', 'count')])
        value['metrics'][0]['units'] = None
        understanding = load('query_understanding')
        with self.assertRaisesRegex(ValueError, 'units must be nonempty text'):
            understanding.validate_interpretation(value, 'Count facts', SCHEMA, {'rules': []})
        repaired = understanding._repair_model_interpretation(value, 'Count facts', SCHEMA, {'rules': []})
        self.assertEqual(repaired['metrics'][0]['units'], 'unspecified')
        self.assertEqual(understanding.validate_interpretation(repaired, 'Count facts', SCHEMA, {'rules': []}), repaired)
        for units in ([], {}, 1, False):
            value['metrics'][0]['units'] = units
            with self.assertRaises(ValueError):
                understanding.validate_interpretation(value, 'Count facts', SCHEMA, {'rules': []})

    def test_shared_rdf_property_groups_fact_reference_under_owner_key(self):
        plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'input': 'facts',
                'group_by': ['ownerId'], 'operation': 'count_rows', 'input_column': '*', 'output_column': 'n'}],
                'projection': ['ownerId', 'n']}
        branches = [{'id': 'facts', 'fields': ['ownerId', 'factId'], 'retrieval_specs': [{'class': 'Facts'}]}]
        value = contract(required_projection=['ownerId', 'n'], group_by=[{'table': 'Owners', 'column': 'id'}],
                         metrics=[metric('n', 'Facts', 'factId', 'none', 'count_rows', [{'table': 'Owners', 'column': 'id'}])])
        spec = self.build(plan, branches, value)
        self.assertEqual(spec['contract_errors'], [])
        data, log = load('execution').execute_spec(spec, {'facts': [{'ownerId': 'x', 'factId': 1},
            {'ownerId': 'x', 'factId': 2}]}, registry(), dataset_schemas={'facts': ['ownerId', 'factId']})
        self.assertEqual(load('execution').execution_errors(log), [])
        self.assertEqual(data, [{'ownerId': 'x', 'n': 2}])
        foreign = deepcopy(SCHEMA)
        foreign['Facts']['columns'][0]['predicate_iri'] = 'urn:foreign:ownerId'
        self.assertTrue(self.build(plan, branches, value, foreign)['contract_errors'])

    def test_subject_identity_does_not_gain_property_equivalence(self):
        schema = {'Facts': {'columns': [{'name': 'subject_iri'}]},
                  'Owners': {'columns': [{'name': 'subject_iri'}]}}
        branches = [{'id': 'facts', 'fields': ['subject_iri'], 'retrieval_specs': [{'class': 'Facts'}]}]
        plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'group_by': ['subject_iri'],
                                'operation': 'count_rows', 'input_column': '*', 'output_column': 'n'}],
                'projection': ['n']}
        value = contract(required_projection=['n'], group_by=[{'table': 'Owners', 'column': 'subject_iri'}])
        self.assertTrue(self.build(plan, branches, value, schema)['contract_errors'])

    def test_extra_display_group_is_still_rejected(self):
        branches = [{'id': 'facts', 'fields': ['ownerId', 'label'], 'retrieval_specs': [{'class': 'Facts'}]}]
        plan = {'final_steps': [{'operator': 'Filter_Aggregate', 'group_by': ['ownerId', 'label'],
                'operation': 'count_rows', 'input_column': '*', 'output_column': 'n'}], 'projection': ['n']}
        value = contract(required_projection=['n'], group_by=[{'table': 'Owners', 'column': 'id'}])
        self.assertTrue(self.build(plan, branches, value)['contract_errors'])

    def test_omitted_declared_order_is_added_but_existing_truncation_not_hidden(self):
        branches = [{'id': 'facts', 'fields': ['ownerId', 'amount'], 'retrieval_specs': [{'class': 'Facts'}]}]
        value = contract(required_projection=['ownerId'], order_by=[{'column': 'amount', 'direction': 'DESC'},
                         {'column': 'ownerId', 'direction': 'ASC'}], limit=2)
        spec = self.build({'projection': ['ownerId']}, branches, value)
        self.assertEqual(spec['contract_errors'], [])
        data, log = load('execution').execute_spec(spec, {'facts': [
            {'ownerId': 'b', 'amount': 3}, {'ownerId': 'a', 'amount': 3}, {'ownerId': 'c', 'amount': 1}]}, registry(),
            dataset_schemas={'facts': ['ownerId', 'amount']})
        self.assertEqual(data, [{'ownerId': 'a'}, {'ownerId': 'b'}])
        self.assertEqual(load('execution').execution_errors(log), [])
        bad = self.build({'final_steps': [{'operator': 'Order_By', 'order_by': value['order_by'], 'limit': 1}],
                          'projection': ['ownerId']}, branches, value)
        self.assertTrue(bad['contract_errors'])

    def test_shared_key_coalesce_preserves_outer_unmatched_rows(self):
        branches = [{'id': 'left', 'fields': ['key', 'a'], 'retrieval_specs': [{'class': 'Left'}]},
                    {'id': 'right', 'fields': ['key', 'b'], 'retrieval_specs': [{'class': 'Right'}]}]
        plan = {'final_steps': [{'id': 'joined', 'operator': 'Integrate', 'inputs': ['left', 'right'],
                 'left_on': ['key'], 'right_on': ['key'], 'join_type': 'outer'},
                {'operator': 'Math_Compute', 'expression': "coalesce(column('key'), column('key_right'))",
                 'output_column': 'display'}], 'projection': ['display', 'a', 'b']}
        spec = self.build(plan, branches, contract(required_projection=['display', 'a', 'b']), {})
        self.assertEqual(spec['contract_errors'], [])
        data, log = load('execution').execute_spec(spec, {'left': [{'key': 'x', 'a': 1}],
            'right': [{'key': 'y', 'b': 2}]}, registry(), dataset_schemas={b['id']: b['fields'] for b in branches})
        self.assertEqual(load('execution').execution_errors(log), [])
        self.assertEqual(data, [{'display': 'x', 'a': 1, 'b': None}, {'display': 'y', 'a': None, 'b': 2}])
        plan['final_steps'][1]['expression'] = "coalesce(column('key'), column('unrelated_missing'))"
        self.assertTrue(self.build(plan, branches, contract(required_projection=['display']), {})['contract_errors'])

    def test_existing_suffixed_field_is_not_rewritten(self):
        helper = load('plan_lineage').normalize_coalesced_key_expression
        expression = "coalesce(column('key'), column('key_right'))"
        self.assertEqual(helper(expression, ['key', 'key_right'], {'key': {'key_right'}}), expression)
        self.assertEqual(helper("column('key_right')", ['key'], {'key': {'key_right'}}), "column('key_right')")

    def test_calculated_categorical_dimension_must_not_be_omitted_from_partial_group(self):
        value = contract(required_projection=['tier', 'band', 'n'], group_by=[{'table': 'Owners', 'column': 'tier'}],
            metrics=[{**metric('band', 'Facts', 'factId'), 'units': 'categorical'}, metric('n', 'Facts', 'factId', 'count')])
        with self.assertRaisesRegex(ValueError, 'band is missing from final group_by'):
            load('query_understanding').validate_interpretation(value, 'Count by tier and band', SCHEMA, {'rules': []})

    def test_intermediate_count_distribution_requires_calculated_grouping(self):
        value = contract(required_projection=['tier', 'count_band', 'n'], group_by=[{'table': 'Owners', 'column': 'tier'}],
            metrics=[metric('count_band', 'Facts', 'factId', 'none', 'count_distinct', [{'table': 'Facts', 'column': 'ownerId'}]),
                     metric('n', 'Owners', 'id', 'none', 'count', [{'table': 'Owners', 'column': 'tier'}])])
        understanding = load('query_understanding')
        with self.assertRaisesRegex(ValueError, 'Intermediate measure count_band'):
            understanding.validate_interpretation(value, 'Counts by tier and number of facts', SCHEMA, {'rules': []})
        value['group_by'].append({'table': 'Facts', 'column': 'count_band'})
        self.assertEqual(understanding.validate_interpretation(value, 'Counts by tier and number of facts', SCHEMA, {'rules': []}), value)

    def test_provider_throttle_is_retryable_but_quota_and_local_bugs_are_not(self):
        helper = load('transport_errors')
        class Throttle(RuntimeError):
            status_code = 429
        self.assertTrue(helper.is_transient_connection_error(Throttle('rate_limit_exceeded: Too many requests')))
        self.assertTrue(helper.is_transient_connection_error('ThrottlingException: temporarily unavailable'))
        self.assertTrue(helper.is_transient_connection_error(Throttle('Error code: 429 rate_limit_exceeded: request quota exceeded')))
        self.assertFalse(helper.is_transient_connection_error(Throttle('insufficient_quota')))
        self.assertTrue(helper.is_quota_exhaustion_error(Throttle('insufficient_quota')))
        self.assertFalse(helper.is_transient_connection_error(AttributeError('None has no attribute lower')))
        self.assertFalse(helper.is_transient_connection_error(ValueError('Unknown field in plan')))


if __name__ == '__main__':
    unittest.main()
