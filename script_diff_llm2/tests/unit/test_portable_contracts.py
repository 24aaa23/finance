"""Behavioral checks on a synthetic schema that is unrelated to the benchmark."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from script_diff_llm.backends.sql import _deterministic_entity_group_sql, pre_programmed_scan_sql
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.dag.executor import AOPExecutor
from script_diff_llm.pipeline.specification import cleanup_query_spec
from script_diff_llm.pipeline.specification import semantic_build_query_spec
from script_diff_llm.pipeline.semantic_catalog import load_semantic_catalog, relevant_catalog_metrics


SCHEMA = {
    "customers": {"column_names": ["customer_id", "region", "active"]},
    "charges": {"column_names": ["customer_id", "amount", "charge_id"]},
}


def spec():
    return {
        "query_type": "comparative", "base_entity": "customers", "entity_key": "customer_id",
        "join_policy": "left_join", "execution_strategy": "preaggregate_sql",
        "grain": {"pre_aggregate_by": ["customer_id"], "final_group_by": ["region"]},
        "group_by": [{"source_class": "customers", "field": "region", "output_name": "region"}],
        "filters": [{"source_class": "customers", "field": "active", "operator": "=", "value": 1}],
        "measures": [{"source_class": "charges", "field": "amount", "output_name": "average_total",
                      "per_entity_operation": "SUM", "final_operation": "AVG"}],
        "output_schema": ["region", "average_total"],
        "requirements": [
            {"text": "active", "implemented_by": ["filters.0"]},
            {"text": "region", "implemented_by": ["group_by.0"]},
            {"text": "average total", "implemented_by": ["measures.0"]},
        ],
    }


QUESTION = "For each region, what is the average total charge of active customers?"


class PortableContractsTest(unittest.TestCase):
    def test_source_catalog_is_schema_validated_and_query_scoped(self):
        import json
        catalog = {"version": "source-v1", "identity_bindings": [
            {"kg_uri_prefix": "https://source.example/id/customer/", "sql_source": "customers",
             "sql_field": "customer_id", "provenance": "source owner ID mapping v1"},
        ], "metrics": [
            {"id": "average-charge", "backend": "sql", "source": "charges",
             "fields": ["amount"], "terms": ["average total charge"],
             "definition": "Mean of per-customer charge totals", "formula": "SUM(amount) per customer, then AVG",
             "unit": "currency", "provenance": "source owner metric guide v1"},
            {"id": "unrelated", "backend": "sql", "source": "charges",
             "fields": ["amount"], "terms": ["unrelated score"],
             "definition": "Different source metric", "provenance": "source owner metric guide v1"},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog))
            loaded = load_semantic_catalog(str(path), SCHEMA, {})
            self.assertEqual(len(loaded["identity_bindings"]), 1)
            selected = relevant_catalog_metrics(loaded, QUESTION, "sql", SCHEMA)
            self.assertEqual([entry["id"] for entry in selected], ["average-charge"])
            catalog["metrics"][0]["fields"] = ["reference_answer"]
            path.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError):
                load_semantic_catalog(str(path), SCHEMA, {})

    def test_cross_backend_ids_need_declared_namespace_mapping(self):
        import networkx as nx
        uri = "https://source.example/id/customer/C-003"
        registry = {"Scan": lambda _: {"status": "success", "data": [{"customer_id": uri}]}}
        unmapped = AOPExecutor(registry, rdf_graph=None)
        mapped = AOPExecutor(registry, rdf_graph=None, identity_bindings=[
            {"kg_uri_prefix": "https://source.example/id/customer/"},
        ])
        self.assertEqual(unmapped._kg_scan({})["data"][0]["customer_id"], uri)
        self.assertEqual(mapped._kg_scan({})["data"][0]["customer_id"], "C-003")

        dag = nx.DiGraph()
        dag.add_node("Q1", outputs=[{"name": "customer_id"}])
        dag.add_node("Q2", outputs=[{"name": "account_id"}])
        dag.add_node("M1", outputs=[])
        dag.add_edge("Q1", "M1", source_field="customer_id")
        dag.add_edge("Q2", "M1", source_field="account_id")
        rows = [("Q1", {"data": [{"customer_id": "C-003", "region": "east"}]}),
                ("Q2", {"data": [{"account_id": "A-9", "region": "east"}]})]
        result = unmapped._run_set_operation("M1", "Set_Intersect", rows, dag)
        self.assertEqual(result["data"], [])

    def test_compiled_entity_grain_uses_independent_eligible_population(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "synthetic.db"
            with sqlite3.connect(db) as conn:
                conn.executescript("CREATE TABLE customers(customer_id INTEGER, region TEXT, active INTEGER);"
                                   "CREATE TABLE charges(customer_id INTEGER, amount REAL, charge_id INTEGER);")
                conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", [
                    (1, None, 1), (2, None, 1), (3, "east", 1), (4, "east", 0)])
                conn.executemany("INSERT INTO charges VALUES (?, ?, ?)", [
                    (1, 10, 1), (1, 20, 2), (2, 50, 3), (4, 1000, 4)])
            plan = spec()
            self.assertEqual(validate_query_spec(plan, SCHEMA, QUESTION), [])
            sql = _deterministic_entity_group_sql({"query_spec": plan, "sql_schema": SCHEMA})
            result = pre_programmed_scan_sql({"sql": sql}, str(db))
            self.assertEqual(result["status"], "success")
            self.assertEqual({row["region"]: row["average_total"] for row in result["data"]},
                             {None: 40.0, "east": None})
            # The scan must not be able to mutate a source database.
            rejected = pre_programmed_scan_sql({"sql": "DELETE FROM customers"}, str(db))
            self.assertEqual(rejected["status"], "error")
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 4)

    def test_zero_event_counts_are_explicit_not_global_coalesce(self):
        plan = spec()
        plan["measures"] = [{"source_class": "charges", "field": "charge_id", "output_name": "avg_count",
                             "per_entity_operation": "COUNT", "final_operation": "AVG",
                             "missing_entity_value": 0}]
        plan["output_schema"] = ["region", "avg_count"]
        sql = _deterministic_entity_group_sql({"query_spec": plan, "sql_schema": SCHEMA})
        self.assertIn('AVG(COALESCE(metric_source_0."avg_count", 0))', sql)
        plan["measures"][0].pop("missing_entity_value")
        sql = _deterministic_entity_group_sql({"query_spec": plan, "sql_schema": SCHEMA})
        self.assertNotIn("COALESCE", sql)

    def test_cleanup_does_not_invent_definition_from_metric_name(self):
        plan = spec()
        plan["measures"][0].update({"output_name": "average_profit", "field": "amount",
                                     "formula": None, "per_entity_operation": "AVG"})
        cleaned = cleanup_query_spec(plan, QUESTION, ["customers", "charges"], str.lower, schema_kind="sql")
        self.assertIsNone(cleaned["measures"][0]["formula"])
        self.assertEqual(cleaned["measures"][0]["per_entity_operation"], "AVG")

    def test_misassigned_filter_literal_and_unknown_field_are_rejected(self):
        plan = spec()
        plan["filters"][0] = {"source_class": "customers", "field": "region", "operator": "=", "value": "west"}
        self.assertTrue(any("not supported" in error for error in validate_query_spec(plan, SCHEMA, QUESTION)))
        plan = spec()
        plan["measures"][0]["field"] = "made_up_metric"
        self.assertTrue(any("made_up_metric" in error for error in validate_query_spec(plan, SCHEMA, QUESTION)))

    def test_uncovered_plan_item_is_rejected(self):
        plan = spec()
        plan["requirements"] = plan["requirements"][:-1]
        self.assertIn("measures.0 has no quoted requirement.", validate_query_spec(plan, SCHEMA, QUESTION))

    def test_missing_ledger_is_visible_but_schema_errors_still_block(self):
        plan = spec()
        plan.pop("requirements")
        blocking, warnings = split_contract_errors(validate_query_spec(plan, SCHEMA, QUESTION))
        self.assertEqual(blocking, [])
        self.assertIn("Every subquery needs a requirement ledger.", warnings)
        plan["measures"][0]["field"] = "invented_amount"
        blocking, _ = split_contract_errors(validate_query_spec(plan, SCHEMA, QUESTION))
        self.assertTrue(any("invented_amount" in error for error in blocking))

    def test_logical_base_binds_only_to_unique_physical_source(self):
        plan = spec()
        plan["base_entity"] = "customer"
        plan["measures"] = [{"source_class": "customers", "field": "customer_id",
                             "output_name": "customer_id", "per_entity_operation": None,
                             "final_operation": None}]
        plan["output_schema"] = ["region", "customer_id"]
        plan["required_classes"] = ["customer", "customers"]
        plan["requirements"][-1] = {"text": "customer", "implemented_by": ["measures.0"]}
        cleaned = cleanup_query_spec(plan, QUESTION, list(SCHEMA), str.lower,
                                     schema_kind="sql", schema=SCHEMA)
        self.assertEqual(cleaned["base_entity"], "customers")
        self.assertNotIn("customer", cleaned["required_classes"])
        self.assertEqual(validate_query_spec(cleaned, SCHEMA, QUESTION), [])

        ambiguous_schema = SCHEMA
        ambiguous = copy.deepcopy(plan)
        ambiguous["group_by"] = []
        ambiguous["filters"] = [{"source_class": "charges", "field": "amount", "operator": ">", "value": 0}]
        ambiguous["output_schema"] = ["customer_id"]
        ambiguous["requirements"] = [{"text": "customer", "implemented_by": ["measures.0"]}]
        # Explicit key projections from different owners remain ambiguous.
        ambiguous['measures'].append({'source_class': 'charges', 'field': 'customer_id',
                                      'output_name': 'charge_customer_id'})
        cleaned = cleanup_query_spec(ambiguous, QUESTION, list(SCHEMA), str.lower,
                                     schema_kind="sql", schema=ambiguous_schema)
        self.assertEqual(cleaned["base_entity"], "customer")

    def test_requirement_paraphrase_keeps_literals_but_rejects_inventions(self):
        plan = spec()
        plan["requirements"][0]["text"] = "filter active customers"
        self.assertEqual(validate_query_spec(plan, SCHEMA, QUESTION), [])
        plan["requirements"][0]["text"] = "filter political affiliation of active customers"
        self.assertTrue(any("unsupported terms" in error for error in validate_query_spec(plan, SCHEMA, QUESTION)))

    def test_point_lookup_projection_can_be_verified_lexically(self):
        plan = spec()
        plan["query_type"] = "point_lookup"
        plan["measures"] = [{"source_class": "customers", "field": "customer_id",
                             "output_name": "customer_id", "per_entity_operation": None,
                             "final_operation": None}]
        plan["output_schema"] = ["region", "customer_id"]
        plan["requirements"] = plan["requirements"][:-1]
        self.assertEqual(validate_query_spec(plan, SCHEMA, "Which customer_id is active in each region?"), [])

    def test_contract_repair_accepts_grounded_plan(self):
        import json
        from types import SimpleNamespace

        incomplete = spec()
        incomplete["measures"][0]["field"] = "unknown_charge"
        repaired = spec()
        responses = [incomplete, repaired]
        calls = []

        def create(**request):
            calls.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(responses.pop(0))))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec(
            {"query": QUESTION, "root_query": QUESTION, "schema_kind": "sql",
             "global_schema": SCHEMA, "retrieved_tables": list(SCHEMA),
             "semantic_catalog": {"metrics": [
                 {"id": "charge-definition", "backend": "sql", "source": "charges",
                  "terms": ["average total charge"], "definition": "per-customer total"},
                 {"id": "unrelated-definition", "backend": "sql", "source": "charges",
                  "terms": ["unrelated score"], "definition": "should not enter this prompt"},
             ]}},
            client, "fake-model", parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None,
        )
        self.assertEqual(len(calls), 2)
        self.assertIn("charge-definition", calls[0]["messages"][0]["content"])
        self.assertNotIn("unrelated-definition", calls[0]["messages"][0]["content"])
        self.assertEqual(result["query_spec"]["contract_errors"], [])

    def test_nested_json_fragment_triggers_complete_plan_retry(self):
        import json
        from types import SimpleNamespace

        responses = [{"text": "active", "implemented_by": ["filters.0"]}, spec()]
        calls = []

        def create(**request):
            calls.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(responses.pop(0))))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = semantic_build_query_spec(
            {"query": QUESTION, "root_query": QUESTION, "schema_kind": "sql",
             "global_schema": SCHEMA, "retrieved_tables": list(SCHEMA)},
            client, "fake-model", parse_json_fn=lambda text, default, _: json.loads(text),
            normalize_for_compare_fn=str.lower, log_call_fn=lambda *_: None,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["query_spec"]["base_entity"], "customers")
        self.assertEqual(result["query_spec"]["contract_errors"], [])

    def test_unresolved_definition_stops_before_generation(self):
        plan = spec()
        plan["unresolved_requirements"] = ["average total has no defined population"]
        called = []
        registry = {"Query_Spec": lambda _: {"query_spec": plan},
                    "Generate": lambda _: called.append("called")}
        executor = AOPExecutor(registry, rdf_graph=None, sql_schema=SCHEMA, db_path="unused")
        result = executor._run_sql_subquery("Q1", QUESTION, QUESTION, {}, {})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["trace"]["failure_stage"], "Query_Spec_Contract")
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
