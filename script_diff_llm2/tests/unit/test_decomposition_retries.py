"""Bounded planner repair checks; no model calls or benchmark examples."""
import unittest
from unittest.mock import Mock

from script_diff_llm.pipeline.dag.planner import AdvancedAOPPlanner
from script_diff_llm.pipeline.decomposition import _ensure_domain_coverage


class DecompositionRetriesTest(unittest.TestCase):
    def planner(self, responses):
        fn = Mock(side_effect=responses)
        return AdvancedAOPPlanner(None, {}, fn, 'test-model'), fn

    def valid(self):
        return {'nodes': [{'id': 'Q1', 'operator': 'Subquery', 'backend': 'SQL',
                           'inputs': [], 'outputs': []}]}

    def test_valid_single_node_does_not_retry(self):
        planner, fn = self.planner([self.valid()])
        dag = planner.plan_optimal_dag('List devices')
        self.assertEqual(fn.call_count, 1)
        self.assertFalse(dag.graph['decomposition_fallback'])

    def test_third_retry_can_recover_and_receives_feedback(self):
        planner, fn = self.planner([{'nodes': []}] * 3 + [self.valid()])
        dag = planner.plan_optimal_dag('List devices')
        self.assertEqual(fn.call_count, 4)
        self.assertIn('decomposition_feedback', fn.call_args_list[1].args[0])
        self.assertFalse(dag.graph['decomposition_fallback'])

    def test_cycles_retry_before_fallback(self):
        nodes = [{'id': name, 'operator': 'Subquery', 'backend': 'SQL',
                  'outputs': [{'name': 'key'}],
                  'inputs': [{'name': 'key', 'source': other + '.key'}]}
                 for name, other in [('A', 'B'), ('B', 'A')]]
        planner, fn = self.planner([{'nodes': nodes}] * 4)
        dag = planner.plan_optimal_dag('List connected devices')
        self.assertEqual(fn.call_count, 4)
        self.assertEqual(list(dag), ['Q1'])
        self.assertTrue(dag.graph['decomposition_fallback'])
        self.assertIn('cycles', dag.graph['decomposition_failures'][0])

    def test_scope_rejection_preserves_plan_for_repair(self):
        nodes = [{'id': 'A'}, {'id': 'B'}]
        result = _ensure_domain_coverage('List devices', {'nodes': nodes})
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['rejected_nodes'], nodes)
        self.assertIn('scope_clauses', result['decomposition_error'])


if __name__ == '__main__':
    unittest.main()
