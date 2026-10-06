"""Regression cases for observed false raw-retrieval rejection gates."""
import copy
import unittest
import sqlite3
import tempfile
from pathlib import Path

from support import FakeClient, load


class RetrievalNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.module = load("llm_operators.query_spec")
        self.schema = {"Allocation": {"columns": ["id", "sector", "pct", "rdfs_label"], "subject_field": "id"}}
        self.spec = {"branch_id": "q1", "retrieval_specs": [{"class": "Allocation", "fields": ["id", "sector", "pct"],
                      "filters": [{"field": "sector", "operator": "=", "value": "Exact Category"},
                                  {"field": "pct", "operator": ">", "value": 30}]}]}
        self.requirements = {"answer_requirements": {"predicates": [
            {"id": "p1", "source_class": "Allocation", "branch_ids": ["q1"], "field": "Allocation.sector", "operator": "=", "value": "Exact Category"},
            {"id": "p2", "source_class": "Allocation", "branch_ids": ["q1"], "field": "Allocation.pct", "operator": ">", "value": 30},
        ]}}

    def test_qualified_expected_fields_match_local_filters(self):
        self.assertEqual([], self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_qualified_retrieval_fields_normalize_only_known_active_class(self):
        spec = {"retrieval_specs": [{"class": "Allocation", "fields": ["Allocation.id", "Allocation.pct", "Other.pct", "Allocation.unknown"],
                "entity_key": ["Allocation.id"], "filters": [{"field": "Allocation.pct", "operator": ">", "value": 30}]}]}
        self.module._normalize_rdf_fields(spec, self.schema)
        self.assertEqual(["id", "pct", "Other.pct", "Allocation.unknown"], spec["retrieval_specs"][0]["fields"])
        self.assertEqual("pct", spec["retrieval_specs"][0]["filters"][0]["field"])

    def test_changed_literal_still_rejected(self):
        self.spec["retrieval_specs"][0]["filters"][0]["value"] = "Exact"
        self.assertTrue(self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_wrong_other_class_qualifier_is_not_equated(self):
        self.requirements["answer_requirements"]["predicates"][0]["field"] = "Other.sector"
        self.assertTrue(self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_other_branch_predicate_does_not_apply(self):
        self.requirements["answer_requirements"]["predicates"][0]["branch_ids"] = ["q2"]
        self.spec["retrieval_specs"][0]["filters"].pop(0)
        self.assertEqual([], self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_null_operator_aliases_are_unary_but_string_null_is_literal(self):
        self.spec["retrieval_specs"][0]["filters"] = [{"field": "pct", "operator": "!=", "value": None}]
        self.requirements["answer_requirements"]["predicates"] = [{"source_class": "Allocation", "field": "pct", "operator": "is_not_null"}]
        self.assertEqual([], self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))
        self.spec["retrieval_specs"][0]["filters"][0]["value"] = "null"
        self.assertTrue(self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_final_display_notes_are_not_raw_branch_requirements(self):
        self.requirements["answer_requirements"].update(required_projection=["rdfs_label"], group_by=["rdfs_label"], preserve_null_groups=True)
        self.assertEqual([], self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))

    def test_explicit_source_join_key_remains_required(self):
        self.requirements["answer_requirements"]["joins"] = [{"left_branch": "q1", "left_field": "Allocation.rdfs_label"}]
        self.assertIn("Query_Spec omits required join key: rdfs_label", self.module._answer_requirement_errors(self.spec, self.requirements, self.schema))


class DeterministicPreScanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.database = Path(tmp.name) / "facts.db"
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE Fact (id INTEGER, name TEXT, date TEXT)')
        db.close()
        self.schema = load("sqlite_backend").load_sqlite_schema(self.database)

    def check(self, sql=None, fields=None, filters=None, **extra):
        client = FakeClient({"is_valid": False, "reason": "A model critic must not be called"})
        retrieval = {"class": "Fact", "fields": fields or ["id"], "entity_key": ["id"],
                     "optional_fields": [f for f in (fields or []) if f != "id"], "filters": filters or []}
        if sql is None:
            sql = load("raw_sql").render_raw_sql(retrieval, self.schema)
        inputs = {"sparql": sql, "retrieval_spec": retrieval, "global_schema": self.schema,
                  "sqlite_db_path": str(self.database), **extra}
        result = load("llm_operators.pre_scan_validate").semantic_pre_scan_validate(inputs, client)["pre_scan_validation"]
        self.assertEqual([], client.calls)
        return result

    def test_optional_explicit_nonnull_and_date_filter_passes(self):
        self.assertTrue(self.check(fields=["id", "date"], filters=[
            {"field": "date", "operator": "is_not_null"},
            {"field": "date", "operator": ">=", "value": "2025-01-01", "value_type": "date"},
        ])["is_valid"])

    def test_other_required_classes_do_not_reject_active_branch(self):
        self.assertTrue(self.check(query_spec={"required_classes": ["MissingOtherBranch"]})["is_valid"])

    def test_missing_selected_field_rejected(self):
        result = self.check('SELECT "id" AS "id" FROM "Fact"', ["id", "name"])
        self.assertFalse(result["is_valid"])
        self.assertIn("retrieval contract", result["reason"])

    def test_exact_projection_alias_accepted(self):
        self.assertTrue(self.check('SELECT "id" AS "id" FROM "Fact"')["is_valid"])

    def test_star_rejected_for_explicit_retrieval_contract(self):
        self.assertFalse(self.check('SELECT * FROM "Fact"')["is_valid"])

    def test_invalid_or_nonselect_queries_rejected(self):
        for query in ("", "SELECT WHERE", "DELETE FROM Fact", "PRAGMA query_only=OFF"):
            with self.subTest(query=query):
                self.assertFalse(self.check(query)["is_valid"])

    def test_unresolved_source_contract_rejected(self):
        result = self.check(query_spec={"contract_errors": ["required predicate omitted"]})
        self.assertFalse(result["is_valid"])
        self.assertEqual("Query_Spec", result["repair_stage"])


if __name__ == "__main__":
    unittest.main()
