import concurrent.futures
import json
import os
import re
import threading
import time
from typing import Any

import networkx as nx
import rdflib

from script_diff_llm.backends import sql as sql_pipeline
from script_diff_llm.pipeline.semantic_contract import (
    normalize_semantic_result,
    normalize_result_iris,
    set_operation_key,
    should_validate_semantics,
    validate_aggregation_shape,
    validate_semantic_result,
)


class AOPExecutor:
    """
    Executes the generated subquery DAG topologically.
    Each node in the DAG may be a Subquery (SQL or KG backend) or a Set operator.
    Manages data binding between nodes and per-node self-healing loops.
    """

    def __init__(
        self,
        operator_registry: dict[str, Any],
        rdf_graph: rdflib.Graph,
        llm_client: Any = None,
        kg_metadata: dict[str, Any] | None = None,
        db_path: str = ":memory:",
        sql_schema: dict[str, Any] | None = None,
        pre_scan_validate_max_retries: int = 3,
        post_scan_validate_max_retries: int = 3,
        scan_refine_max_retries: int = 3,
    ):
        self.registry = operator_registry
        self.rdf_graph = rdf_graph
        self.llm_client = llm_client
        self.kg_metadata = kg_metadata or {}
        self.db_path = db_path
        self.sql_schema = sql_schema or {}
        self.pre_scan_validate_max_retries = pre_scan_validate_max_retries
        self.post_scan_validate_max_retries = post_scan_validate_max_retries
        self.scan_refine_max_retries = scan_refine_max_retries

    def _json_safe(self, value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    def _row_count(self, result: Any) -> int:
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            return len(result.get("data") or [])
        return 0

    def _build_execution_levels(self, dag: nx.DiGraph) -> list[list[str]]:
        in_degree = {node_id: dag.in_degree(node_id) for node_id in dag.nodes}
        ready = sorted([node_id for node_id, degree in in_degree.items() if degree == 0])
        levels = []
        while ready:
            levels.append(ready)
            next_ready = []
            for node_id in ready:
                for successor in dag.successors(node_id):
                    in_degree[successor] -= 1
                    if in_degree[successor] == 0:
                        next_ready.append(successor)
            ready = sorted(next_ready)
        if sum(len(level) for level in levels) != dag.number_of_nodes():
            raise ValueError("Cannot execute subquery DAG because it contains a cycle.")
        return levels

    def _planned_node_trace(self, node_id: str, dag: nx.DiGraph) -> dict[str, Any]:
        node_data = dag.nodes[node_id]
        dependencies = []
        for pred in dag.predecessors(node_id):
            edge_data = dag.get_edge_data(pred, node_id, default={}) or {}
            dependencies.append({
                "source": pred,
                "target": node_id,
                "field": edge_data.get("field", ""),
                "source_field": edge_data.get("source_field", ""),
                "type": edge_data.get("type", ""),
            })
        return {
            "node_id": node_id,
            "description": node_data.get("description", ""),
            "operator": node_data.get("operator", "Subquery"),
            "backend": node_data.get("backend", ""),
            "declared_inputs": self._json_safe(node_data.get("inputs", [])),
            "declared_outputs": self._json_safe(node_data.get("outputs", [])),
            "dependencies": dependencies,
        }

    def _log_dag_plan(self, dag: nx.DiGraph, execution_levels: list[list[str]]) -> None:
        print("[DAG] Generated subqueries and dependencies:")
        for level_index, level in enumerate(execution_levels, 1):
            print(f"[DAG] Level {level_index}: {level}")
            for node_id in level:
                node_data = dag.nodes[node_id]
                preds = list(dag.predecessors(node_id))
                print(
                    f"   [DAG] {node_id}: op={node_data.get('operator', 'Subquery')} "
                    f"backend={node_data.get('backend', '')} deps={preds} "
                    f"inputs={node_data.get('inputs', [])} outputs={node_data.get('outputs', [])} "
                    f"subquery={node_data.get('description', '')}"
                )

    @staticmethod
    def _normalize_bound_field_name(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    @classmethod
    def _field_tokens(cls, value: Any) -> list[str]:
        text = str(value or "")
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
        tokens = [token.lower() for token in re.split(r"[^a-zA-Z0-9]+", text) if token]
        normalized = []
        for token in tokens:
            if token.endswith("ids"):
                token = token[:-1]
            normalized.append(token)
        return normalized

    @classmethod
    def _best_matching_row_key(cls, source_field: str, rows: list[dict[str, Any]]) -> str | None:
        if not rows or not isinstance(rows[0], dict):
            return None
        row_keys = [str(key) for key in rows[0].keys()]
        if source_field in row_keys:
            return source_field

        source_norm = cls._normalize_bound_field_name(source_field)
        source_tokens = cls._field_tokens(source_field)
        source_token_set = set(source_tokens)
        if not source_norm or not source_token_set:
            return None

        best_key = None
        best_score = 0
        for row_key in row_keys:
            row_norm = cls._normalize_bound_field_name(row_key)
            row_tokens = cls._field_tokens(row_key)
            row_token_set = set(row_tokens)
            score = 0
            if row_norm == source_norm:
                score = 100
            elif row_token_set == source_token_set:
                score = 90
            elif row_token_set and row_token_set <= source_token_set:
                score = 70 + len(row_token_set)
            elif source_token_set and source_token_set <= row_token_set:
                score = 60 + len(source_token_set)
            elif source_tokens and row_tokens and source_tokens[-1] == row_tokens[-1]:
                overlap = len(source_token_set & row_token_set)
                if overlap:
                    score = 50 + overlap
            if score > best_score:
                best_key = row_key
                best_score = score
        return best_key if best_score >= 71 else None

    def _resolve_bound_inputs(self, node_id: str, dag: nx.DiGraph, results_cache: dict[str, Any]) -> dict[str, Any]:
        node_data = dag.nodes[node_id]
        declared_inputs = node_data.get("inputs", [])
        bound = {}
        for inp in declared_inputs:
            source = inp.get("source", "")
            if "." not in source:
                continue
            src_node, src_field = source.split(".", 1)
            upstream_result = results_cache.get(src_node, {})
            if isinstance(upstream_result, dict):
                value = upstream_result.get(src_field)
                if value is None and isinstance(upstream_result.get("data"), list):
                    resolved_field = self._best_matching_row_key(src_field, upstream_result["data"]) or src_field
                    col_vals = [r.get(resolved_field) for r in upstream_result["data"] if resolved_field in r]
                    value = col_vals if col_vals else None
                if value is not None:
                    bound[inp["name"]] = value
        return bound

    def _output_key_for_predecessor(self, dag: nx.DiGraph, pred: str, node_id: str, rows: list[dict]) -> str:
        edge_data = dag.get_edge_data(pred, node_id, default={}) or {}
        row_keys = set(rows[0].keys()) if rows else set()
        if edge_data.get("source_field") and (not row_keys or edge_data["source_field"] in row_keys):
            return edge_data["source_field"]
        outputs = dag.nodes[pred].get("outputs", [])
        if outputs and isinstance(outputs[0], dict) and outputs[0].get("name") and (not row_keys or outputs[0]["name"] in row_keys):
            return outputs[0]["name"]
        if rows:
            preferred = ["investorId", "portfolioId", "holdingId", "goalId", "entity_id", "id"]
            for key in preferred:
                if key in rows[0]:
                    return key
            return list(rows[0].keys())[0]
        return "entity_id"

    def _kg_scan(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the KG Scan operator and normalize resource IRIs to local names.

        Fuseki binds resources as full IRIs, but the benchmark contract and the
        SQL backend both speak local identifiers. Normalizing at the scan
        boundary keeps KG rows shape-comparable with SQL rows and lets
        cross-backend set operations meet on the same key space.
        """
        scan_result = self.registry["Scan"](inputs)
        if isinstance(scan_result, dict) and isinstance(scan_result.get("data"), list):
            scan_result["data"] = normalize_result_iris(scan_result["data"])
        return scan_result

    def _run_kg_subquery(self, node_id: str, description: str, root_query: str, bound_inputs: dict[str, Any], trace: dict) -> dict[str, Any]:
        del trace
        print(f"   [KG] Running KG pipeline for node '{node_id}'...")
        node_trace = {
            "node_id": node_id,
            "retrieved_classes": [],
            "query_spec": {},
            "generated_sparql": "",
            "pre_scan_validation_is_valid": "",
            "pre_scan_validation_reason": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_error_type": "",
            "scan_raw_rows": "",
            "self_heal_attempts": 0,
            "failure_stage": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "bound_inputs": self._json_safe(bound_inputs),
            "attempts": [],
        }

        inputs = {"query": description, "root_query": root_query, "bound_inputs": bound_inputs, "global_schema": self.kg_metadata}
        retrieve_result = self.registry["Retrieve"](inputs)
        inputs.update(retrieve_result)
        node_trace["retrieved_classes"] = retrieve_result.get("retrieved_tables", [])

        qs_result = self.registry["Query_Spec"](inputs)
        inputs.update(qs_result)
        node_trace["query_spec"] = qs_result.get("query_spec", {})

        gen_result = self.registry["Generate"](inputs)
        inputs["sparql"] = gen_result.get("sparql", "")
        node_trace["generated_sparql"] = inputs["sparql"]
        node_trace["attempts"].append({"stage": "Generate", "attempt": 1, "output_present": bool(inputs["sparql"])})

        for attempt in range(1, self.pre_scan_validate_max_retries + 1):
            shape_check = validate_aggregation_shape(inputs.get("query_spec", {}), inputs.get("sparql", ""))
            if not shape_check.get("is_valid", True):
                check = shape_check
                node_trace["attempts"].append({
                    "stage": "Aggregation_Shape_Check",
                    "attempt": attempt,
                    "is_valid": False,
                    "severity": shape_check.get("severity", ""),
                    "reason": shape_check.get("reason", ""),
                })
            else:
                psv_result = self.registry["Pre_Scan_Validate"](inputs)
                check = psv_result.get("pre_scan_validation", {})
            is_valid = bool(check.get("is_valid", False))
            severity = str(check.get("severity", "repairable_warning")).lower()
            node_trace["pre_scan_validation_is_valid"] = is_valid
            node_trace["pre_scan_validation_reason"] = check.get("reason", "")
            node_trace["attempts"].append({
                "stage": "Pre_Scan_Validate",
                "attempt": attempt,
                "is_valid": is_valid,
                "severity": severity,
                "reason": check.get("reason", ""),
            })

            if is_valid or severity in {"valid", "acceptable_warning"}:
                break

            if attempt == self.pre_scan_validate_max_retries:
                if check is shape_check:
                    # An unmet fan-out contract is a quality warning, not a broken query.
                    node_trace["aggregation_shape_warning"] = check.get("reason", "")
                    break
                node_trace["failure_stage"] = "Pre_Scan_Validate"
                print(f"   [KG] Pre_Scan_Validate hard stop for node '{node_id}'.")
                return {"status": "error", "error_message": check.get("reason"), "data": [], "trace": node_trace}

            inputs["logic_feedback"] = json.dumps({
                "error_type": "pre_scan_validation_failed",
                "reason": check.get("reason"),
                "rewrite_hint": check.get("rewrite_hint", ""),
                "query_spec": inputs.get("query_spec", {}),
                "failed_sparql": inputs.get("sparql", ""),
            }, indent=2)
            node_trace["self_heal_attempts"] += 1
            gen_result = self.registry["Generate"](inputs)
            inputs["sparql"] = gen_result.get("sparql", "")
            node_trace["generated_sparql"] = inputs["sparql"]
            node_trace["attempts"].append({"stage": "Generate", "attempt": attempt + 1, "output_present": bool(inputs["sparql"])})

        scan_result = {}
        for attempt in range(1, self.scan_refine_max_retries + 1):
            scan_result = self._kg_scan(inputs)
            node_trace["attempts"].append({
                "stage": "Scan",
                "attempt": attempt,
                "status": scan_result.get("status", ""),
                "row_count": scan_result.get("row_count", 0),
                "error": scan_result.get("error_message", ""),
            })
            if scan_result.get("status") != "error":
                break
            if attempt == self.scan_refine_max_retries:
                node_trace["failure_stage"] = "Scan"
                node_trace["scan_status"] = "error"
                node_trace["scan_error"] = scan_result.get("error_message", "")
                print(f"   [KG] Scan failed after retries for node '{node_id}'.")
                return {"status": "error", "error_message": scan_result.get("error_message"), "data": [], "trace": node_trace}

            node_trace["self_heal_attempts"] += 1
            failed_sparql = scan_result.get("failed_sparql", inputs.get("sparql", ""))
            refine_inputs = {
                "failed_sparql": failed_sparql,
                "error_message": scan_result.get("error_message"),
                "logic_feedback": json.dumps({"unknown_terms": scan_result.get("unknown_terms", []), "error_type": "sparql_error"}, indent=2),
                "query": description,
                "root_query": root_query,
                "query_spec": inputs.get("query_spec", {}),
            }
            refine_result = self.registry["Refine"](refine_inputs)
            inputs["sparql"] = refine_result.get("sparql", failed_sparql)
            node_trace["generated_sparql"] = inputs["sparql"]

        original_successful_scan = scan_result
        if isinstance(scan_result, dict) and isinstance(scan_result.get("data"), list):
            scan_result["data"] = normalize_semantic_result(
                root_query,
                inputs.get("query_spec", {}),
                scan_result.get("data", []),
            )
            scan_result["row_count"] = len(scan_result.get("data", []))
        if not should_validate_semantics(inputs.get("query_spec", {})):
            node_trace["validation_is_valid"] = ""
            node_trace["validation_reason"] = ""
        for attempt in range(1, self.post_scan_validate_max_retries + 1):
            if not should_validate_semantics(inputs.get("query_spec", {})):
                break
            validation = validate_semantic_result(root_query, inputs.get("query_spec", {}), scan_result.get("data", []))
            is_valid = bool(validation.get("is_valid", False))
            severity = str(validation.get("severity", "repairable_warning")).lower()
            node_trace["validation_is_valid"] = is_valid
            node_trace["validation_reason"] = validation.get("reason", "")
            node_trace["attempts"].append({
                "stage": "Validate",
                "attempt": attempt,
                "is_valid": is_valid,
                "severity": severity,
                "reason": validation.get("reason", ""),
            })
            if is_valid or severity == "valid":
                break
            if attempt == self.post_scan_validate_max_retries:
                scan_result = original_successful_scan
                break

            node_trace["self_heal_attempts"] += 1
            failed_sparql = inputs.get("sparql", "")
            refine_inputs = {
                "failed_sparql": failed_sparql,
                "error_message": validation.get("reason", ""),
                "logic_feedback": json.dumps({
                    "error_type": "semantic_validation_failed",
                    "reason": validation.get("reason", ""),
                    "rewrite_hint": validation.get("rewrite_hint", ""),
                    "query_spec": inputs.get("query_spec", {}),
                    "result_sample": (scan_result.get("data", []) or [])[:10],
                }, indent=2),
                "query": description,
                "root_query": root_query,
                "query_spec": inputs.get("query_spec", {}),
            }
            refine_result = self.registry["Refine"](refine_inputs)
            inputs["sparql"] = refine_result.get("sparql", failed_sparql)
            node_trace["generated_sparql"] = inputs["sparql"]
            scan_result = self._kg_scan(inputs)
            node_trace["attempts"].append({
                "stage": "Scan",
                "attempt": self.scan_refine_max_retries + attempt,
                "status": scan_result.get("status", ""),
                "row_count": scan_result.get("row_count", 0),
                "error": scan_result.get("error_message", ""),
            })
            if scan_result.get("status") == "error":
                scan_result = original_successful_scan
                node_trace["attempts"].append({
                    "stage": "Validate_Fallback",
                    "attempt": attempt,
                    "reason": "semantic retry scan failed; retained original successful scan result",
                })
                break
            if isinstance(scan_result, dict) and isinstance(scan_result.get("data"), list):
                scan_result["data"] = normalize_semantic_result(
                    root_query,
                    inputs.get("query_spec", {}),
                    scan_result.get("data", []),
                )
                scan_result["row_count"] = len(scan_result.get("data", []))

        node_trace["scan_status"] = scan_result.get("status", "")
        node_trace["scan_row_count"] = scan_result.get("row_count", "")
        node_trace["scan_error"] = scan_result.get("error_message", "")
        node_trace["scan_error_type"] = scan_result.get("error_type", "")
        node_trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False)
        node_trace["output_row_count"] = len(scan_result.get("data", []) or [])
        node_trace["output_columns"] = list(scan_result.get("data", [{}])[0].keys()) if scan_result.get("data") else []
        return {"status": "success", "data": scan_result.get("data", []), "trace": node_trace}

    def _run_sql_subquery(self, node_id: str, description: str, root_query: str, bound_inputs: dict[str, Any], trace: dict) -> dict[str, Any]:
        del trace
        print(f"   [SQL] Running SQL pipeline for node '{node_id}'...")
        node_trace = {
            "node_id": node_id,
            "query_spec": {},
            "generated_sql": "",
            "generate_sql_reasoning": "",
            "generate_sql_parse_error": "",
            "generate_sql_raw_response_preview": "",
            "pre_scan_validation_is_valid": "",
            "pre_scan_validation_reason": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_error_type": "",
            "scan_raw_rows": "",
            "self_heal_attempts": 0,
            "failure_stage": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "bound_inputs": self._json_safe(bound_inputs),
            "attempts": [],
        }

        inputs = {
            "query": description,
            "root_query": root_query,
            "bound_inputs": bound_inputs,
            "sql_schema": self.sql_schema,
            "global_schema": self.sql_schema,
            "schema_kind": "sql",
        }
        qs_result = self.registry["Query_Spec"](inputs)
        inputs.update(qs_result)
        node_trace["query_spec"] = qs_result.get("query_spec", {})

        gen_result = sql_pipeline.semantic_generate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
        inputs["sql"] = gen_result.get("sql", "")
        node_trace["generated_sql"] = inputs["sql"]
        node_trace["sql_schema_tables"] = gen_result.get("sql_schema_tables", [])
        node_trace["sql_schema_relevant_tables"] = gen_result.get("relevant_tables", [])
        node_trace["generate_sql_reasoning"] = gen_result.get("reasoning", "")
        node_trace["generate_sql_parse_error"] = gen_result.get("parse_error", "")
        node_trace["generate_sql_raw_response_preview"] = gen_result.get("raw_response_preview", "")
        node_trace["attempts"].append({"stage": "Generate_SQL", "attempt": 1, "output_present": bool(inputs["sql"]), "parse_error": gen_result.get("parse_error", "")})

        for attempt in range(1, self.pre_scan_validate_max_retries + 1):
            shape_check = validate_aggregation_shape(inputs.get("query_spec", {}), inputs.get("sql", ""))
            if not shape_check.get("is_valid", True):
                check = shape_check
                node_trace["attempts"].append({
                    "stage": "Aggregation_Shape_Check_SQL",
                    "attempt": attempt,
                    "is_valid": False,
                    "severity": shape_check.get("severity", ""),
                    "reason": shape_check.get("reason", ""),
                })
            else:
                psv_result = sql_pipeline.semantic_pre_scan_validate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
                check = psv_result.get("pre_scan_validation", {})
            is_valid = bool(check.get("is_valid", False))
            severity = str(check.get("severity", "repairable_warning")).lower()
            node_trace["pre_scan_validation_is_valid"] = is_valid
            node_trace["pre_scan_validation_reason"] = check.get("reason", "")
            node_trace["attempts"].append({
                "stage": "Pre_Scan_Validate_SQL",
                "attempt": attempt,
                "is_valid": is_valid,
                "severity": severity,
                "reason": check.get("reason", ""),
            })

            if is_valid or severity in {"valid", "acceptable_warning"}:
                break
            if attempt == self.pre_scan_validate_max_retries:
                if check is shape_check:
                    # An unmet fan-out contract is a quality warning, not a broken query.
                    # Execute anyway so the post-scan contract check can judge the rows.
                    node_trace["aggregation_shape_warning"] = check.get("reason", "")
                    break
                node_trace["failure_stage"] = "Pre_Scan_Validate_SQL"
                print(f"   [SQL] Pre_Scan_Validate_SQL hard stop for node '{node_id}'.")
                return {"status": "error", "error_message": check.get("reason"), "data": [], "trace": node_trace}

            inputs["logic_feedback"] = json.dumps({
                "error_type": "pre_scan_validation_failed",
                "reason": check.get("reason"),
                "rewrite_hint": check.get("rewrite_hint", ""),
                "failed_sql": inputs.get("sql", ""),
            }, indent=2)
            node_trace["self_heal_attempts"] += 1
            gen_result = sql_pipeline.semantic_generate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
            inputs["sql"] = gen_result.get("sql", "")
            node_trace["generated_sql"] = inputs["sql"]
            node_trace["sql_schema_tables"] = gen_result.get("sql_schema_tables", [])
            node_trace["sql_schema_relevant_tables"] = gen_result.get("relevant_tables", [])
            node_trace["generate_sql_reasoning"] = gen_result.get("reasoning", "")
            node_trace["generate_sql_parse_error"] = gen_result.get("parse_error", "")
            node_trace["generate_sql_raw_response_preview"] = gen_result.get("raw_response_preview", "")
            node_trace["attempts"].append({"stage": "Generate_SQL", "attempt": attempt + 1, "output_present": bool(inputs["sql"]), "parse_error": gen_result.get("parse_error", "")})

        validation = {"is_valid": True, "reason": "", "severity": "valid"}
        scan_result = {}
        original_successful_scan = None
        for attempt in range(1, self.post_scan_validate_max_retries + 1):
            scan_result = sql_pipeline.pre_programmed_scan_sql(inputs, db_path=self.db_path)
            node_trace["attempts"].append({
                "stage": "Scan_SQL",
                "attempt": attempt,
                "status": scan_result.get("status", ""),
                "row_count": scan_result.get("row_count", 0),
                "error": scan_result.get("error_message", ""),
                "error_type": scan_result.get("error_type", ""),
            })
            if scan_result.get("status") == "error":
                node_trace["failure_stage"] = "Scan_SQL"
                print(f"   [SQL] Scan_SQL failed for node '{node_id}': {scan_result.get('error_message')}")
                return {"status": "error", "error_message": scan_result.get("error_message"), "data": [], "trace": node_trace}
            if original_successful_scan is None:
                original_successful_scan = scan_result
            if isinstance(scan_result, dict) and isinstance(scan_result.get("data"), list):
                scan_result["data"] = normalize_semantic_result(
                    root_query,
                    inputs.get("query_spec", {}),
                    scan_result.get("data", []),
                )
                scan_result["row_count"] = len(scan_result.get("data", []))

            if not should_validate_semantics(inputs.get("query_spec", {})):
                node_trace["validation_is_valid"] = ""
                node_trace["validation_reason"] = ""
                break

            validation = validate_semantic_result(root_query, inputs.get("query_spec", {}), scan_result.get("data", []))
            is_valid = bool(validation.get("is_valid", False))
            severity = str(validation.get("severity", "repairable_warning")).lower()
            node_trace["validation_is_valid"] = is_valid
            node_trace["validation_reason"] = validation.get("reason", "")
            node_trace["attempts"].append({
                "stage": "Validate_SQL",
                "attempt": attempt,
                "is_valid": is_valid,
                "severity": severity,
                "reason": validation.get("reason", ""),
            })
            if is_valid or severity == "valid":
                break
            if attempt == self.post_scan_validate_max_retries:
                scan_result = original_successful_scan or scan_result
                break

            inputs["logic_feedback"] = json.dumps({
                "error_type": "semantic_validation_failed",
                "reason": validation.get("reason", ""),
                "rewrite_hint": validation.get("rewrite_hint", ""),
                "query_spec": inputs.get("query_spec", {}),
                "failed_sql": inputs.get("sql", ""),
                "result_sample": (scan_result.get("data", []) or [])[:10],
            }, indent=2)
            node_trace["self_heal_attempts"] += 1
            gen_result = sql_pipeline.semantic_generate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
            inputs["sql"] = gen_result.get("sql", "")
            node_trace["generated_sql"] = inputs["sql"]
            node_trace["sql_schema_tables"] = gen_result.get("sql_schema_tables", [])
            node_trace["sql_schema_relevant_tables"] = gen_result.get("relevant_tables", [])
            node_trace["generate_sql_reasoning"] = gen_result.get("reasoning", "")
            node_trace["generate_sql_parse_error"] = gen_result.get("parse_error", "")
            node_trace["generate_sql_raw_response_preview"] = gen_result.get("raw_response_preview", "")
            node_trace["attempts"].append({"stage": "Generate_SQL", "attempt": self.pre_scan_validate_max_retries + attempt, "output_present": bool(inputs["sql"]), "parse_error": gen_result.get("parse_error", "")})

            psv_result = sql_pipeline.semantic_pre_scan_validate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
            check = psv_result.get("pre_scan_validation", {})
            node_trace["pre_scan_validation_is_valid"] = bool(check.get("is_valid", False))
            node_trace["pre_scan_validation_reason"] = check.get("reason", "")
            node_trace["attempts"].append({
                "stage": "Pre_Scan_Validate_SQL",
                "attempt": self.pre_scan_validate_max_retries + attempt,
                "is_valid": bool(check.get("is_valid", False)),
                "severity": str(check.get("severity", "repairable_warning")).lower(),
                "reason": check.get("reason", ""),
            })
            if not check.get("is_valid", False) and str(check.get("severity", "repairable_warning")).lower() not in {"valid", "acceptable_warning"}:
                if attempt == self.post_scan_validate_max_retries:
                    scan_result = original_successful_scan or scan_result
                    break
                continue

        node_trace["scan_status"] = scan_result.get("status", "")
        node_trace["scan_row_count"] = scan_result.get("row_count", "")
        node_trace["scan_error"] = scan_result.get("error_message", "")
        node_trace["scan_error_type"] = scan_result.get("error_type", "")
        node_trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False)

        node_trace["output_row_count"] = len(scan_result.get("data", []) or [])
        node_trace["output_columns"] = list(scan_result.get("data", [{}])[0].keys()) if scan_result.get("data") else []
        return {"status": "success", "data": scan_result.get("data", []), "trace": node_trace}

    @staticmethod
    def _key_rows(rows: list[dict], key: str) -> dict[str, dict]:
        """Index rows by a canonical form of `key` so backends share a key space."""
        keyed = {}
        for row in rows:
            if not isinstance(row, dict) or row.get(key) is None:
                continue
            canonical = set_operation_key(row.get(key))
            if canonical:
                keyed.setdefault(canonical, row)
        return keyed

    @staticmethod
    def _identifier_candidates(rows: list[dict]) -> list[str]:
        """Columns that plausibly identify an entity, most identifier-like first."""
        if not rows:
            return []
        candidates = []
        for column in rows[0].keys():
            values = [row.get(column) for row in rows[:200] if isinstance(row, dict)]
            keys = {set_operation_key(value) for value in values if value is not None}
            if not keys:
                continue
            lowered = str(column).lower()
            score = (0 if ("id" in lowered or lowered.endswith("_key")) else 1, -len(keys))
            candidates.append((score, str(column)))
        return [column for _, column in sorted(candidates)]

    def _realign_set_operation_keys(
        self,
        op_name: str,
        pred_rows: list[tuple[str, list[dict]]],
        keyed_inputs: list[tuple[str, str, dict[str, dict]]],
    ) -> list[tuple[str, str, dict[str, dict]]] | None:
        """Re-key predecessors on a shared identifier when the declared keys do not meet.

        Different backends name and shape the same identifier differently — a KG
        node may bind ``?investor`` to a full IRI while a SQL node returns
        ``investor_id`` as a bare literal — so the planner-declared output field
        can leave two sets with no common values at all. Rather than report an
        empty intersection, retry over identifier-like columns and keep the
        pairing that actually overlaps. Purely deterministic: no LLM involved.
        """
        if op_name not in {"Set_Intersect", "Set_Difference"} or len(keyed_inputs) < 2:
            return None
        if all(row_by_key for _, _, row_by_key in keyed_inputs):
            current = [set(row_by_key.keys()) for _, _, row_by_key in keyed_inputs]
            if current[0].intersection(*current[1:]):
                return None

        rows_by_pred = dict(pred_rows)
        base_id = keyed_inputs[0][0]
        best = None
        for base_column in self._identifier_candidates(rows_by_pred.get(base_id, []))[:5]:
            base_keyed = self._key_rows(rows_by_pred.get(base_id, []), base_column)
            if not base_keyed:
                continue
            attempt = [(base_id, base_column, base_keyed)]
            overlap = len(base_keyed)
            for pred_id, _, _ in keyed_inputs[1:]:
                choice = None
                for column in self._identifier_candidates(rows_by_pred.get(pred_id, []))[:5]:
                    keyed = self._key_rows(rows_by_pred.get(pred_id, []), column)
                    shared = len(set(base_keyed) & set(keyed))
                    if shared and (choice is None or shared > choice[0]):
                        choice = (shared, column, keyed)
                if choice is None:
                    attempt = None
                    break
                attempt.append((pred_id, choice[1], choice[2]))
                overlap = min(overlap, choice[0])
            if attempt and overlap:
                # Candidates are ordered identifier-first, so the first base
                # column that overlaps every predecessor is the most trustworthy
                # join key. Maximizing raw overlap instead would let an
                # incidental low-cardinality column (a sector, a category) win
                # over the real entity id.
                best = (overlap, attempt)
                break
        return best[1] if best else None

    def _run_set_operation(self, node_id: str, op_name: str, pred_results: list, dag: nx.DiGraph) -> dict[str, Any]:
        print(f"   [SET] Running {op_name} for node '{node_id}'...")
        node_trace = {"node_id": node_id, "operator": op_name, "input_summaries": [], "binding_operation": op_name}
        pred_rows = []
        for pred_id, res in pred_results:
            data = res.get("data", []) if isinstance(res, dict) else []
            rows = [row for row in (data if isinstance(data, list) else []) if isinstance(row, dict)]
            pred_rows.append((pred_id, rows))

        keyed_inputs = []
        for pred_id, rows in pred_rows:
            key = self._output_key_for_predecessor(dag, pred_id, node_id, rows)
            keyed_inputs.append((pred_id, key, self._key_rows(rows, key)))

        realigned_key = self._realign_set_operation_keys(op_name, pred_rows, keyed_inputs)
        if realigned_key:
            keyed_inputs = realigned_key
            node_trace["key_realignment"] = "re-keyed predecessors on a shared identifier column to avoid an empty result"

        for pred_id, key, row_by_key in keyed_inputs:
            source_rows = next((rows for source_id, rows in pred_rows if source_id == pred_id), [])
            node_trace["input_summaries"].append({"source_node": pred_id, "source_key": key, "row_count": len(source_rows), "key_count": len(row_by_key)})

        sets = [set(row_by_key.keys()) for _, _, row_by_key in keyed_inputs]
        if not sets:
            node_trace["output_row_count"] = 0
            return {"status": "success", "data": [], "trace": node_trace}

        if op_name == "Set_Intersect":
            result_set = sets[0].intersection(*sets[1:])
        elif op_name == "Set_Union":
            result_set = sets[0].union(*sets[1:])
        elif op_name == "Set_Difference":
            result_set = sets[0].difference(*sets[1:])
        else:
            result_set = sets[0]

        base_rows = keyed_inputs[0][2] if keyed_inputs else {}
        result_rows = []
        for key_value in sorted(result_set):
            row = dict(base_rows.get(key_value, {}))
            if not row:
                row = {"entity_id": key_value}
            result_rows.append(row)

        node_trace["output_row_count"] = len(result_rows)
        node_trace["output_columns"] = list(result_rows[0].keys()) if result_rows else []
        return {"status": "success", "data": result_rows, "trace": node_trace}

    def _execute_node(self, node_id: str, dag: nx.DiGraph, initial_query: str, results_cache: dict[str, Any]) -> dict[str, Any]:
        node_data = dag.nodes[node_id]
        op_name = node_data.get("operator", "Subquery")
        backend = node_data.get("backend", "KG")
        description = node_data.get("description", initial_query)
        started = time.perf_counter()
        print(f"\n[Node '{node_id}'] op={op_name} backend={backend} thread={threading.get_ident()}")

        bound_inputs = self._resolve_bound_inputs(node_id, dag, results_cache)
        pred_results = [(p, results_cache[p]) for p in dag.predecessors(node_id) if p in results_cache]

        if op_name == "Subquery":
            result = self._run_sql_subquery(node_id, description, initial_query, bound_inputs, {}) if backend == "SQL" else self._run_kg_subquery(node_id, description, initial_query, bound_inputs, {})
        elif op_name in {"Set_Intersect", "Set_Union", "Set_Difference"}:
            result = self._run_set_operation(node_id, op_name, pred_results, dag)
        elif op_name not in self.registry:
            # Decomposition occasionally emits an operator name outside the
            # registered set (a set-operator synonym is normalized upstream in
            # build_subquery_dag, but any other unrecognized name lands here).
            # Fail just this node, the same way a bad SQL/SPARQL query does,
            # rather than raising past the DAG loop.
            result = {
                "status": "error",
                "error_message": f"Operator '{op_name}' not found in registry.",
                "data": [],
            }
        else:
            merged_inputs = {"query": description, "bound_inputs": bound_inputs}
            for _, res in pred_results:
                if isinstance(res, dict):
                    merged_inputs.update(res)
            result = self.registry[op_name](merged_inputs)

        elapsed = round(time.perf_counter() - started, 3)
        node_trace = result.pop("trace", {}) if isinstance(result, dict) else {}
        node_trace.update({
            "node_id": node_id,
            "operator": op_name,
            "backend": backend,
            "description": description,
            "bound_inputs": self._json_safe(bound_inputs),
            "upstream_nodes": [pred_id for pred_id, _ in pred_results],
            "status": result.get("status", "success") if isinstance(result, dict) else "success",
            "elapsed_seconds": elapsed,
            "thread_id": threading.get_ident(),
        })
        if isinstance(result, dict):
            result["trace"] = node_trace
        print(f" [{node_id}] complete. status={result.get('status', 'success')} rows={self._row_count(result)} elapsed={elapsed}s")
        return result

    def execute_dag(self, dag: nx.DiGraph, initial_query: str) -> Any:
        print("\n--- Starting Subquery DAG Execution ---")
        results_cache: dict[str, Any] = {}
        all_node_traces: dict[str, Any] = {}
        node_plan_traces: dict[str, Any] = {}
        top_level_trace = {
            "operator_sequence": [],
            "node_backends": {},
            "node_statuses": {},
            "node_dependencies": {},
            "dag_execution_levels": [],
            "failure_stage": "",
            "self_heal_attempts": 0,
            "final_status": "success",
        }

        ordered_nodes = list(nx.topological_sort(dag))
        execution_levels = self._build_execution_levels(dag)
        top_level_trace["dag_execution_levels"] = execution_levels
        self._log_dag_plan(dag, execution_levels)
        for node_id in ordered_nodes:
            node_data = dag.nodes[node_id]
            backend = node_data.get("backend", "")
            op_name = node_data.get("operator", "Subquery")
            top_level_trace["operator_sequence"].append(f"{node_id}:{op_name}({backend or 'set'})")
            top_level_trace["node_backends"][node_id] = backend or op_name
            top_level_trace["node_dependencies"][node_id] = list(dag.predecessors(node_id))
            node_plan_traces[node_id] = self._planned_node_trace(node_id, dag)

        for level_index, level in enumerate(execution_levels, 1):
            runnable_nodes = []
            for node_id in level:
                failed_preds = [pred for pred in dag.predecessors(node_id) if results_cache.get(pred, {}).get("status") in {"error", "skipped"}]
                if failed_preds:
                    skipped_trace = {
                        **node_plan_traces[node_id],
                        "status": "skipped",
                        "failure_stage": "Dependency",
                        "skipped_due_to": failed_preds,
                    }
                    all_node_traces[node_id] = skipped_trace
                    top_level_trace["node_statuses"][node_id] = "skipped"
                    results_cache[node_id] = {
                        "status": "skipped",
                        "error_message": f"Skipped because upstream dependency failed: {failed_preds}",
                        "data": [],
                    }
                    print(f" [{node_id}] skipped because upstream dependency failed: {failed_preds}")
                else:
                    runnable_nodes.append(node_id)

            if not runnable_nodes:
                continue

            print(f"[DAG] Executing level {level_index} with {len(runnable_nodes)} node(s): {runnable_nodes}")
            max_workers = max(1, min(len(runnable_nodes), int(os.getenv("DAG_LEVEL_MAX_WORKERS", "4"))))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as node_pool:
                future_to_node = {
                    node_pool.submit(self._execute_node, node_id, dag, initial_query, dict(results_cache)): node_id
                    for node_id in runnable_nodes
                }
                for future in concurrent.futures.as_completed(future_to_node):
                    node_id = future_to_node[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "status": "error",
                            "error_message": str(exc),
                            "data": [],
                            "trace": {
                                **node_plan_traces[node_id],
                                "status": "error",
                                "failure_stage": "Exception",
                                "error_message": str(exc),
                            },
                        }
                    node_trace = result.pop("trace", {})
                    all_node_traces[node_id] = {**node_plan_traces[node_id], **node_trace}
                    top_level_trace["self_heal_attempts"] += node_trace.get("self_heal_attempts", 0)
                    node_status = result.get("status", "success")
                    top_level_trace["node_statuses"][node_id] = node_status
                    if node_status == "error" and not top_level_trace["failure_stage"]:
                        top_level_trace["failure_stage"] = f"{node_id}:{node_trace.get('failure_stage', 'unknown')}"
                    results_cache[node_id] = result

        last_node = ordered_nodes[-1]
        last_result = results_cache.get(last_node, {})
        final_data = last_result.get("data", [])
        failed_nodes = [node_id for node_id, status in top_level_trace["node_statuses"].items() if status == "error"]
        skipped_nodes = [node_id for node_id, status in top_level_trace["node_statuses"].items() if status == "skipped"]
        top_level_trace["final_status"] = "error" if (failed_nodes or skipped_nodes) else "success"

        explain_inputs = {"query": initial_query, "data": final_data}
        if top_level_trace["final_status"] == "error":
            explain_inputs["context"] = (
                f"Subquery DAG failed. Failed nodes: {failed_nodes}. Skipped nodes: {skipped_nodes}. "
                f"Failure stage: {top_level_trace.get('failure_stage', '')}."
            )
        elif not final_data:
            explain_inputs["context"] = "No data was found after executing all subquery nodes."
        if top_level_trace["final_status"] == "error":
            final_answer = {
                "final_answer": explain_inputs["context"],
                "status": "error",
                "error_message": explain_inputs["context"],
            }
        else:
            final_answer = self.registry["Explain"](explain_inputs)

        aggregate_trace = {
            "operator_sequence": top_level_trace["operator_sequence"],
            "dag_execution_levels": top_level_trace["dag_execution_levels"],
            "retrieved_classes": [],
            "query_spec": {},
            "generated_sparql": "",
            "pre_scan_validation_is_valid": "",
            "pre_scan_validation_reason": "",
            "pre_scan_warning": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_raw_rows": json.dumps(final_data, ensure_ascii=False),
            "unknown_terms": [],
            "term_suggestions": {},
            "refine_reason": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "self_heal_attempts": top_level_trace["self_heal_attempts"],
            "short_circuit_stage": "",
            "failure_stage": top_level_trace.get("failure_stage", ""),
            "final_status": top_level_trace["final_status"],
            "node_statuses": top_level_trace["node_statuses"],
            "node_dependencies": top_level_trace["node_dependencies"],
            "node_traces": all_node_traces,
            "node_backends": top_level_trace["node_backends"],
        }

        for node_id in ordered_nodes:
            nt = all_node_traces.get(node_id, {})
            if nt.get("retrieved_classes"):
                aggregate_trace["retrieved_classes"] = nt["retrieved_classes"]
            if nt.get("query_spec"):
                aggregate_trace["query_spec"] = nt["query_spec"]
            if nt.get("generated_sparql"):
                aggregate_trace["generated_sparql"] = nt["generated_sparql"]
            if nt.get("generated_sql"):
                aggregate_trace["generated_sparql"] = nt["generated_sql"]
            if "pre_scan_validation_is_valid" in nt and nt.get("pre_scan_validation_is_valid") != "":
                aggregate_trace["pre_scan_validation_is_valid"] = nt["pre_scan_validation_is_valid"]
                aggregate_trace["pre_scan_validation_reason"] = nt.get("pre_scan_validation_reason", "")
            if "validation_is_valid" in nt and nt.get("validation_is_valid") != "":
                aggregate_trace["validation_is_valid"] = nt["validation_is_valid"]
                aggregate_trace["validation_reason"] = nt.get("validation_reason", "")
            if nt.get("scan_status"):
                aggregate_trace["scan_status"] = nt["scan_status"]
                aggregate_trace["scan_row_count"] = nt.get("scan_row_count", "")
                aggregate_trace["scan_error"] = nt.get("scan_error", "")

        if isinstance(final_answer, dict):
            final_answer["trace"] = aggregate_trace

        print("--- Subquery DAG Execution Complete ---")
        return final_answer
