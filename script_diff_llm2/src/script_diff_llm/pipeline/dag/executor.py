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
from script_diff_llm.pipeline.contracts import split_contract_errors, validate_query_spec
from script_diff_llm.pipeline.semantic_contract import (
    normalize_semantic_result,
    normalize_result_iris,
    set_operation_key,
    should_validate_semantics,
    validate_aggregation_shape,
    validate_join_population_shape,
    validate_join_policy_shape,
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
        identity_bindings: list[dict[str, Any]] | None = None,
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
        self.identity_prefixes = tuple(
            binding["kg_uri_prefix"] for binding in (identity_bindings or [])
        )
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
                    rows = upstream_result["data"]
                    if not rows:
                        value = []
                    elif all(isinstance(row, dict) and src_field in row for row in rows):
                        value = [row[src_field] for row in rows]
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
            preferred = ["entity_id", "id"]
            for key in preferred:
                if key in rows[0]:
                    return key
            return list(rows[0].keys())[0]
        return "entity_id"

    def _kg_scan(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run KG Scan and apply only declared identity namespace mappings."""
        scan_result = self.registry["Scan"](inputs)
        if isinstance(scan_result, dict) and isinstance(scan_result.get("data"), list):
            scan_result["data"] = normalize_result_iris(scan_result["data"], self.identity_prefixes)
        return scan_result

    def _run_kg_subquery(self, node_id: str, description: str, root_query: str, bound_inputs: dict[str, Any], trace: dict) -> dict[str, Any]:
        expected_outputs = trace.get('expected_outputs', [])
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
        inputs['expected_outputs'] = expected_outputs
        node_trace['expected_outputs'] = expected_outputs
        retrieve_result = self.registry["Retrieve"](inputs)
        inputs.update(retrieve_result)
        node_trace["retrieved_classes"] = retrieve_result.get("retrieved_tables", [])

        qs_result = self.registry["Query_Spec"](inputs)
        inputs.update(qs_result)
        node_trace["query_spec"] = qs_result.get("query_spec", {})
        spec = inputs.get("query_spec")
        contract_errors = validate_query_spec(spec, self.kg_metadata, description) if isinstance(spec, dict) and ("contract_errors" in spec or "requirements" in spec) else []
        contract_errors, contract_warnings = split_contract_errors(contract_errors)
        if contract_warnings:
            node_trace["contract_warnings"] = contract_warnings
        if contract_errors:
            node_trace["failure_stage"] = "Query_Spec_Contract"
            node_trace["contract_errors"] = contract_errors
            return {"status": "error", "error_message": "; ".join(contract_errors), "data": [], "trace": node_trace}

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
            }, indent=2, default=str)
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
        node_trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False, default=str)
        node_trace["output_row_count"] = len(scan_result.get("data", []) or [])
        node_trace["output_columns"] = list(scan_result.get("data", [{}])[0].keys()) if scan_result.get("data") else []
        return {"status": "success", "data": scan_result.get("data", []), "trace": node_trace}

    def _scan_sql_with_repair(self, inputs: dict, node_trace: dict) -> dict:
        """Repair query defects with a bounded budget; never reinterpret the spec."""
        rejected = None
        for attempt in range(1, max(1, self.scan_refine_max_retries) + 1):
            if rejected is None:
                result = sql_pipeline.pre_programmed_scan_sql(inputs, db_path=self.db_path)
                node_trace["attempts"].append({"stage": "Scan_SQL", "attempt": attempt,
                    "status": result.get("status", ""), "row_count": result.get("row_count", 0),
                    "error": result.get("error_message", ""), "error_type": result.get("error_type", "")})
            else:
                result = {"status": "error", "data": [], "error_type": "sql_pre_scan_error",
                          "error_message": rejected.get("reason", "Repaired SQL failed validation.")}
            if result.get("status") != "error":
                return result
            repairable = {"empty_sql", "sql_no_such_table", "sql_no_such_column", "sql_execution_error", "sql_pre_scan_error"}
            used_repairs = node_trace.get("sql_scan_repair_attempts", 0)
            if attempt >= self.scan_refine_max_retries or used_repairs >= max(0, self.scan_refine_max_retries - 1) or result.get("error_type") not in repairable:
                return result
            inputs["logic_feedback"] = json.dumps({"error_type": result.get("error_type"),
                "reason": result.get("error_message"), "failed_sql": inputs.get("sql", ""),
                "rewrite_hint": "Repair the query against the supplied schema. Preserve Query_Spec, bound inputs, all predicates, metric stages and final outputs."})
            node_trace["self_heal_attempts"] += 1
            node_trace["sql_scan_repair_attempts"] = used_repairs + 1
            generated = sql_pipeline.semantic_generate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
            inputs["sql"] = generated.get("sql", "")
            node_trace["generated_sql"] = inputs["sql"]
            node_trace["generate_sql_reasoning"] = generated.get("reasoning", "")
            node_trace["generate_sql_parse_error"] = generated.get("parse_error", "")
            node_trace["sql_schema_relevant_tables"] = generated.get("relevant_tables", [])
            node_trace["attempts"].append({"stage": "Generate_SQL_Scan_Repair", "attempt": attempt,
                                          "output_present": bool(inputs["sql"])})
            rejected = None
            for validate in (validate_aggregation_shape, validate_join_population_shape, validate_join_policy_shape):
                check = validate(inputs.get("query_spec", {}), inputs["sql"])
                if not check.get("is_valid", True):
                    rejected = check
                    break
            if rejected is None:
                check = sql_pipeline.semantic_pre_scan_validate_sql(inputs, self.llm_client, self.registry.get("_generate_model", ""))
                check = check.get("pre_scan_validation", {})
                if not check.get("is_valid", False) and check.get("severity") not in {"valid", "acceptable_warning"}:
                    rejected = check
            node_trace["attempts"].append({"stage": "Pre_Scan_Validate_SQL_Repair", "attempt": attempt,
                "is_valid": rejected is None, "reason": (rejected or {}).get("reason", "")})
            node_trace["pre_scan_validation_is_valid"] = rejected is None
            node_trace["pre_scan_validation_reason"] = check.get("reason", "")
        return result

    def _run_sql_subquery(self, node_id: str, description: str, root_query: str, bound_inputs: dict[str, Any], trace: dict) -> dict[str, Any]:
        expected_outputs = trace.get('expected_outputs', [])
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
            "db_path": self.db_path,
            "global_schema": self.sql_schema,
            "schema_kind": "sql",
            "expected_outputs": expected_outputs,
        }
        node_trace['expected_outputs'] = expected_outputs
        qs_result = self.registry["Query_Spec"](inputs)
        inputs.update(qs_result)
        node_trace["query_spec"] = qs_result.get("query_spec", {})
        spec = inputs.get("query_spec")
        contract_errors = validate_query_spec(spec, self.sql_schema, description) if isinstance(spec, dict) and ("contract_errors" in spec or "requirements" in spec) else []
        contract_errors, contract_warnings = split_contract_errors(contract_errors)
        if contract_warnings:
            node_trace["contract_warnings"] = contract_warnings
        if contract_errors:
            node_trace["failure_stage"] = "Query_Spec_Contract"
            node_trace["contract_errors"] = contract_errors
            return {"status": "error", "error_message": "; ".join(contract_errors), "data": [], "trace": node_trace}

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
                join_check = validate_join_population_shape(inputs.get("query_spec", {}), inputs.get("sql", ""))
                if not join_check.get("is_valid", True):
                    check = join_check
                    node_trace["attempts"].append({
                        "stage": "Join_Population_Check_SQL",
                        "attempt": attempt,
                        "is_valid": False,
                        "severity": join_check.get("severity", ""),
                        "reason": join_check.get("reason", ""),
                    })
                else:
                    policy_check = validate_join_policy_shape(inputs.get("query_spec", {}), inputs.get("sql", ""))
                    if not policy_check.get("is_valid", True):
                        check = policy_check
                        node_trace["attempts"].append({
                            "stage": "Join_Policy_Check_SQL",
                            "attempt": attempt,
                            "is_valid": False,
                            "severity": policy_check.get("severity", ""),
                            "reason": policy_check.get("reason", ""),
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
            }, indent=2, default=str)
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
            scan_result = self._scan_sql_with_repair(inputs, node_trace)
            if scan_result.get("status") == "error":
                node_trace["failure_stage"] = "Scan_SQL"
                node_trace["scan_status"] = "error"
                node_trace["scan_error"] = scan_result.get("error_message", "")
                node_trace["scan_error_type"] = scan_result.get("error_type", "")
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
            }, indent=2, default=str)
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

            join_check = validate_join_population_shape(inputs.get("query_spec", {}), inputs.get("sql", ""))
            if not join_check.get("is_valid", True):
                check = join_check
                node_trace["attempts"].append({
                    "stage": "Join_Population_Check_SQL",
                    "attempt": self.pre_scan_validate_max_retries + attempt,
                    "is_valid": False,
                    "severity": str(join_check.get("severity", "repairable_warning")).lower(),
                    "reason": join_check.get("reason", ""),
                })
            else:
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
        node_trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False, default=str)

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
            declared = [item.get("name") for item in node_data.get("inputs", []) if isinstance(item, dict)]
            missing = [name for name in declared if name not in bound_inputs]
            if missing:
                result = {"status": "error", "data": [], "error_message": f"Unresolved upstream bindings: {missing}",
                          "trace": {"failure_stage": "Binding", "missing_inputs": missing}}
            elif any(isinstance(bound_inputs.get(name), list) and not bound_inputs[name] for name in declared):
                result = {"status": "success", "data": [], "trace": {"empty_upstream": True}}
            else:
                output_contract = {'expected_outputs': node_data.get('outputs', []) if dag.out_degree(node_id) else []}
                result = self._run_sql_subquery(node_id, description, initial_query, bound_inputs, output_contract) if backend == "SQL" else self._run_kg_subquery(node_id, description, initial_query, bound_inputs, output_contract)
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
            "scan_raw_rows": json.dumps(final_data, ensure_ascii=False, default=str),
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
