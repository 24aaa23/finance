"""Regression checks use an unrelated schema and no benchmark answers."""
import sqlite3
import unittest

from script_diff_llm.backends.kg import validate_sparql_terms
from script_diff_llm.pipeline.dag.planner import build_subquery_dag
from script_diff_llm.pipeline.semantic_contract import normalize_semantic_result
from script_diff_llm.pipeline.specification import cleanup_query_spec


class GenericPipelineRepairsTest(unittest.TestCase):
    def test_filtered_aggregation_keeps_null_group_from_sql(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE devices (id INTEGER, region TEXT, active INTEGER)")
        conn.executemany("INSERT INTO devices VALUES (?, ?, ?)", [
            (1, None, 1), (2, "west", 1), (3, "west", 0),
        ])
        rows = [dict(row) for row in conn.execute(
            "SELECT region, COUNT(DISTINCT id) AS device_count FROM devices "
            "WHERE active = 1 GROUP BY region"
        )]
        spec = cleanup_query_spec({
            "query_type": "aggregation", "entity_key": "id",
            "execution_strategy": "single_sql",
            "group_by": [{"output_name": "region", "field": "region", "source_class": "devices"}],
            "filters": [{"field": "active", "operator": "=", "value": 1}],
            "measures": [{"output_name": "device_count", "field": "id",
                          "final_operation": "COUNT", "requires_distinct": True}],
            "output_schema": ["region", "device_count"],
        }, "For each region, how many active devices are there?", ["devices"],
            lambda value: str(value).lower(), schema_kind="sql")
        actual = normalize_semantic_result("For each region, how many active devices are there?", spec, rows)
        self.assertEqual({row["region"]: row["device_count"] for row in actual}, {None: 1, "west": 1})
        self.assertTrue(spec["measures"][0]["requires_distinct"])
        self.assertEqual(spec["execution_strategy"], "single_sql")

    def test_missing_null_policy_does_not_delete_rows(self):
        rows = [{"region": None, "n": 2}, {"region": "west", "n": 3}]
        result = normalize_semantic_result("Counts by region", {
            "group_by": [{"output_name": "region"}],
        }, rows)
        self.assertEqual(len(result), 2)

    def test_explicit_null_exclusion_is_preserved(self):
        result = normalize_semantic_result("Counts by known region", {
            "group_by": [{"output_name": "region"}], "preserve_null_groups": False,
        }, [{"region": None}, {"region": "west"}])
        self.assertEqual([row["region"] for row in result], ["west"])

    def test_single_node_preserves_original_question(self):
        question = "Which reserved devices have a load above 75?"
        dag = build_subquery_dag(question, [{"id": "Q1", "operator": "Subquery",
            "backend": "SQL", "description": "Devices booked for a future date", "inputs": []}])
        self.assertEqual(dag.nodes["Q1"]["description"], question)

    def test_multi_node_local_scopes_remain_separate(self):
        nodes = [{"id": "Q1", "operator": "Subquery", "backend": "SQL", "description": "Active devices",
                  "outputs": [{"name": "device_id"}]},
                 {"id": "Q2", "operator": "Subquery", "backend": "KG", "description": "Connected devices",
                  "outputs": [{"name": "device_id"}]},
                 {"id": "Q3", "operator": "Set_Intersect", "inputs": [
                     {"name": "active", "source": "Q1.device_id"},
                     {"name": "connected", "source": "Q2.device_id"}]}]
        dag = build_subquery_dag("Active and connected devices", nodes)
        self.assertEqual(dag.nodes["Q1"]["description"], "Active devices")

    def test_rdf_namespaces_are_part_of_term_identity(self):
        known = {"https://devices.example/Device", "https://devices.example/serial"}
        wrong = "PREFIX d: <http://example.org/> SELECT ?id WHERE { ?s a d:Device; d:serial ?id }"
        self.assertFalse(validate_sparql_terms(wrong, known)["is_valid"])
        right = wrong.replace("http://example.org/", "https://devices.example/")
        self.assertTrue(validate_sparql_terms(right, known)["is_valid"])

    def test_legacy_local_name_cache_remains_compatible(self):
        query = "PREFIX d: <https://devices.example/> SELECT ?id WHERE { ?s a d:Device; d:serial ?id }"
        self.assertTrue(validate_sparql_terms(query, {"Device", "serial"})["is_valid"])


if __name__ == "__main__":
    unittest.main()
