"""Generic expression/statistic/grain regressions; no benchmark answers."""
import unittest
import duckdb
from support import load, registry


class FinalSpecFixTests(unittest.TestCase):
    def compute(self, expression, data):
        result = load('non_llm_operators.math_compute').pre_programmed_math_compute({
            'data': data, 'expression': expression, 'output_column': 'result', 'strict_spec': True})
        self.assertNotIn('error', result, result)
        return [row['result'] for row in result['data']]

    def contract(self, outputs, groups=(), metrics=()):
        return {'required_projection': outputs, 'group_by': [{'table': 'source', 'column': field} for field in groups],
                'metrics': list(metrics), 'order_by': [], 'limit': None}

    def test_boolean_and_equality_spellings_preserve_quoted_names(self):
        expression = "coalesce(column('true'), TRUE) = true AND NOT coalesce(column('false'), false)"
        self.assertEqual(self.compute(expression, [{'true': True, 'false': None},
                                                   {'true': False, 'false': False}]), [True, False])
        self.assertEqual(self.compute("where(x <> 1, 'FALSE = TRUE', 'null')", [{'x': 2}, {'x': 1}]),
                         ['FALSE = TRUE', 'null'])

    def test_searched_case_and_literal_membership_match_sql_null_behavior(self):
        expression = "CASE WHEN lower(substr(name,1,1)) NOT IN ('a','e') THEN 1 ELSE 0 END"
        self.assertEqual(self.compute(expression, [{'name': 'Alice'}, {'name': 'Ben'}, {'name': None}]), [0, 1, 0])
        self.assertEqual(self.compute("CASE WHEN x = 1 THEN 'one' WHEN x = 2 THEN 'two' ELSE 'other' END",
                                      [{'x': 1}, {'x': 2}, {'x': None}]), ['one', 'two', 'other'])
        self.assertEqual(self.compute("x NOT IN (1, null)", [{'x': 1}, {'x': 2}, {'x': None}]), [False, None, None])

    def test_string_functions_and_cumulative_totals(self):
        rows = [{'label': 'Direct Plan', 'amount': 2}, {'label': 'regular', 'amount': None},
                {'label': None, 'amount': 5}]
        self.assertEqual(self.compute("ilike(label, '%direct%')", rows), [True, False, None])
        self.assertEqual(self.compute("like(label, '%direct%')", rows), [False, False, None])
        self.assertEqual(self.compute("cumsum(amount)", rows), [2, None, 7])

    def test_expression_language_still_rejects_code_and_bad_statistic_parameters(self):
        for expression in ["__import__('os')", "x.__class__", '[x for x in y]', 'percentile(x, 90)',
                           "CASE WHEN x THEN 1", 'where(x,1,0']:
            result = load('non_llm_operators.math_compute').pre_programmed_math_compute({
                'data': [{'x': 1}], 'expression': expression, 'output_column': 'result'})
            self.assertIn('error', result, expression)

    def test_percentiles_match_duckdb_continuous_interpolation_and_nulls(self):
        aggregate = load('llm_operators.filter_aggregate').semantic_filter_aggregate
        rows = [{'group': 'a', 'value': value} for value in [1, 2, 10, None]]
        rows += [{'group': None, 'value': value} for value in [4, 8, None]]
        with duckdb.connect(':memory:') as connection:
            connection.execute('CREATE TABLE sample(g VARCHAR, v DOUBLE)')
            connection.executemany('INSERT INTO sample VALUES (?,?)', [(row['group'], row['value']) for row in rows])
            for q in [0, 0.25, 0.5, 0.9, 1]:
                expected = {group: value for group, value in connection.execute(
                    'SELECT g, quantile_cont(v, ?) FROM sample GROUP BY g', [q]).fetchall()}
                result = aggregate({'data': rows, 'operation': 'percentile_cont', 'quantile': q,
                                    'group_by': ['group'], 'input_column': 'value', 'output_column': 'p'})
                self.assertNotIn('error', result, result)
                self.assertEqual({row['group']: row['p'] for row in result['data']}, expected)
        for data in [[], [{'value': None}]]:
            result = aggregate({'data': data, 'operation': 'median', 'input_column': 'value', 'output_column': 'p'})
            self.assertEqual(result['data'], [{'p': None}])

    def test_percentile_expression_compiles_to_one_scalar_row(self):
        compiler = load('spec_runtime')
        spec = {'final_steps': [{'operator': 'Math_Compute', 'expression': "percentile(column('value'),0.9)",
                                'output_column': 'p'}], 'projection': ['p']}
        compiled = compiler.compile_spec(spec, {'raw': ['value']})
        self.assertEqual(compiled['contract_errors'], [])
        self.assertEqual(compiled['execution_steps'][0]['operator'], 'Filter_Aggregate')
        rows, log = load('execution').execute_spec(spec, {'raw': [{'value': 1}, {'value': 11}]}, registry())
        self.assertFalse(load('execution').execution_errors(log), log)
        self.assertEqual(rows, [{'p': 10.0}])
        for invalid in [-0.1, 1.1, True, float('inf')]:
            bad = compiler.compile_spec({'final_steps': [{'operation': 'percentile_cont', 'quantile': invalid,
                'input_column': 'value', 'output_column': 'p'}], 'projection': ['p']}, {'raw': ['value']})
            self.assertTrue(bad['contract_errors'])

    def test_grouped_percentage_accepts_scalar_denominator_and_rejects_wrong_group(self):
        compiler, understanding = load('spec_runtime'), load('query_understanding')
        for group in ['category', 'region']:
            spec = compiler.compile_spec({'final_steps': [
                {'id': 'part', 'operation': 'sum', 'input': 'raw', 'input_column': 'value',
                 'group_by': [group], 'output_column': 'part_total'},
                {'id': 'whole', 'operation': 'sum', 'input': 'raw', 'input_column': 'value', 'output_column': 'whole_total'},
                {'operator': 'Integrate', 'inputs': ['part', 'whole'], 'join_type': 'cross'},
                {'operator': 'Math_Compute', 'expression': 'part_total / nullif(whole_total,0)', 'output_column': 'share'}],
                'projection': ['share']}, {'raw': ['category', 'region', 'value']})
            self.assertEqual(spec['contract_errors'], [])
            contract = self.contract(['share'], ['category'], [{'output': 'share', 'outer_aggregation': 'none'},
                {'output': 'whole_total', 'outer_aggregation': 'sum'}])
            self.assertEqual(bool(understanding.final_contract_errors(spec, contract)), group != 'category')

    def test_join_equivalent_keys_accept_only_explicit_equality_and_same_dimension_count(self):
        compiler, understanding = load('spec_runtime'), load('query_understanding')
        for key in ['client_id', 'other_key']:
            spec = compiler.compile_spec({'final_steps': [
                {'id': 'totals', 'operation': 'sum', 'input': 'facts', 'input_column': 'value',
                 'group_by': ['client_id', 'other_key'], 'output_column': 'total'},
                {'operator': 'Integrate', 'inputs': ['profiles', 'totals'],
                 'left_on': ['id'], 'right_on': [key], 'join_type': 'inner'}],
                'projection': ['total']}, {'facts': ['client_id', 'other_key', 'value'], 'profiles': ['id']})
            contract = self.contract(['total'], ['id', 'other_key'])
            self.assertEqual(spec['contract_errors'], [])
            self.assertEqual(bool(understanding.final_contract_errors(spec, contract)), key != 'client_id')
            self.assertTrue(understanding.final_contract_errors(spec, self.contract(['total'], ['id'])))


if __name__ == '__main__':
    unittest.main()
