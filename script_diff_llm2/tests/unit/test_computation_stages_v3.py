"""Stage and metadata behavior on synthetic data; no benchmark fixtures."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rdflib import Graph
from script_diff_llm.backends.kg import load_rdf_knowledge_graph
from script_diff_llm.backends.sparql_contract import date_comparison_errors
from script_diff_llm.backends.sql import _deterministic_entity_group_sql
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.specification import cleanup_query_spec
from tests.unit.test_portable_contracts import SCHEMA, QUESTION, spec


class ComputationStagesV3(unittest.TestCase):
    def test_sql_prepare_rejects_invalid_having_and_parentheses_before_model_call(self):
        from script_diff_llm.backends.sql import semantic_pre_scan_validate_sql
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE charges(amount INTEGER)')
                conn.execute('INSERT INTO charges VALUES(5)')
            for sql in ['SELECT amount FROM charges HAVING amount > 1',
                        'SELECT SUM(amount)) FROM charges']:
                result = semantic_pre_scan_validate_sql({'sql': sql, 'db_path': str(path)}, None, 'fake')
                self.assertFalse(result['pre_scan_validation']['is_valid'])
                self.assertIn('preparation failed', result['pre_scan_validation']['reason'])
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute('SELECT amount FROM charges').fetchall(), [(5,)])

    def clean(self, plan):
        return cleanup_query_spec(plan, QUESTION, list(SCHEMA), str.lower, schema_kind='sql', schema=SCHEMA)

    def test_physical_aggregate_does_not_require_formula_at_final_grain(self):
        plan = spec()
        plan['measures'][0]['formula_stage'] = 'final_group'
        clean = self.clean(plan)
        self.assertEqual(clean['measures'][0]['operand_kind'], 'physical')
        self.assertIsNone(clean['measures'][0]['formula_stage'])
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])
        self.assertIsNotNone(_deterministic_entity_group_sql({'query_spec': clean, 'sql_schema': SCHEMA}))

    def test_physical_expression_operands_remain_schema_checked(self):
        plan = spec()
        plan['measures'][0].update(formula='amount * 2', formula_fields=['amount'], formula_stage='final_group')
        clean = self.clean(plan)
        self.assertEqual(clean['measures'][0]['formula_stage'], 'row')
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])
        clean['measures'][0]['formula_fields'] = ['fabricated']
        self.assertTrue(any('unknown formula operand' in e for e in validate_query_spec(clean, SCHEMA)))

    def test_alias_population_predicate_moves_to_aggregate_with_provenance(self):
        plan = spec()
        plan['measures'][0]['population_filters'] = [
            {'source_class': 'derived', 'field': 'average_total', 'operator': '>', 'value': 20}]
        plan['requirements'][-1]['implemented_by'] = ['measures.0.population_filters.0']
        clean = self.clean(plan)
        measure = clean['measures'][0]
        self.assertEqual(measure['population_filters'], [])
        self.assertEqual(measure['aggregate_filters'][0]['stage'], 'entity')
        self.assertEqual(measure['aggregate_filters'][0]['scope'], 'population')
        self.assertEqual(clean['requirements'][-1]['implemented_by'], ['measures.0.aggregate_filters.0'])
        self.assertEqual(split_contract_errors(validate_query_spec(clean, SCHEMA, QUESTION))[0], [])

    def test_threshold_is_after_average_and_restricts_shared_entities(self):
        plan = spec()
        plan['filters'] = []
        plan['measures'][0].update(per_entity_operation='AVG', aggregate_filters=[
            {'field': 'average_total', 'operator': '>', 'value': 20, 'stage': 'entity', 'scope': 'population'}])
        plan['measures'].append({'source_class': 'charges', 'field': 'charge_id', 'output_name': 'events',
                                 'per_entity_operation': 'COUNT', 'final_operation': 'SUM'})
        plan['output_schema'].append('events')
        sql = _deterministic_entity_group_sql({'query_spec': self.clean(plan), 'sql_schema': SCHEMA})
        self.assertIn('HAVING', sql)
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE customers(customer_id INTEGER, region TEXT, active INTEGER);'
                               'CREATE TABLE charges(customer_id INTEGER, amount INTEGER, charge_id INTEGER);'
                               "INSERT INTO customers VALUES(1,'north',1),(2,'north',1);"
                               'INSERT INTO charges VALUES(1,5,1),(1,25,2),(2,30,3),(2,40,4);')
            self.assertEqual(conn.execute(sql).fetchall(), [('north', 35.0, 2)])
            plan['measures'][0]['aggregate_filters'][0]['scope'] = 'metric'
            metric_sql = _deterministic_entity_group_sql({'query_spec': self.clean(plan), 'sql_schema': SCHEMA})
            self.assertEqual(conn.execute(metric_sql).fetchall(), [('north', 35.0, 4)])

    def test_final_group_threshold_is_applied_after_group_aggregate(self):
        plan = spec()
        plan['filters'] = []
        plan['measures'][0]['aggregate_filters'] = [{'field': 'average_total', 'operator': '>',
            'value': 20, 'stage': 'final_group', 'scope': 'population'}]
        sql = _deterministic_entity_group_sql({'query_spec': self.clean(plan), 'sql_schema': SCHEMA})
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE customers(customer_id INTEGER, region TEXT, active INTEGER);'
                               'CREATE TABLE charges(customer_id INTEGER, amount INTEGER, charge_id INTEGER);'
                               "INSERT INTO customers VALUES(1,'north',1),(2,'south',1);"
                               'INSERT INTO charges VALUES(1,30,1),(2,10,2);')
            self.assertEqual(conn.execute(sql).fetchall(), [('north', 30.0)])

    def test_field_comparison_uses_identifier_instead_of_string_literal(self):
        from script_diff_llm.backends.sql import _profile_filter_sql
        predicate = {'field': 'amount', 'operator': '>', 'value': 'limit', 'value_type': 'field'}
        self.assertEqual(_profile_filter_sql([predicate], {'amount', 'limit'}, ''), '"amount" > "limit"')
        self.assertIsNone(_profile_filter_sql([predicate], {'amount'}, ''))

    def test_invalid_aggregate_stage_or_alias_still_blocks(self):
        plan = spec()
        plan['measures'][0]['aggregate_filters'] = [{'field': 'unknown', 'operator': '>', 'value': 0,
                                                   'stage': 'row'}]
        self.assertTrue(split_contract_errors(validate_query_spec(self.clean(plan), SCHEMA))[0])

    def test_extracted_datatype_reaches_date_validator(self):
        schema_text = '''@prefix ex: <https://test.example/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Event a owl:Class .'''
        graph = Graph().parse(data='''@prefix ex: <https://test.example/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:event a ex:Event; ex:day "2025-02-01"^^xsd:date; ex:title "sample" .''', format='turtle')
        def execute(query, *_):
            rows = [{str(key): str(value) for key, value in row.asdict().items()} for row in graph.query(query)]
            return {'status': 'success', 'data': rows}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.ttl'
            path.write_text(schema_text)
            with patch('script_diff_llm.backends.kg.execute_sparql_on_fuseki', side_effect=execute):
                metadata = load_rdf_knowledge_graph(str(path), 'unused', 10)
        self.assertEqual(metadata['Event']['literal_datatypes']['day'], ['http://www.w3.org/2001/XMLSchema#date'])
        query = 'SELECT ?d WHERE { ?s <https://test.example/day> ?d . FILTER(?d >= "2025-01-01") }'
        self.assertTrue(date_comparison_errors(query, metadata))
        typed = query.replace('"2025-01-01"', '"2025-01-01"^^<http://www.w3.org/2001/XMLSchema#date>')
        self.assertEqual(date_comparison_errors(typed, metadata), [])


if __name__ == '__main__':
    unittest.main()
