from copy import deepcopy
import unittest
from support import load, registry


class CaseExpressionTests(unittest.TestCase):
    def execute(self, expression, rows):
        return load('non_llm_operators.math_compute').pre_programmed_math_compute({
            'data': rows, 'strict_spec': True, 'expression': expression, 'output_column': 'result'})

    def test_multiple_conditions_preserve_order_boundaries_and_null_else_behavior(self):
        expression = "CASE WHEN column('score') <= 40 THEN 'Low' WHEN column('score') <= 70 THEN 'Moderate' ELSE 'High' END"
        result = self.execute(expression, [{'score': n} for n in (0, 40, 41, 70, 71, None)])
        self.assertFalse(result.get('error'), result)
        self.assertEqual([r['result'] for r in result['data']], ['Low', 'Low', 'Moderate', 'Moderate', 'High', 'High'])

    def test_missing_else_produces_null_and_nested_cases_work(self):
        result = self.execute('CASE WHEN value > 0 THEN CASE WHEN value > 2 THEN 2 ELSE 1 END END',
                              [{'value': -1}, {'value': 1}, {'value': 3}, {'value': None}])
        self.assertEqual([r['result'] for r in result['data']], [None, 1, 2, None])

    def test_literals_containing_case_keywords_and_case_named_field_are_preserved(self):
        expression = "CASE WHEN amount = 1 AND amount <> 0 THEN 'case when then else end' ELSE 'other' END"
        result = self.execute(expression, [{'amount': 1}, {'amount': 0}])
        self.assertEqual([r['result'] for r in result['data']], ['case when then else end', 'other'])
        self.assertEqual(self.execute('case + 1', [{'case': 1}])['data'][0]['result'], 2)

    def test_compiler_and_runtime_use_same_normalized_expression_and_recompile_idempotently(self):
        plan = {'final_steps': [{'id': 'band', 'operator': 'Math_Compute',
            'expression': "case when score <= 40 then 'Low' when score <= 70 then 'Moderate' else 'High' end", 'output_column': 'band'},
            {'operator': 'Filter_Aggregate', 'input': 'band', 'group_by': ['band'],
             'aggregations': [{'operation': 'avg', 'input_column': 'amount', 'output_column': 'mean'}]}],
            'projection': ['band', 'mean']}
        before = deepcopy(plan)
        spec = load('spec_runtime').compile_spec(plan, {'raw': ['score', 'amount']})
        self.assertEqual(spec['contract_errors'], [])
        self.assertTrue(spec['execution_steps'][0]['expression'].startswith('where('))
        self.assertEqual(plan, before)
        rebuilt = load('spec_runtime').compile_spec(spec, {'raw': ['score', 'amount']})
        self.assertEqual(spec['execution_steps'], rebuilt['execution_steps'])
        rows, log = load('execution').execute_spec(spec,
            {'raw': [{'score': 40, 'amount': 10}, {'score': 70, 'amount': None}, {'score': 71, 'amount': 20}]}, registry())
        self.assertEqual(load('execution').execution_errors(log), [])
        self.assertEqual(rows, [{'band': 'Low', 'mean': 10.0}, {'band': 'Moderate', 'mean': None}, {'band': 'High', 'mean': 20.0}])

    def test_malformed_cases_unknown_fields_and_unsafe_functions_are_rejected(self):
        for expression in ('CASE WHEN x > 0 THEN 1', 'CASE WHEN x > 0 THEN ELSE 0 END',
                           'CASE x WHEN 1 THEN 2 END', 'CASE WHEN missing > 0 THEN 1 ELSE 0 END',
                           "CASE WHEN x > 0 THEN __import__('os').system('echo BAD') ELSE 0 END"):
            with self.subTest(expression=expression):
                result = self.execute(expression, [{'x': 1}])
                self.assertTrue(result.get('error'), result)

    def test_repair_guidance_does_not_echo_runtime_values(self):
        feedback = load('prompt_boundary').feedback_for_prompt({'errors': ['invalid expression: PRIVATE_RUNTIME_VALUE']})
        self.assertIn('where(condition, true_value, false_value)', feedback)
        self.assertNotIn('PRIVATE_RUNTIME_VALUE', feedback)
