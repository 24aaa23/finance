"""AOP executor."""

from .common import (
    Any,
    Dict,
    POST_SCAN_VALIDATE_MAX_RETRIES,
    PRE_SCAN_VALIDATE_MAX_RETRIES,
    SCAN_REFINE_MAX_RETRIES,
    json,
    nx,
    time,
)
from .utils import sparql_too_similar


class AOPExecutor:

    """
    Executes the generated DAG topologically. Manages state transitions,
    the Global Data Bus (context preservation), and the Self-Healing validation loops.
    """
    def __init__(self, operator_registry: Dict[str, Any], rdf_graph: Any,
                 global_schema: Dict[str, Any] | None = None):
        self.registry = operator_registry
        self.rdf_graph = rdf_graph
        self.global_schema = global_schema or {}

    def execute_dag(
        self,
        dag: nx.DiGraph,
        initial_query: str,
        decomposition: Dict[str, Any] | None = None,
        initial_context: Dict[str, Any] | None = None,
    ) -> Any:
        print("\n--- Starting DAG Execution ---")
        decomposition = decomposition or {}
        initial_context = initial_context or {}
        results_cache = {
            "global_query": initial_query,
            "pre_dag_context": {
                **initial_context,
                "decomposition": decomposition,
            },
        }
        trace = {
            "operator_sequence": [],
            "operator_audit": [],
            "retrieved_classes": list(initial_context.get("retrieved_tables", [])),
            "decomposition": decomposition,
            "subquestions": decomposition.get("subquestions", []) if isinstance(decomposition, dict) else [],
            "query_spec": {},
            "query_specs": [],
            "processing_specs": [],
            "final_spec": {},
            "retrieval_specs": [],
            "operator_plan": [],
            "post_scan_operator_outputs": [],
            "final_operator_data": [],
            "final_output_produced": False,
            "generated_sparql": "",
            "generated_sparqls": [],
            "executed_sparqls": [],
            "pre_scan_validation_is_valid": "",
            "pre_scan_validation_reason": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_raw_rows": "",
            "unknown_terms": [],
            "term_suggestions": {},
            "refine_reason": "",
            "pre_scan_warning": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "self_heal_attempts": 0,
            "repair_log": [],
            "short_circuit_stage": "",
            "failure_stage": "",
        }
        operator_plan_usage = {}
        retrieval_spec_usage = 0

        def resolve_subquestion(subquestion_id: str | None) -> Dict[str, Any]:
            if not subquestion_id or not isinstance(decomposition, dict):
                return {}
            for subquestion in decomposition.get("subquestions", []):
                if isinstance(subquestion, dict) and str(subquestion.get("id")) == str(subquestion_id):
                    return subquestion
            return {}

        def attach_query_spec_step_inputs(op_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal retrieval_spec_usage
            query_spec = inputs.get("query_spec", {})
            if not isinstance(query_spec, dict):
                return inputs
            if op_name == "Generate":
                retrieval_specs = query_spec.get("retrieval_specs", [])
                if isinstance(retrieval_specs, list) and retrieval_specs and "retrieval_spec" not in inputs:
                    retrieval_spec_id = inputs.get("retrieval_spec_id") or inputs.get("retrieval_id")
                    selected_spec = None
                    if retrieval_spec_id:
                        selected_spec = next(
                            (
                                spec for spec in retrieval_specs
                                if isinstance(spec, dict) and spec.get("id") == retrieval_spec_id
                            ),
                            None,
                        )
                    if selected_spec is None:
                        index = min(retrieval_spec_usage, len(retrieval_specs) - 1)
                        selected_spec = retrieval_specs[index]
                        retrieval_spec_usage += 1
                    inputs["retrieval_spec"] = selected_spec
                return inputs

            operator_plan = query_spec.get("operator_plan", [])
            if not isinstance(operator_plan, list):
                return inputs

            if op_name in {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Union", "Difference"}:
                merge_strategy = inputs.get("decomposition", {}).get("merge_strategy", {})
                if isinstance(merge_strategy, dict):
                    for key in ("join_key", "join_type", "how"):
                        if merge_strategy.get(key) is not None and key not in inputs:
                            inputs[key] = merge_strategy[key]
                merge_plan = query_spec.get("merge_plan", {})
                if isinstance(merge_plan, dict):
                    merge_operator = merge_plan.get("operator")
                    if (
                        merge_plan.get("required")
                        and (merge_operator in {None, op_name} or str(merge_operator) == op_name)
                    ):
                        for key in ("join_key", "left_input", "right_input", "join_type", "how"):
                            if merge_plan.get(key) is not None and key not in inputs:
                                inputs[key] = merge_plan[key]

            used_count = operator_plan_usage.get(op_name, 0)
            matching_steps = [
                step for step in operator_plan
                if isinstance(step, dict) and step.get("operator") == op_name
            ]
            if used_count >= len(matching_steps):
                return inputs

            step_inputs = {
                key: value
                for key, value in matching_steps[used_count].items()
                if key not in {"operator", "input", "output"} and value is not None
            }
            merged = {**inputs, **step_inputs}
            operator_plan_usage[op_name] = used_count + 1
            return merged

        def run_pre_scan_validation_loop(inputs: Dict[str, Any], max_retries: int) -> tuple[bool, Dict[str, Any], Any]:
            attempt = 0
            result = {"pre_scan_validation": {"is_valid": False, "reason": "Pre_Scan_Validate was not executed."}}

            while attempt < max_retries:
                result = self.registry["Pre_Scan_Validate"](inputs)
                check = result.get("pre_scan_validation", {})
                is_valid = check.get("is_valid") is True
                reason = check.get("reason", "")
                rewrite_hint = check.get("rewrite_hint", "")
                severity = str(check.get("severity", "valid" if is_valid else "repairable_warning")).strip().lower()

                trace["pre_scan_validation_is_valid"] = is_valid
                trace["pre_scan_validation_reason"] = reason

                if is_valid:
                    print("   [+] Pre_Scan_Validate passed.")
                    if severity == "acceptable_warning":
                        trace["pre_scan_warning"] = reason
                    result["sparql"] = inputs.get("sparql", "")
                    return True, result, None

                attempt += 1
                print(f"   [!] Pre_Scan_Validate failed attempt {attempt} ({severity}): {reason}")

                if attempt == max_retries:
                    trace["short_circuit_stage"] = "Pre_Scan_Validate"
                    trace["failure_stage"] = "Pre_Scan_Validate"
                    trace["validation_is_valid"] = False
                    trace["validation_reason"] = reason
                    final_result = {"final_answer": "Raw retrieval failed its contract after retries: " + str(reason), "trace": trace}
                    return False, result, final_result

                inputs["logic_feedback"] = json.dumps({
                    "error_type": "pre_scan_validation_failed",
                    "reason": reason,
                    "rewrite_hint": rewrite_hint,
                    "query_spec": inputs.get("query_spec", {}),
                    "failed_sparql": inputs.get("sparql", "")
                }, indent=2)

                trace["self_heal_attempts"] += 1
                regenerate_result = self.registry["Generate"](inputs)
                inputs["sparql"] = regenerate_result.get("sparql", "")
                trace["generated_sparql"] = inputs["sparql"]
                print("   [+] SQL regenerated after Pre_Scan_Validate failure.")

            result["sparql"] = inputs.get("sparql", "")
            return False, result, None

        def run_scan_refine_loop(inputs: Dict[str, Any], max_retries: int) -> tuple[Dict[str, Any], Any]:
            attempt = 0
            result = {}

            while attempt < max_retries:
                result = self.registry["Scan"](inputs)

                if result.get("status") != "error":
                    # Zero matches do not justify weakening a validated retrieval predicate.
                    # The final validator may request an explicit semantic repair with evidence.
                    return result, None

                attempt += 1
                print(f"   [!] SQL Error Caught: {result.get('error_message')}")
                trace["scan_status"] = "error"
                trace["scan_error"] = result.get("error_message", "")
                trace["unknown_terms"] = result.get("unknown_terms", trace["unknown_terms"])
                trace["term_suggestions"] = result.get("term_suggestions", trace["term_suggestions"])
                if result.get("unknown_terms"):
                    trace["refine_reason"] = "Unknown SQL identifiers before Scan"

                if attempt == max_retries:
                    print("   [!] Max retries reached for Scan. Short-circuiting directly to Explain.")
                    trace["short_circuit_stage"] = "Scan"
                    trace["failure_stage"] = "Scan"
                    final_result = self.registry["Explain"]({
                        "query": initial_query,
                        "data": [],
                        "context": "A database error prevented data retrieval."
                    })
                    if isinstance(final_result, dict):
                        final_result["trace"] = trace
                    return result, final_result

                query_spec = inputs.get("query_spec", {})
                source_classes = [item.get("class") for item in query_spec.get("retrieval_specs", [])
                                  if isinstance(item, dict)]
                assigned_source = inputs.get("subquestion", {}).get("source_class")
                if assigned_source:
                    source_classes.append(assigned_source)
                source_schema = {name: self.global_schema[name] for name in source_classes
                                 if name in self.global_schema}
                scan_feedback = {
                    "error_type": "raw_schema_failure" if result.get("unknown_terms") else "scan_error",
                    "reason": result.get("error_message", ""),
                    "unknown_terms": result.get("unknown_terms", []),
                    "term_suggestions": result.get("term_suggestions", {}),
                    "failed_sparql": result.get("failed_sparql", ""),
                    "source_schema": source_schema,
                }

                if not result.get("failed_sparql"):
                    print(f"   [+] No SQL was available. Triggering [Generate] again (Attempt {attempt}/{max_retries})...")
                    inputs["logic_feedback"] = json.dumps(scan_feedback, default=str)
                    trace["self_heal_attempts"] += 1
                    regenerate_result = self.registry["Generate"](inputs)
                    inputs["sparql"] = regenerate_result.get("sparql", "")
                    trace["generated_sparql"] = inputs["sparql"]

                    _, pre_check_result, final_result = run_pre_scan_validation_loop(
                        inputs,
                        PRE_SCAN_VALIDATE_MAX_RETRIES,
                    )
                    if final_result is not None:
                        return pre_check_result, final_result
                    inputs["sparql"] = pre_check_result.get("sparql", inputs["sparql"])
                    continue

                retrieval_contract_failure = bool(result.get("unknown_terms"))
                if retrieval_contract_failure:
                    # Unknown classes/predicates or a wrong source field are failures of the
                    # raw retrieval contract. A Refine call only rewrites text using the same
                    # bad Query_Spec, so regenerate that spec first.
                    print(f"   [+] Regenerating [Query_Spec] after raw schema failure (Attempt {attempt}/{max_retries})...")
                    query_spec_inputs = dict(inputs)
                    query_spec_inputs["previous_query_spec"] = query_spec
                    query_spec_inputs["spec_feedback"] = json.dumps({
                        **scan_feedback,
                        "hint": "Choose only schema-valid source class properties and required raw fields."
                    }, indent=2, default=str)
                    regenerated_spec = self.registry["Query_Spec"](query_spec_inputs)
                    candidate_spec = regenerated_spec.get("query_spec", {}) if isinstance(regenerated_spec, dict) else {}
                    if isinstance(candidate_spec, dict) and not candidate_spec.get("contract_errors"):
                        inputs["query_spec"] = candidate_spec
                        inputs["retrieval_spec"] = candidate_spec.get("retrieval_specs", [{}])[0]
                        inputs["logic_feedback"] = query_spec_inputs["spec_feedback"]
                        trace["self_heal_attempts"] += 1
                        regenerated_sparql = self.registry["Generate"](inputs)
                        inputs["sparql"] = regenerated_sparql.get("sparql", "")
                        trace["generated_sparql"] = inputs["sparql"]
                        _, pre_check_result, final_result = run_pre_scan_validation_loop(inputs, PRE_SCAN_VALIDATE_MAX_RETRIES)
                        if final_result is not None:
                            return pre_check_result, final_result
                        inputs["sparql"] = pre_check_result.get("sparql", inputs["sparql"])
                        print("   [+] Query_Spec regenerated. Retrying [Scan]...")
                        continue

                print(f"   [+] Triggering [Refine] Operator (Attempt {attempt}/{max_retries})...")
                trace["self_heal_attempts"] += 1
                is_timeout = "timed out" in str(result.get("error_message", "")).lower()
                # Include schema-valid properties for the target class so the LLM
                # has concrete alternatives instead of guessing.
                query_spec_for_refine = inputs.get("query_spec", {})
                target_class = ""
                if isinstance(query_spec_for_refine, dict):
                    retrievals = query_spec_for_refine.get("retrieval_specs", [])
                    if retrievals and isinstance(retrievals[0], dict):
                        target_class = retrievals[0].get("class", "")
                logic_feedback = {
                    **scan_feedback,
                    "unknown_terms": result.get("unknown_terms", []),
                    "suggestions": result.get("term_suggestions", {}),
                    "target_class": target_class,
                    "error_type": "timeout" if is_timeout else "sparql_error",
                    "hint": (
                        "The raw retrieval timed out. Remove redundant query expressions while "
                        "preserving its source, fields, filters, and optional bindings. "
                        "Do not add aggregates, calculation subqueries, DISTINCT, or limits."
                        if is_timeout
                        else "Use only the declared backend's schema identifiers: SQL tables/columns "
                        "or exact RDF class/predicate IRIs. Do not invent sources or fields. "
                        "Check all fields against the source schema: " + target_class
                    )
                }
                refine_inputs = {
                    "failed_sparql": result.get("failed_sparql"),
                    "error_message": result.get("error_message"),
                    "logic_feedback": json.dumps(logic_feedback, indent=2),
                    "query": initial_query,
                    "query_spec": inputs.get("query_spec", {}),
                    "schema_details": source_schema,
                }
                refine_result = self.registry["Refine"](refine_inputs)
                new_sparql = refine_result.get("sparql", "")
                if is_timeout and sparql_too_similar(result.get("failed_sparql", ""), new_sparql):
                    print("   [!] Refined SQL is too similar to the timed-out query. Forcing Generate with stronger feedback.")
                    inputs["logic_feedback"] = json.dumps({
                        "error_type": "similar_timeout_rewrite",
                        "failed_sparql": result.get("failed_sparql", ""),
                        "hint": (
                            "The previous rewrite repeated the timed-out query. Remove redundant "
                            "patterns while keeping the declared raw retrieval unchanged. "
                            "Preserve its source, selected fields, filters, and optional bindings; "
                            "do not add aggregates, calculation subqueries, DISTINCT, or limits."
                        )
                    }, indent=2)
                    regenerate_result = self.registry["Generate"](inputs)
                    new_sparql = regenerate_result.get("sparql", "")

                inputs["sparql"] = new_sparql
                trace["generated_sparql"] = inputs["sparql"]
                _, pre_check_result, final_result = run_pre_scan_validation_loop(
                    inputs,
                    PRE_SCAN_VALIDATE_MAX_RETRIES,
                )
                if final_result is not None:
                    return pre_check_result, final_result
                inputs["sparql"] = pre_check_result.get("sparql", inputs["sparql"])
                print(f"   [+] SQL Refined. Retrying [Scan]...")

            return result, None

        def execute_spec_steps(spec, datasets, dataset_schemas=None):
            from .execution import execute_spec
            return execute_spec(spec, datasets, self.registry, initial_query, dataset_schemas)

        def abort_spec(stage, errors):
            trace["failure_stage"] = stage
            trace["validation_is_valid"] = False
            trace["validation_reason"] = "; ".join(str(error) for error in errors)
            trace["final_output_produced"] = False
            return {"final_answer": trace["validation_reason"], "trace": trace}

        def run_spec_attempts(stage, inputs, datasets, schemas):
            from .execution import execution_errors
            spec_key = "processing_spec" if stage == "Processing_Spec" else "final_spec"
            max_attempts = 4 if stage == "Final_Spec" else 3
            spec, errors, log = {}, [], []
            for attempt in range(max_attempts):
                try:
                    candidate = self.registry[stage](inputs)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    candidate = {spec_key: {"contract_errors": ["Malformed spec: " + str(exc)]}}
                spec = candidate.get(spec_key) if isinstance(candidate, dict) else None
                if not isinstance(spec, dict):
                    spec = {}
                    errors = [stage + " did not produce a specification."]
                else:
                    errors = list(spec.get("contract_errors", []))
                if stage == "Processing_Spec":
                    trace["processing_specs"].append({"attempt": attempt + 1, "processing_spec": spec})
                else:
                    trace["final_spec"] = spec
                if errors and spec.get("repair_stage") in {"Query_Spec", "Decompose"}:
                    trace["repair_stage"] = "Decompose"
                    trace["repair_log"].append({"stage": stage, "attempt": attempt + 1, "errors": errors,
                                                "spec": spec, "action": "repair_upstream"})
                    return {}, errors
                data, log = [], []
                if not errors:
                    data, log = execute_spec_steps(spec, datasets, schemas)
                    errors = [str(item.get("error") or item) for item in execution_errors(log)]
                if not errors:
                    return {**candidate, "data": data, "data_schema": spec.get("compiled_output_schema", []),
                            "execution_errors": [],
                            "processing_execution" if stage == "Processing_Spec" else "final_execution": log}, []
                # Build structured feedback so the LLM knows exactly which step
                # failed and why, rather than receiving a flat error string.
                failed_steps = [
                    {"step": item.get("step"), "operator": item.get("operator"),
                     "code": item.get("code"),
                     "error": str(item.get("error", "")),
                     "inputs": item.get("inputs", []),
                     "input_schemas": item.get("input_schemas", {})}
                    for item in execution_errors(log)
                ]
                structured_feedback = json.dumps({
                    "stage": stage,
                    "attempt": attempt + 1,
                    "failed_steps": failed_steps,
                    "errors": errors,
                    "available_schemas": {**schemas, **spec.get("dataset_schemas", {})},
                    "step_ids": spec.get("execution_name_map", {}),
                    "hint": "Repair the failed plan using these input columns and step IDs. Preserve the question's conditions, population, and requested metrics. Return the complete corrected plan."
                }, indent=2, default=str)
                trace["repair_log"].append({"stage": stage, "attempt": attempt + 1,
                                            "errors": errors, "execution": log, "spec": spec,
                                            "action": "stop" if attempt == max_attempts - 1 else "regenerate"})
                inputs["spec_feedback"] = structured_feedback
                inputs["previous_" + spec_key] = spec
                inputs["previous_execution"] = log
            if spec.get("repair_stage") in {"Query_Spec", "Decompose"} or spec.get("missing_requirements"):
                trace["repair_stage"] = "Decompose"
            return {}, errors

        for node in nx.topological_sort(dag):
            node_data = dag.nodes[node]
            op_name = node_data["operator"]
            trace["operator_sequence"].append(op_name)
            print(f"Executing: [{op_name}] at Node '{node}'...")
            operator_started_at = time.perf_counter()

            raw_inputs = node_data.get("explicit_inputs", {})
            if not isinstance(raw_inputs, dict):
                raw_inputs = {}

            inputs = raw_inputs.copy()
            inputs["query"] = initial_query
            inputs["original_query"] = initial_query
            inputs["decomposition"] = decomposition

            branch_scoped_operators = {"Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Refine", "Processing_Spec"}
            subquestion = resolve_subquestion(inputs.get("subquestion_id"))
            if subquestion and op_name in branch_scoped_operators:
                inputs["subquestion"] = subquestion
                inputs["query"] = subquestion.get("question", initial_query)
            inputs["_node_id"] = node
            for k, v in node_data.items():
                if k not in inputs and k not in {"operator", "explicit_inputs"}:
                    inputs[k] = v

            # Subquestion resolution: inherit from ancestors/predecessors if not set directly
            subquestion_id = inputs.get("subquestion_id") or node_data.get("subquestion_id")
            if not subquestion_id:
                for anc in nx.ancestors(dag, node):
                    anc_sub_id = (
                        dag.nodes[anc].get("explicit_inputs", {}).get("subquestion_id")
                        or dag.nodes[anc].get("subquestion_id")
                    )
                    if anc_sub_id:
                        subquestion_id = anc_sub_id
                        break
            if subquestion_id and op_name in branch_scoped_operators:
                inputs["subquestion_id"] = subquestion_id
                subquestion = resolve_subquestion(subquestion_id)
                if subquestion:
                    subq_text = subquestion.get("question") or subquestion.get("text") or initial_query
                    inputs["subquestion"] = subquestion
                    inputs["query"] = subq_text
            elif op_name in {"Validate", "Explain"}:
                inputs["query"] = initial_query
                inputs.pop("subquestion_id", None)
                inputs.pop("subquestion", None)

            #Standard Flow: Get inputs from direct predecessors
            for i, pred in enumerate(dag.predecessors(node)):
                inputs[f"branch_{i+1}_output"] = results_cache[pred]
                if isinstance(results_cache[pred], dict):
                    inputs.update(results_cache[pred])

            predecessor_outputs = [
                results_cache[pred]
                for pred in dag.predecessors(node)
                if isinstance(results_cache.get(pred), dict)
            ]
            if op_name in {"Set_Intersect", "Set_Union", "Set_Difference", "Union", "Difference", "Integrate"} and len(predecessor_outputs) >= 2:
                branch_data_lists = [output.get("data", []) for output in predecessor_outputs]
                inputs.setdefault("branch_data_lists", branch_data_lists)
                inputs.setdefault("list_a", branch_data_lists[0])
                inputs.setdefault("list_b", branch_data_lists[1])

            # THE GLOBAL DATA BUS FIX
            #Ensures intermediate routing nodes don't drop the 'retrieved_tables' context
            # THE GLOBAL DATA BUS FIX (Scoped):
            # Global context (retrieved_tables, decomposition) is safely inherited from any past node
            for past_node, past_result in results_cache.items():
                if isinstance(past_result, dict) and "retrieved_tables" in past_result:
                    if "retrieved_tables" not in inputs:
                        inputs["retrieved_tables"] = []
                    # Safely merge tables without duplicates
                    for tbl in past_result["retrieved_tables"]:
                        if tbl not in inputs["retrieved_tables"]:
                            inputs["retrieved_tables"].append(tbl)
                if isinstance(past_result, dict) and past_result.get("decomposition") and "decomposition" not in inputs:
                    inputs["decomposition"] = past_result["decomposition"]

            # 1. Direct predecessor inheritance (Immediate data flow in DAG)
            predecessors = list(dag.predecessors(node))
            for i, pred in enumerate(predecessors):
                pred_res = results_cache.get(pred)
                inputs[f"branch_{i+1}_output"] = pred_res
                if isinstance(pred_res, dict):
                    if "data" not in inputs and pred_res.get("data") is not None:
                        inputs["data"] = pred_res["data"]
                    if "sparql" not in inputs and pred_res.get("sparql"):
                        inputs["sparql"] = pred_res["sparql"]
                    if "query_spec" not in inputs and pred_res.get("query_spec"):
                        inputs["query_spec"] = pred_res["query_spec"]

            # If multiple branches feed into this operator (e.g. Integrate, Union, Difference)
            if len(predecessors) > 1 and "branch_data_lists" not in inputs:
                inputs["branch_data_lists"] = [
                    results_cache[p].get("data", [])
                    for p in predecessors
                    if isinstance(results_cache.get(p), dict) and isinstance(results_cache[p].get("data"), list)
                ]

            # 2. Reverse topological ancestor fallback (closest ancestors first for missing artifacts)
            topo_order = list(nx.topological_sort(dag))
            node_idx = topo_order.index(node)
            for anc_node in reversed(topo_order[:node_idx]):
                if anc_node in nx.ancestors(dag, node):
                    anc_result = results_cache.get(anc_node)
                    if isinstance(anc_result, dict):
                        if "data" not in inputs and anc_result.get("data") is not None:
                            inputs["data"] = anc_result["data"]
                        if "sparql" not in inputs and anc_result.get("sparql"):
                            inputs["sparql"] = anc_result["sparql"]
                        if "query_spec" not in inputs and anc_result.get("query_spec"):
                            inputs["query_spec"] = anc_result["query_spec"]

            # Global requirements cannot be overwritten by a predecessor's local question.
            inputs["original_query"] = initial_query
            inputs["decomposition"] = decomposition
            inputs["answer_requirements"] = decomposition.get("answer_requirements", {})
            if op_name in {"Final_Spec", "Validate", "Explain"}:
                inputs["query"] = initial_query
            inputs = attach_query_spec_step_inputs(op_name, inputs)

            # Operator execution & self-healing routing
            if op_name not in self.registry:
                raise ValueError(f"Operator {op_name} not found in registry!")

            operator_func = self.registry[op_name]

            # THE SELF-HEALING LOOP (Syntax & DB Errors)
            #max number of retires can be changed as per needs
            if op_name == "Query_Spec":
                result = {}
                for spec_attempt in range(3):
                    try:
                        candidate = operator_func(inputs)
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        candidate = {"query_spec": {"contract_errors": ["Malformed Query_Spec: " + str(exc)]}}
                    candidate_spec = candidate.get("query_spec", {}) if isinstance(candidate, dict) else {}
                    trace["query_specs"].append({
                        "attempt": spec_attempt + 1,
                        "query_spec": candidate_spec,
                    })
                    contract_errors = candidate_spec.get("contract_errors", []) if isinstance(candidate_spec, dict) else ["Query_Spec was not produced."]
                    # Schema/field/filter contracts are checked by Query_Spec itself.
                    # The additional model critic repeatedly required other branches
                    # here. Check SPARQL locally and full-question semantics at Validate.
                    if not contract_errors:
                        result = candidate if isinstance(candidate, dict) else {}
                        break
                    trace["repair_log"].append({
                        "stage": "Query_Spec",
                        "attempt": spec_attempt + 1,
                        "errors": [str(error) for error in contract_errors],
                        "action": "stop" if spec_attempt == 2 else "regenerate",
                    })
                    if spec_attempt == 2:
                        trace["failure_stage"] = "Query_Spec"
                        trace["validation_reason"] = "; ".join(str(error) for error in contract_errors)
                        final_result = self.registry["Explain"]({"query": initial_query, "data": [], "context": "; ".join(str(error) for error in contract_errors)})
                        if isinstance(final_result, dict):
                            final_result["trace"] = trace
                        return final_result
                    print("   [!] Query_Spec contract failed; regenerating raw retrieval plan.")
                    inputs["spec_feedback"] = json.dumps({
                        "stage": "Query_Spec", "attempt": spec_attempt + 1,
                        "errors": [str(error) for error in contract_errors],
                        "hint": "Repair the previous branch contract using the schema. Preserve the assigned source, conditions, and required connection keys."
                    })
                    inputs["previous_query_spec"] = candidate_spec

            elif op_name == "Pre_Scan_Validate":
                _, result, final_result = run_pre_scan_validation_loop(inputs, PRE_SCAN_VALIDATE_MAX_RETRIES)
                if final_result is not None:
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result

            elif op_name == "Scan":
                result, final_result = run_scan_refine_loop(inputs, SCAN_REFINE_MAX_RETRIES)
                if final_result is not None:
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result
                # A nested Query_Spec repair changes the branch contract. Persist the repaired
                # contract on the Scan result so Processing_Spec and Validate do not fall back
                # to the stale Query_Spec ancestor.
                if isinstance(result, dict) and isinstance(inputs.get("query_spec"), dict):
                    result["query_spec"] = inputs["query_spec"]
                    from .execution import row_schema
                    retrieval = inputs["query_spec"].get("retrieval_specs", [{}])[0]
                    if "columns" in result:
                        missing = set(retrieval.get("fields", [])) - set(result["columns"])
                        if missing:
                            return abort_spec("Execution", ["Scan result omits selected fields: " + ", ".join(sorted(missing))])
                    result["sparql"] = result.get("sparql") or inputs.get("sparql", "")
                    trace["executed_sparqls"].append({"node": node, "branch_id": inputs.get("subquestion_id"),
                        "sparql": result["sparql"], "row_count": len(result.get("data", []))})
                    fields = result.get("columns") or ([] if result.get("data") else retrieval.get("fields", []))
                    result["data_schema"] = row_schema(result.get("data", []), fields)

            # THE LOGIC VALIDATION LOOP (Semantic Errors)

            #|| Making validation loop for max_retires
            # THE LOGIC VALIDATION LOOP
            elif op_name == "Processing_Spec":
                from .execution import row_schema
                raw_rows = inputs.get("data", [])
                raw_schema = row_schema(raw_rows, inputs.get("data_schema", []))
                inputs["input_schema"] = raw_schema
                result, errors = run_spec_attempts("Processing_Spec", inputs, {"raw": raw_rows}, {"raw": raw_schema})
                if errors:
                    return abort_spec("Processing_Spec", errors)
                result["processing_context"] = {
                    "raw_data": raw_rows, "raw_schema": raw_schema,
                    "query_spec": inputs.get("query_spec", {}),
                    "executed_sparql": inputs.get("sparql", ""),
                    "subquestion": inputs.get("subquestion", {}),
                    "subquestion_id": inputs.get("subquestion_id"),
                    "decomposition": decomposition,
                }

            elif op_name == "Final_Spec":
                from .execution import row_schema
                processed_datasets, processing_contexts = [], []
                datasets, schemas = {}, {}
                for pred in dag.predecessors(node):
                    predecessor = results_cache.get(pred, {})
                    if not isinstance(predecessor, dict):
                        continue
                    processing_spec = predecessor.get("processing_spec", {})
                    dataset_id = str(processing_spec.get("output_id") or pred)
                    rows = predecessor.get("data", [])
                    datasets[dataset_id] = rows
                    schemas[dataset_id] = row_schema(rows, predecessor.get("data_schema") or processing_spec.get("compiled_output_schema", []))
                    profile = {
                        "id": dataset_id, "fields": schemas[dataset_id],
                        "entity_grain": processing_spec.get("entity_grain", []),
                        "aggregation_lineage": processing_spec.get("aggregation_lineage", []),
                        "aggregation_policy": processing_spec.get("aggregation_policy"),
                    }
                    context = predecessor.get("processing_context")
                    if isinstance(context, dict):
                        processing_contexts.append({"id": dataset_id, **context})
                        profile["branch_id"] = context.get("subquestion_id")
                        profile["question"] = context.get("subquestion", {}).get("question", "")
                        profile["executed_sparql"] = context.get("executed_sparql", "")
                        profile["source_requirement_ids"] = context.get("subquestion", {}).get("requirement_ids", [])
                        profile["retrieval_specs"] = context.get("query_spec", {}).get("retrieval_specs", [])
                    processed_datasets.append(profile)
                inputs["processed_datasets"] = processed_datasets
                trace["branch_profiles"] = processed_datasets
                result, errors = run_spec_attempts("Final_Spec", inputs, datasets, schemas)
                if errors:
                    return abort_spec("Final_Spec", errors)
                result["processed_datasets"] = processed_datasets
                result["branch_datasets"] = datasets
                result["branch_schemas"] = schemas
                result["processing_contexts"] = processing_contexts
                result["answer_requirements"] = decomposition.get("answer_requirements", {})

            elif op_name == "Validate":
                # Execution completion and model review are different facts. A
                # critic cannot discard a computed answer or turn it into an error.
                inputs["branch_evidence"] = inputs.get("processed_datasets", [])
                result = operator_func(inputs)
                review = result.get("validation", {})
                if review.get("status") == "execution_error" or review.get("repair_stage") == "Execution":
                    return abort_spec("Execution", [review.get("reason", "Invalid execution result")])
                trace["validation_is_valid"] = review.get("is_valid")
                trace["validation_reason"] = review.get("reason", "")
                trace["answer_review_status"] = review.get("status") or (
                    "accepted" if review.get("is_valid") is True else
                    "rejected" if review.get("is_valid") is False else "unconfirmed")
                if inputs.get("final_spec"):
                    trace["final_spec"] = inputs["final_spec"]
                    trace["final_operator_data"] = inputs.get("data", [])
                    trace["final_output_produced"] = True

            # Standard Execution for all other operators
            else:
                result = operator_func(inputs)

            # Store Result in Memory
            if isinstance(result, dict):
                if "retrieved_tables" in result:
                    trace["retrieved_classes"] = result.get("retrieved_tables", [])
                if "query_spec" in result:
                    trace["query_spec"] = result.get("query_spec", {})
                    trace["query_specs"].append({
                        "node": node,
                        "subquestion_id": inputs.get("subquestion_id", ""),
                        "query": inputs.get("query", initial_query),
                        "query_spec": result.get("query_spec", {}),
                    })
                    if isinstance(trace["query_spec"], dict):
                        trace["retrieval_specs"] = trace["query_spec"].get("retrieval_specs", [])
                        trace["operator_plan"] = trace["query_spec"].get("operator_plan", [])
                if "processing_spec" in result:
                    trace["processing_specs"].append({
                        "node": node,
                        "subquestion_id": inputs.get("subquestion_id", ""),
                        "processing_spec": result.get("processing_spec", {}),
                        "execution": result.get("processing_execution", []),
                    })
                    trace["final_operator_data"] = result.get("data", [])
                if "final_spec" in result:
                    trace["final_spec"] = result.get("final_spec", {})
                    trace["post_scan_operator_outputs"].extend(result.get("final_execution", []))
                    trace["final_operator_data"] = result.get("data", [])
                    trace["final_output_produced"] = not bool(result.get("execution_errors"))
                if "sparql" in result:
                    trace["generated_sparql"] = result.get("sparql", "")
                    if op_name == "Generate":
                        trace["generated_sparqls"].append({
                            "node": node,
                            "retrieval_spec_id": inputs.get("retrieval_spec", {}).get("id") if isinstance(inputs.get("retrieval_spec"), dict) else "",
                            "sparql": result.get("sparql", ""),
                        })
                if op_name in {
                    "Filter_Aggregate",
                    "Order_By",
                    "Math_Compute",
                    "Set_Intersect",
                    "Set_Union",
                    "Set_Difference",
                    "Union",
                    "Difference",
                    "Integrate",
                }:
                    operator_output = result.get("data", result)
                    trace["post_scan_operator_outputs"].append({
                        "operator": op_name,
                        "row_count": len(operator_output) if isinstance(operator_output, list) else "",
                        "sample": operator_output[:5] if isinstance(operator_output, list) else operator_output,
                    })
                    if result.get("data") is not None:
                        trace["final_operator_data"] = result.get("data", [])
                if op_name == "Pre_Scan_Validate":
                    pre_scan_validation = result.get("pre_scan_validation", {})
                    trace["pre_scan_validation_is_valid"] = pre_scan_validation.get("is_valid", "")
                    trace["pre_scan_validation_reason"] = pre_scan_validation.get("reason", "")
                if op_name == "Scan":
                    trace["scan_status"] = result.get("status", "")
                    trace["scan_row_count"] = result.get("row_count", "")
                    trace["scan_error"] = result.get("error_message", "")
                    trace["scan_raw_rows"] = json.dumps(result.get("data", []), ensure_ascii=False)
                    trace["unknown_terms"] = result.get("unknown_terms", trace["unknown_terms"])
                    trace["term_suggestions"] = result.get("term_suggestions", trace["term_suggestions"])
                    if result.get("status") == "error":
                        trace["failure_stage"] = "Scan"
                if op_name == "Validate":
                    validation = result.get("validation", {})
                    trace["validation_is_valid"] = validation.get("is_valid", "")
                    trace["validation_reason"] = validation.get("reason", "")
                    if validation.get("status") == "execution_error":
                        trace["failure_stage"] = "Execution"
            results_cache[node] = result
            input_data = inputs.get("data", [])
            output_data = result.get("data", []) if isinstance(result, dict) else []
            input_columns = []
            output_columns = []
            if isinstance(input_data, list):
                for row in input_data[:10]:
                    if isinstance(row, dict):
                        input_columns.extend(key for key in row if key not in input_columns)
            if isinstance(output_data, list):
                for row in output_data[:10]:
                    if isinstance(row, dict):
                        output_columns.extend(key for key in row if key not in output_columns)
            trace["operator_audit"].append({
                "node": node,
                "operator": op_name,
                "subquestion_id": inputs.get("subquestion_id", ""),
                "elapsed_ms": round((time.perf_counter() - operator_started_at) * 1000, 2),
                "input_rows": len(input_data) if isinstance(input_data, list) else None,
                "output_rows": len(output_data) if isinstance(output_data, list) else None,
                "input_columns": input_columns,
                "output_columns": output_columns,
                "output_sample": output_data[:5] if isinstance(output_data, list) else None,
            })
            print(f" {op_name} completed.")

        last_node = list(nx.topological_sort(dag))[-1]
        print("--- Execution Complete ---")
        final_result = results_cache[last_node]
        if isinstance(final_result, dict):
            final_result["trace"] = trace
        return final_result
