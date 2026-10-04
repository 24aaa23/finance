"""Generic source evidence and bounded execution repairs, with fake model calls."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rdflib import Graph
from script_diff_llm.backends.kg import load_rdf_knowledge_graph
from script_diff_llm.pipeline.dag.executor import AOPExecutor
from script_diff_llm.pipeline.specification import cleanup_query_spec


class SourceGroundingAndSqlRepair(unittest.TestCase):
    def test_rdf_small_domains_preserve_separators_case_and_ownership(self):
        source = Graph().parse(data='''@prefix ex: <https://synthetic.example/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:a a ex:Record; ex:category "A|B"; ex:label "display-one"; rdfs:label "record name" .
ex:b a ex:Record; ex:category "Mixed Case"; ex:label "display-two" .''', format='turtle')
        for i in range(33):
            source.parse(data=f'@prefix ex: <https://synthetic.example/> . ex:n{i} a ex:Record; ex:identifier "id-{i}" .', format='turtle')
        schema_text = '''@prefix ex: <https://synthetic.example/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Record a owl:Class; rdfs:comment "Source record definition" .
ex:category rdfs:comment "Record classification" .'''
        def execute(query, *_):
            return {'status': 'success', 'data': [{str(k): str(v) for k, v in row.asdict().items()} for row in source.query(query)]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.ttl'
            path.write_text(schema_text)
            with patch('script_diff_llm.backends.kg.execute_sparql_on_fuseki', side_effect=execute):
                schema = load_rdf_knowledge_graph(str(path), 'unused', 5)
        columns = {c['name']: c for c in schema['Record']['columns']}
        self.assertEqual(columns['category']['allowed_values'], ['A|B', 'Mixed Case'])
        self.assertTrue(columns['category']['allowed_values_complete'])
        self.assertNotIn('allowed_values', columns['identifier'])
        self.assertEqual(columns['https://synthetic.example/label']['allowed_values'], ['display-one', 'display-two'])
        self.assertEqual(columns['http://www.w3.org/2000/01/rdf-schema#label']['allowed_values'], ['record name'])
        self.assertEqual(columns['category']['description'], 'Record classification')
        plan = {'base_entity': 'Record', 'filters': [{'source_class': 'Record', 'field': 'category', 'operator': '=', 'value': 'mixed case'}]}
        cleaned = cleanup_query_spec(plan, 'Mixed Case records', ['Record'], str.lower, schema=schema)
        self.assertEqual(cleaned['filters'][0]['value'], 'Mixed Case')
        plan['filters'][0]['field'] = 'https://synthetic.example/label'
        cleaned = cleanup_query_spec(plan, 'Mixed Case records', ['Record'], str.lower, schema=schema)
        self.assertEqual(cleaned['filters'][0]['field'], 'https://synthetic.example/label')
        self.assertEqual(cleaned['filters'][0]['value'], 'mixed case')

    def test_rdf_profile_failure_keeps_physical_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.ttl'
            path.write_text('@prefix ex: <https://synthetic.example/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Record a owl:Class .')
            responses = [{'status': 'success', 'data': [{'class': 'https://synthetic.example/Record', 'p': 'https://synthetic.example/category', 'datatype': 'http://www.w3.org/2001/XMLSchema#string'}]},
                         {'status': 'error', 'error_message': 'timeout'}]
            with patch('script_diff_llm.backends.kg.execute_sparql_on_fuseki', side_effect=responses):
                schema = load_rdf_knowledge_graph(str(path), 'unused', 5)
        self.assertEqual(schema['Record']['columns'][0]['name'], 'category')
        self.assertNotIn('allowed_values', schema['Record']['columns'][0])

    def executor(self, budget=3):
        return AOPExecutor({}, rdf_graph=None, scan_refine_max_retries=budget)

    def trace(self):
        return {'attempts': [], 'self_heal_attempts': 0}

    def test_repair_preserves_spec_bindings_and_revalidates_before_rescan(self):
        inputs = {'sql': 'SELECT missing FROM records', 'query_spec': {'output_schema': ['value']},
                  'bound_inputs': {'id': ['C-1']}}
        original = copy.deepcopy(inputs)
        trace = self.trace()
        error = {'status': 'error', 'error_type': 'sql_no_such_column', 'error_message': 'no such column: missing'}
        success = {'status': 'success', 'data': [{'value': 5}], 'row_count': 1}
        with patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.pre_programmed_scan_sql', side_effect=[error, success]) as scan, \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_generate_sql', return_value={'sql': 'SELECT value FROM records'}) as generate, \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_pre_scan_validate_sql', return_value={'pre_scan_validation': {'is_valid': True}}) as validate:
            result = self.executor()._scan_sql_with_repair(inputs, trace)
        self.assertEqual(result, success)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(inputs['query_spec'], original['query_spec'])
        self.assertEqual(inputs['bound_inputs'], original['bound_inputs'])
        self.assertEqual(trace['self_heal_attempts'], 1)

    def test_rejected_repair_is_never_scanned_and_budget_is_bounded(self):
        error = {'status': 'error', 'error_type': 'sql_execution_error', 'error_message': 'syntax error'}
        with patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.pre_programmed_scan_sql', return_value=error) as scan, \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_generate_sql', return_value={'sql': 'SELECT wrong FROM records'}) as generate, \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_pre_scan_validate_sql', return_value={'pre_scan_validation': {'is_valid': False, 'severity': 'hard_error', 'reason': 'invalid'}}):
            result = self.executor(3)._scan_sql_with_repair({'sql': 'invalid'}, self.trace())
        self.assertEqual(result['status'], 'error')
        self.assertEqual(scan.call_count, 1)
        self.assertEqual(generate.call_count, 2)

    def test_database_environment_errors_do_not_trigger_model_repair(self):
        error = {'status': 'error', 'error_type': 'db_path_error', 'error_message': 'missing file'}
        with patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.pre_programmed_scan_sql', return_value=error), \
             patch('script_diff_llm.pipeline.dag.executor.sql_pipeline.semantic_generate_sql') as generate:
            self.assertEqual(self.executor()._scan_sql_with_repair({'sql': 'SELECT 1'}, self.trace()), error)
        generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
