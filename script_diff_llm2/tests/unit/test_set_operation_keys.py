"""Deterministic set operations must meet on a shared key space.

Cross-backend DAGs routinely produce the same identifier in different shapes:
a KG node binds `?investor` to a full IRI while a SQL node returns `investor_id`
as a bare literal. These tests pin that the set operators stay deterministic and
still intersect correctly across those shapes.
"""
import unittest

import networkx as nx

from script_diff_llm.pipeline.dag.executor import AOPExecutor


def _executor():
    return AOPExecutor(operator_registry={}, rdf_graph=None)


def _dag(edges_meta=None):
    dag = nx.DiGraph()
    for node_id in ("Q1", "Q2", "M1"):
        dag.add_node(node_id, id=node_id, operator="Subquery", outputs=[])
    dag.nodes["M1"]["operator"] = "Set_Intersect"
    for source in ("Q1", "Q2"):
        dag.add_edge(source, "M1", **((edges_meta or {}).get(source, {})))
    return dag


class SetOperationKeyAlignmentTest(unittest.TestCase):
    def test_iri_and_literal_ids_intersect(self):
        dag = _dag()
        pred_results = [
            ("Q1", {"data": [{"investorId": "INV-415"}, {"investorId": "INV-238"}, {"investorId": "INV-999"}]}),
            ("Q2", {"data": [
                {"investor": "https://wealth.example.org/kg/investor/INV-415"},
                {"investor": "https://wealth.example.org/kg/investor/INV-238"},
            ]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Intersect", pred_results, dag)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)

    def test_realignment_picks_a_shared_identifier_column(self):
        """Declared output fields can disagree; a shared id column still exists."""
        dag = _dag(edges_meta={
            "Q1": {"source_field": "investorName"},
            "Q2": {"source_field": "investor"},
        })
        pred_results = [
            ("Q1", {"data": [
                {"investorName": "Kavita Kulkarni", "investorId": "INV-415"},
                {"investorName": "Ravi Nair", "investorId": "INV-238"},
            ]}),
            ("Q2", {"data": [
                {"investor": "https://wealth.example.org/kg/investor/INV-415", "label": "K. Kulkarni"},
            ]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Intersect", pred_results, dag)
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["trace"].get("key_realignment", ""), (
            "re-keyed predecessors on a shared identifier column to avoid an empty result"
        ))

    def test_genuinely_disjoint_sets_stay_empty(self):
        """Realignment must not manufacture overlap that is not there."""
        dag = _dag()
        pred_results = [
            ("Q1", {"data": [{"investorId": "INV-001"}, {"investorId": "INV-002"}]}),
            ("Q2", {"data": [{"investorId": "INV-777"}, {"investorId": "INV-888"}]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Intersect", pred_results, dag)
        self.assertEqual(result["data"], [])

    def test_union_is_unaffected_by_realignment(self):
        dag = _dag()
        pred_results = [
            ("Q1", {"data": [{"investorId": "INV-001"}]}),
            ("Q2", {"data": [{"investorId": "INV-002"}]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Union", pred_results, dag)
        self.assertEqual(len(result["data"]), 2)

    def test_set_difference_removes_iri_shaped_matches(self):
        dag = _dag()
        pred_results = [
            ("Q1", {"data": [{"investorId": "INV-001"}, {"investorId": "INV-002"}]}),
            ("Q2", {"data": [{"investor": "https://wealth.example.org/kg/investor/INV-001"}]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Difference", pred_results, dag)
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["investorId"], "INV-002")

    def test_empty_predecessor_does_not_crash(self):
        dag = _dag()
        pred_results = [("Q1", {"data": []}), ("Q2", {"data": [{"investorId": "INV-001"}]})]
        result = _executor()._run_set_operation("M1", "Set_Intersect", pred_results, dag)
        self.assertEqual(result["data"], [])

    def test_identifier_column_wins_over_a_wider_incidental_overlap(self):
        """A low-cardinality shared column must not outrank the real entity id."""
        dag = _dag(edges_meta={"Q1": {"source_field": "declared_but_absent"}})
        pred_results = [
            ("Q1", {"data": [
                {"investorId": "INV-001", "sector": "Tech"},
                {"investorId": "INV-002", "sector": "Tech"},
            ]}),
            ("Q2", {"data": [
                {"investorId": "INV-001", "sector": "Tech"},
                {"investorId": "INV-777", "sector": "Tech"},
            ]}),
        ]
        result = _executor()._run_set_operation("M1", "Set_Intersect", pred_results, dag)
        self.assertEqual([row["investorId"] for row in result["data"]], ["INV-001"])
