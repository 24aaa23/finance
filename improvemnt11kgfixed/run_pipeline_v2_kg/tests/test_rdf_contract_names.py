from copy import deepcopy
import json
import unittest
from support import FakeClient, load


def schema():
    return {'Items': {'backend': 'rdf', 'class_iri': 'https://example.org/Items',
        'subject_field': 'subject_iri', 'source_tables': ['DECLARED_ITEMS_SOURCE'], 'columns': [
            {'name': 'subject_iri', 'datatype': 'resource_iri'},
            {'name': 'recordId', 'predicate_iri': 'https://example.org/recordId'},
            {'name': 'amount', 'predicate_iri': 'https://example.org/amount',
             'ontology_attribute': 'stored_amount', 'datatype': 'numeric'}]},
        'Other': {'backend': 'rdf', 'class_iri': 'https://example.org/Other',
                  'columns': [{'name': 'recordId'}]}}


class RdfContractNameTests(unittest.TestCase):
    def run_response(self, response):
        return load('llm_operators.query_spec').semantic_build_query_spec({
            'query': 'List records with amount below -20', 'global_schema': schema(),
            'subquestion': {'id': 'q1', 'source_class': 'Items', 'required_fields': ['recordId', 'amount']},
            'decomposition': {'answer_requirements': {'predicates': [{'id': 'p1', 'source_class': 'Items',
                'field': 'amount', 'operator': '<', 'value': -20, 'stage': 'scan', 'branch_ids': ['q1']}]}}},
            FakeClient(response))['query_spec']

    def test_declared_class_iri_is_the_same_source_and_renders_correct_query(self):
        for name in ('Items', 'https://example.org/Items', '<https://example.org/Items>', 'DECLARED_ITEMS_SOURCE'):
            with self.subTest(name=name):
                response = {'id': 'q1', 'retrieval_specs': [{'id': 'q1', 'class': name,
                    'entity_key': ['subject_iri'], 'fields': ['subject_iri', 'recordId', 'amount'],
                    'filters': [{'field': 'amount', 'operator': '<', 'value': -20, 'value_type': 'number'}]}]}
                before = deepcopy(response)
                spec = self.run_response(response)
                self.assertEqual(spec['contract_errors'], [])
                self.assertEqual(spec['retrieval_specs'][0]['class'], 'Items')
                query = load('raw_query').render_raw_query(spec['retrieval_specs'][0], schema())
                self.assertIn('a <https://example.org/Items>', query)
                self.assertIn('FILTER(?amount < -20)', query)
                self.assertEqual(response, before)

    def test_real_source_switch_and_same_tail_in_foreign_namespace_remain_errors(self):
        for name in ('https://example.org/Other', 'https://foreign.example/Items'):
            with self.subTest(name=name):
                spec = self.run_response({'id': 'q1', 'retrieval_specs': [{'id': 'q1', 'class': name,
                    'entity_key': ['recordId'], 'fields': ['recordId'], 'filters': []}]})
                self.assertTrue(any('changed assigned source' in error for error in spec['contract_errors']))

    def test_property_iris_and_documented_field_names_normalize_without_touching_literals(self):
        response = {'id': 'q1', 'output_schema': ['@id', 'https://example.org/recordId', 'stored_amount'],
            'retrieval_specs': [{'id': 'q1', 'class': 'https://example.org/Items',
                'fields': ['@id', 'https://example.org/recordId', 'stored_amount'],
                'entity_key': ['@id'], 'filters': [
                    {'field': '<https://example.org/amount>', 'operator': '<', 'value': -20},
                    {'field': 'recordId', 'operator': '=', 'value': 'https://foreign.example/Items'}]}]}
        spec = self.run_response(response)
        self.assertEqual(spec['contract_errors'], [])
        retrieval = spec['retrieval_specs'][0]
        self.assertEqual(retrieval['fields'], ['subject_iri', 'recordId', 'amount'])
        self.assertEqual(retrieval['filters'][1]['value'], 'https://foreign.example/Items')
        self.assertEqual(spec['output_schema'], retrieval['fields'])

    def test_nested_predicate_fields_are_normalized(self):
        spec = {'retrieval_specs': [{'class': 'https://example.org/Items', 'fields': ['amount'],
            'filters': [{'any': [{'field': 'https://example.org/amount', 'operator': '>', 'value': 0},
                                {'not': {'field': 'stored_amount', 'operator': 'is_null', 'value': None}}]}]}]}
        load('llm_operators.query_spec')._normalize_rdf_fields(spec, schema())
        filters = spec['retrieval_specs'][0]['filters'][0]['any']
        self.assertEqual(filters[0]['field'], 'amount')
        self.assertEqual(filters[1]['not']['field'], 'amount')

    def test_ambiguous_bindings_are_not_guessed(self):
        source = schema()
        source['Alias'] = deepcopy(source['Items'])
        self.assertEqual(load('rdf_contracts').class_key('https://example.org/Items', source), 'https://example.org/Items')
        source['Items']['columns'].append({'name': 'different', 'predicate_iri': 'https://example.org/amount'})
        self.assertEqual(load('rdf_contracts').field_key('https://example.org/amount', 'Items', source), 'https://example.org/amount')

    def test_decompose_normalizes_declared_source_and_fields_without_changing_filter_literals(self):
        response = {'selected_decomposition': {'subquestions': [{'id': 'q1', 'source_class': 'https://example.org/Items',
            'retrieval_grain': ['subject_iri'], 'required_fields': ['stored_amount']}],
            'answer_requirements': {'predicates': [{'id': 'p1', 'source_class': 'https://example.org/Items',
                'field': 'stored_amount', 'operator': '<', 'value': -20, 'branch_ids': ['q1'], 'stage': 'scan'}]}}}
        result = load('llm_operators.decompose').semantic_decompose_question({
            'query': 'Amounts below -20', 'global_schema': schema()}, FakeClient(response))['selected_decomposition']
        self.assertEqual(result['contract_errors'], [])
        self.assertEqual(result['subquestions'][0]['source_class'], 'Items')
        self.assertEqual(result['subquestions'][0]['required_fields'], ['amount'])
        self.assertEqual(result['answer_requirements']['predicates'][0]['value'], -20)

    def test_retrieve_and_interpretation_use_the_same_declared_name_resolution(self):
        result = load('llm_operators.retrieve').semantic_retrieve({'query': 'List amounts', 'table_index': schema()},
            FakeClient(['https://example.org/Items', 'DECLARED_ITEMS_SOURCE', 'https://foreign.example/Items']))
        self.assertEqual(result['retrieved_tables'], ['Items'])
        value = {'bindings': [{'table': 'https://example.org/Items', 'column': 'stored_amount'}],
                 'required_projection': ['my_custom_alias'], 'group_by': [], 'metrics': [], 'filters': []}
        load('rdf_contracts').normalize_interpretation_refs(value, schema())
        self.assertEqual(value['bindings'], [{'table': 'Items', 'column': 'amount'}])
        self.assertEqual(value['required_projection'], ['my_custom_alias'])

    def test_final_output_retains_documented_aliases_and_preserves_null_values(self):
        source = schema()
        branches = [{'id': 'raw', 'fields': ['subject_iri', 'amount'],
                     'retrieval_specs': [{'class': 'Items', 'fields': ['subject_iri', 'amount']}]}]
        requirements = {'query_understanding': {'required_projection': ['stored_amount'],
            'metrics': [], 'group_by': [], 'bindings': [], 'filters': [], 'order_by': [], 'limit': None}}
        client = FakeClient({'final_steps': [], 'projection': ['amount']})
        result = load('llm_operators.final_spec').semantic_build_final_spec({'query': 'List amounts',
            'global_schema': source, 'processed_datasets': branches, 'answer_requirements': requirements}, client)['final_spec']
        self.assertEqual(result['contract_errors'], [])
        self.assertEqual(result['projection'], ['stored_amount'])
        from support import registry
        for rows in ([{'subject_iri': 'urn:one', 'amount': None}, {'subject_iri': 'urn:two', 'amount': 3}], []):
            data, log = load('execution').execute_spec(result, {'raw': rows}, registry(),
                                                      dataset_schemas={'raw': ['subject_iri', 'amount']})
            self.assertEqual(load('execution').execution_errors(log), [])
            self.assertEqual(data, [{'stored_amount': None}, {'stored_amount': 3}] if rows else [])

    def test_output_aliases_are_not_invented_for_metrics_or_unknown_names(self):
        helper = load('llm_operators.final_spec').retain_documented_output_aliases
        plan = {'final_steps': [], 'projection': ['amount']}
        compiled = load('spec_runtime').compile_spec(plan, {'raw': ['amount']})
        branches = [{'id': 'raw', 'retrieval_specs': [{'class': 'Items'}]}]
        for requirements in ({'query_understanding': {'required_projection': ['unknown_alias'], 'metrics': []}},
                             {'query_understanding': {'required_projection': ['stored_amount'],
                                'metrics': [{'output': 'stored_amount'}]}}):
            self.assertIs(helper(plan, compiled, requirements, branches, schema()), plan)
