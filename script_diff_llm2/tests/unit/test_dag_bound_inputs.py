import unittest

import networkx as nx
import rdflib

from script_diff_llm.pipeline.dag.executor import AOPExecutor


class DagBoundInputResolutionTest(unittest.TestCase):
    def _executor(self):
        return AOPExecutor(operator_registry={}, rdf_graph=rdflib.Graph())

    def test_resolves_semantic_alias_to_category_column(self):
        executor = self._executor()
        dag = nx.DiGraph()
        dag.add_node("Q0", outputs=[{"name": "profile_category_id"}])
        dag.add_node(
            "Q1",
            inputs=[{"name": "all_category_id", "source": "Q0.profile_category_id", "type": "entity_id[]"}],
        )
        dag.add_edge("Q0", "Q1", field="all_category_id", source_field="profile_category_id", type="entity_id[]")
        cache = {
            "Q0": {
                "status": "success",
                "data": [
                    {"investorId": "INV-1", "category": "Equity"},
                    {"investorId": "INV-2", "category": "Debt"},
                ],
            }
        }
        bound = executor._resolve_bound_inputs("Q1", dag, cache)
        self.assertEqual(bound["all_category_id"], ["Equity", "Debt"])

    def test_prefers_exact_identifier_match_when_available(self):
        executor = self._executor()
        dag = nx.DiGraph()
        dag.add_node("Q0", outputs=[{"name": "investor_id"}])
        dag.add_node(
            "Q1",
            inputs=[{"name": "investor_id", "source": "Q0.investor_id", "type": "entity_id[]"}],
        )
        dag.add_edge("Q0", "Q1", field="investor_id", source_field="investor_id", type="entity_id[]")
        cache = {
            "Q0": {
                "status": "success",
                "data": [
                    {"investorId": "INV-1", "investorName": "A"},
                    {"investorId": "INV-2", "investorName": "B"},
                ],
            }
        }
        bound = executor._resolve_bound_inputs("Q1", dag, cache)
        self.assertEqual(bound["investor_id"], ["INV-1", "INV-2"])


if __name__ == "__main__":
    unittest.main()
