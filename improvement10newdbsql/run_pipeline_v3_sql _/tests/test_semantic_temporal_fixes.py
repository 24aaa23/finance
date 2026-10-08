"""Generic logical and temporal regressions; no benchmark answers or model calls."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
from support import load, registry


class LogicalConditionsTests(unittest.TestCase):
    def setUp(self):
        self.check = load('llm_operators.query_spec')._answer_requirement_errors
        self.schema = {'records': {'columns': [{'name': 'key'}, {'name': 'flag'}]}}
        self.condition = {'source_class': 'records', 'stage': 'scan', 'branch_ids': ['q'],
                          'any': [{'field': 'flag', 'operator': '=', 'value': True},
                                  {'field': 'flag', 'operator': 'is_null', 'value': None}]}
        self.decomp = {'answer_requirements': {'predicates': [self.condition]}}
        self.spec = {'id': 'q', 'retrieval_specs': [{'class': 'records', 'fields': ['key', 'flag'],
                                                  'filters': [self.condition]}]}

    def test_or_contract_passes_and_flattened_and_fails(self):
        self.assertEqual(self.check(self.spec, self.decomp, self.schema), [])
        self.spec['retrieval_specs'][0]['filters'] = self.condition['any']
        errors = self.check(self.spec, self.decomp, self.schema)
        self.assertTrue(any('Contradictory' in e for e in errors))
        self.assertTrue(any('drops or changes' in e for e in errors))

    def test_mandatory_predicate_inside_or_does_not_pass(self):
        self.decomp['answer_requirements']['predicates'] = [dict(self.condition, **self.condition['any'][0])]
        self.decomp['answer_requirements']['predicates'][0].pop('any')
        self.assertTrue(self.check(self.spec, self.decomp, self.schema))

    def test_commutative_tree_and_nested_not_are_preserved(self):
        condition = load('sql_conditions').condition_tree
        self.assertEqual(condition({'any': self.condition['any']}), condition({'any': self.condition['any'][::-1]}))
        self.assertNotEqual(condition({'any': self.condition['any']}), condition({'not': {'any': self.condition['any']}}))

    def test_calculations_cannot_be_quoted_raw_values(self):
        errors = load('sql_conditions').raw_condition_errors({'field': 'date', 'value': '(SELECT MAX(date) FROM records)'})
        self.assertTrue(errors)


class TemporalFunctionsTests(unittest.TestCase):
    def compute(self, expression, rows, **options):
        result = load('non_llm_operators.math_compute').pre_programmed_math_compute(
            {'expression': expression, 'data': rows, 'strict_spec': True, 'output_column': 'result', **options})
        self.assertNotIn('error', result, result)
        return [row['result'] for row in result['data']]

    def test_date_difference_matches_duckdb_including_null_and_negative(self):
        pairs = [('2024-02-28', '2024-03-01'), ('2024-03-01', '2024-02-28'), (None, '2024-03-01')]
        with duckdb.connect() as db:
            expected = [db.execute("SELECT date_diff('day', CAST(? AS DATE), CAST(? AS DATE))", pair).fetchone()[0] for pair in pairs]
        self.assertEqual(self.compute("date_diff('day',a,b)", [{'a': a, 'b': b} for a, b in pairs]), expected)
        self.assertEqual(self.compute("(date(b)-date(a))/365.25", [{'a': '2024-02-28', 'b': '2024-03-01'}]), [2/365.25])
        self.assertEqual(self.compute("date(b)-a", [{'a': '2024-02-28', 'b': '2024-03-01'}]), [2])
        self.assertEqual(self.compute("date(a)<b", [{'a': '2024-02-28', 'b': '2024-03-01'}]), [True])

    def test_lag_rolling_and_partition_match_sql(self):
        rows = [{'entity': 'A', 'n': 1, 'amount': 2}, {'entity': 'A', 'n': 2, 'amount': None},
                {'entity': 'A', 'n': 3, 'amount': 8}, {'entity': 'B', 'n': 4, 'amount': 20}]
        with duckdb.connect() as db:
            db.execute('CREATE TABLE amounts(entity VARCHAR,n INTEGER,amount DOUBLE)')
            db.executemany('INSERT INTO amounts VALUES (?,?,?)', [tuple(row.values()) for row in rows])
            expected = db.execute('SELECT lag(amount,1,99) OVER(PARTITION BY entity ORDER BY n), '
                'avg(amount) OVER(PARTITION BY entity ORDER BY n ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) '
                'FROM amounts ORDER BY n').fetchall()
        self.assertEqual(self.compute('lag(amount,1,99)', rows, window_partition_by=['entity']), [r[0] for r in expected])
        self.assertEqual(self.compute('rolling_mean(amount,3,1)', rows, window_partition_by=['entity']), [r[1] for r in expected])

    def test_date_add_trunc_and_fiscal_parts(self):
        self.assertEqual(self.compute("dateadd('month',1,date('2024-01-31'))", [{}]), ['2024-02-29T00:00:00+00:00'])
        self.assertEqual(self.compute("date_trunc('quarter',d)", [{'d': '2024-05-19'}]), ['2024-04-01T00:00:00+00:00'])
        op = load('non_llm_operators.date_extract').pre_programmed_date_extract
        for part, expected in [('quarter', '2026-Q1'), ('quarter_start', '2026-01-01'),
                               ('fiscal_year', 2025), ('fiscal_quarter', 4)]:
            result = op({'data': [{'d': '2026-03-31'}, {'d': None}], 'input_column': 'd', 'part': part,
                         'output_column': 'result', 'fiscal_start_month': 4})
            self.assertEqual([r['result'] for r in result['data']], [expected, None])

    def test_invalid_dates_offsets_and_python_access_rejected(self):
        op = load('non_llm_operators.math_compute').pre_programmed_math_compute
        for expression in ["date('bad date')", "lag(x,-1)", "rolling_mean(x,0)", "x.shift(1)", "__import__('os')"]:
            self.assertIn('error', op({'expression': expression, 'data': [{'x': 2}]}))


class FinalContractTests(unittest.TestCase):
    def test_cumulative_sum_passes_but_different_formula_fails(self):
        compile_spec = load('spec_runtime').compile_spec
        check = load('query_understanding').final_contract_errors
        contract = {'metrics': [{'output': 'running_total', 'outer_aggregation': 'sum'}],
                    'group_by': [{'column': 'day'}], 'required_projection': ['day', 'running_total'], 'order_by': [], 'limit': None}
        plan = {'final_steps': [
            {'id': 'daily', 'operator': 'Filter_Aggregate', 'input': 'raw', 'group_by': ['day'], 'operation': 'sum', 'input_column': 'amount', 'output_column': 'daily_amount'},
            {'id': 'ordered', 'operator': 'Order_By', 'input': 'daily', 'order_by': [{'column': 'day', 'direction': 'ASC'}]},
            {'operator': 'Math_Compute', 'input': 'ordered', 'expression': "cumsum(column('daily_amount'))", 'output_column': 'running_total'}],
            'projection': ['day', 'running_total']}
        spec = compile_spec(plan, {'raw': ['day', 'amount']})
        self.assertEqual(spec['contract_errors'], [])
        self.assertEqual(check(spec, contract), [])
        result, log = load('execution').execute_spec(spec, {'raw': [{'day': '2025-01-01', 'amount': 2}, {'day': '2025-01-02', 'amount': 5}]}, registry())
        self.assertFalse(load('execution').execution_errors(log))
        self.assertEqual([r['running_total'] for r in result], [2, 7])
        plan['final_steps'][-1]['expression'] = "column('daily_amount') * 2"
        self.assertTrue(check(compile_spec(plan, {'raw': ['day', 'amount']}), contract))
        plan['final_steps'][-1]['expression'] = "cumsum(column('daily_amount'))"
        plan['final_steps'][-1]['input'] = 'daily'
        self.assertTrue(any('Order_By' in error for error in compile_spec(plan, {'raw': ['day', 'amount']})['contract_errors']))

    def test_latest_snapshot_grain_reduced_only_by_matching_max_join(self):
        compile_spec = load('spec_runtime').compile_spec
        plan = {'final_steps': [
            {'id': 'daily', 'operator': 'Filter_Aggregate', 'input': 'raw', 'group_by': ['entity', 'day'], 'operation': 'sum', 'input_column': 'amount', 'output_column': 'total'},
            {'id': 'latest', 'operator': 'Filter_Aggregate', 'input': 'raw', 'group_by': ['entity'], 'operation': 'max', 'input_column': 'day', 'output_column': 'last_day'},
            {'operator': 'Integrate', 'inputs': ['daily', 'latest'], 'left_on': ['entity', 'day'], 'right_on': ['entity', 'last_day'], 'join_type': 'inner'}],
            'projection': ['entity', 'total']}
        spec = compile_spec(plan, {'raw': ['entity', 'day', 'amount']})
        total = next(r for r in spec['aggregation_lineage'] if r['output_column'] == 'total')
        self.assertEqual(total['group_by'], ['entity'])
        plan['final_steps'][-1]['left_on'] = ['entity']
        plan['final_steps'][-1]['right_on'] = ['entity']
        total = next(r for r in compile_spec(plan, {'raw': ['entity', 'day', 'amount']})['aggregation_lineage'] if r['output_column'] == 'total')
        self.assertEqual(total['group_by'], ['entity', 'day'])


class GradedRetryTests(unittest.TestCase):
    def test_keeps_matches_ungraded_and_stale_grades_and_retries_errors(self):
        statuses = ['MATCH', 'MISMATCH', 'PARTIAL', 'MISMATCH', 'FINAL_SPEC_ERROR']
        raw = [{'Sample Row ID': str(i), 'Question': 'q', 'Ground Truth': '[]', 'New Pipeline Result': '[]',
                'New Status': 'FINAL_SPEC_ERROR' if i == 4 else 'PIPELINE_SUCCESS'} for i in range(6)]
        grades = [{**row, 'New Status': status} for row, status in zip(raw, statuses)]
        grades[3]['New Pipeline Result'] = 'old answer'
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'graded.csv'
            with p.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(grades[0])); writer.writeheader(); writer.writerows(grades)
            self.assertEqual([r['Sample Row ID'] for r in load('retry_batch').graded_retry_rows(raw, p)], ['1', '2', '4'])


if __name__ == '__main__':
    unittest.main()
