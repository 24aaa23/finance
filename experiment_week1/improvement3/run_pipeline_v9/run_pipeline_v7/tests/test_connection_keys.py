"""Shared declarations survive independent model-generated retrievals."""
import copy
import unittest

from support import FakeClient, load


class ConnectionKeyTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "Record": {"subject_field": "subject", "columns": [
                {"name": "subject", "datatype": "resource_iri"},
                {"name": "owner", "datatype": "object_reference (points to: Person)"},
                {"name": "amount", "datatype": "numeric"},
                {"name": "tenant", "datatype": "categorical_string"}]},
            "Person": {"subject_field": "subject", "columns": [
                {"name": "subject", "datatype": "resource_iri"},
                {"name": "name", "datatype": "categorical_string"},
                {"name": "tenant", "datatype": "categorical_string"}]},
        }
        self.decomposition = {"subquestions": [
            {"id": "facts", "source_class": "Record"},
            {"id": "people", "source_class": "Person"}],
            "answer_requirements": {"joins": [{"left_branch": "facts", "right_branch": "people",
                "left_on": ["owner"], "right_on": ["subject"]}]}}

    def build(self, branch, fields):
        source = next(item["source_class"] for item in self.decomposition["subquestions"] if item["id"] == branch)
        return load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "retrieve the raw records", "original_query": "Compare totals by person",
            "subquestion": {"id": branch, "source_class": source},
            "decomposition": self.decomposition, "global_schema": self.schema,
        }, FakeClient({"id": branch, "retrieval_specs": [{"class": source,
            "fields": fields, "optional_fields": list(fields), "filters": []}]}))["query_spec"]

    def test_both_independent_branches_retain_connection_and_subject(self):
        before = copy.deepcopy(self.decomposition)
        left, right = self.build("facts", ["amount"]), self.build("people", ["name"])
        self.assertFalse(left["contract_errors"])
        self.assertFalse(right["contract_errors"])
        a, b = left["retrieval_specs"][0], right["retrieval_specs"][0]
        self.assertIn("owner", a["fields"])
        self.assertIn("subject", a["fields"])
        self.assertIn("subject", b["fields"])
        self.assertIn("owner", a["optional_fields"])
        self.assertEqual(a["fields"], left["output_schema"])
        self.assertEqual(before, self.decomposition)

    def test_composite_keys_are_all_retained(self):
        join = self.decomposition["answer_requirements"]["joins"][0]
        join["left_on"] = ["Record.owner", "Record.tenant"]
        join["right_on"] = ["Person.subject", "Person.tenant"]
        for branch, fields in [("facts", ["amount"]), ("people", ["name"])]:
            spec = self.build(branch, fields)
            self.assertFalse(spec["contract_errors"])
            self.assertIn("tenant", spec["retrieval_specs"][0]["fields"])

    def test_unknown_key_is_not_silently_ignored(self):
        self.decomposition["answer_requirements"]["joins"][0]["left_on"] = ["invented"]
        spec = self.build("facts", ["amount"])
        self.assertTrue(any("unknown branch/source/key" in error for error in spec["contract_errors"]))
        self.assertNotIn("invented", spec["retrieval_specs"][0]["fields"])

    def test_different_subject_types_are_not_valid_shared_ids(self):
        self.decomposition["answer_requirements"]["joins"][0]["left_on"] = ["subject"]
        self.assertTrue(any("different entity classes" in error for error in self.build("facts", ["amount"])["contract_errors"]))

    def test_resource_to_literal_connection_is_rejected(self):
        self.decomposition["answer_requirements"]["joins"][0]["right_on"] = ["name"]
        self.assertTrue(any("literal field" in error for error in self.build("facts", ["amount"])["contract_errors"]))

    def test_no_declared_join_does_not_invent_one(self):
        self.decomposition["answer_requirements"]["joins"] = []
        spec = self.build("facts", ["amount"])
        self.assertFalse(spec["contract_errors"])
        self.assertNotIn("owner", spec["retrieval_specs"][0]["fields"])


if __name__ == "__main__":
    unittest.main()
