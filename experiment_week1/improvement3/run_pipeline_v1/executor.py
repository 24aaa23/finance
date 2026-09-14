"""AOP executor."""

from .common import (
    Any,
    Dict,
    POST_SCAN_VALIDATE_MAX_RETRIES,
    PRE_SCAN_VALIDATE_MAX_RETRIES,
    SCAN_REFINE_MAX_RETRIES,
    json,
    nx,
    rdflib,
    re,
    time,
)
from .utils import normalize_classification, sparql_too_similar, validate_sparql_terms


def get_actual_properties_for_failed_query(failed_sparql: str, rdf_graph) -> list:
    """
    Extracts the entity string from a failed SPARQL query, queries the graph
    for that entity, and returns the actual property URIs that exist on it.
    """
    if not rdf_graph:
        return []

    # 1. Extract potential string literals from the failed query (e.g., "INV003" or "INV-003")
    literals = re.findall(r'["\']([^"\']+)["\']', failed_sparql)

    actual_props = set()
    for literal in literals:
        # Skip small/generic strings
        if len(literal) < 3:
            continue

        # 2. Search the physical graph for ANY node that contains this string
        # (Using LCASE to catch "inv003" vs "INV-003" mismatches)
        query = f"""
        SELECT DISTINCT ?p WHERE {{
          ?s ?p ?o .
          FILTER(CONTAINS(LCASE(STR(?o)), "{literal.lower()}"))
        }}
        """
        try:
            for row in rdf_graph.query(query):
                # Clean up the URI to match how the LLM writes prefixes (wm:property)
                prop = str(row[0]).replace("https://wealth.example.org/ontology/", "wm:")
                actual_props.add(prop)
        except Exception:
            continue

        if actual_props:
            break # We found the real properties! Stop searching.

    return list(actual_props)


class AOPExecutor:

    """
    Executes the generated DAG topologically. Manages state transitions,
    the Global Data Bus (context preservation), and the Self-Healing validation loops.
    """
    def __init__(self, operator_registry: Dict[str, Any], rdf_graph: rdflib.Graph):
        self.registry = operator_registry
        self.rdf_graph = rdf_graph

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
            "retrieved_classes": [],
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
            "generated_sparql": "",
            "generated_sparqls": [],
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
                is_valid = bool(check.get("is_valid", False))
                reason = check.get("reason", "")
                rewrite_hint = check.get("rewrite_hint", "")
                severity = str(check.get("severity", "valid" if is_valid else "repairable_warning")).strip().lower()

                trace["pre_scan_validation_is_valid"] = is_valid
                trace["pre_scan_validation_reason"] = reason

                if is_valid or severity in {"valid", "acceptable_warning"}:
                    print("   [+] Pre_Scan_Validate passed.")
                    if severity == "acceptable_warning":
                        trace["pre_scan_warning"] = reason
                    result["sparql"] = inputs.get("sparql", "")
                    return True, result, None

                attempt += 1
                print(f"   [!] Pre_Scan_Validate failed attempt {attempt} ({severity}): {reason}")

                if attempt == max_retries:
                    sparql_to_scan = inputs.get("sparql", "")
                    hard_stop_reasons = []
                    if not sparql_to_scan.strip():
                        hard_stop_reasons.append("empty SPARQL")
                    if "SELECT" not in sparql_to_scan.upper() and "ASK" not in sparql_to_scan.upper():
                        hard_stop_reasons.append("missing SELECT/ASK")
                    term_check = validate_sparql_terms(sparql_to_scan, self.rdf_graph)
                    if not term_check["is_valid"]:
                        hard_stop_reasons.append("unknown RDF terms")
                        trace["unknown_terms"] = term_check["unknown_terms"]
                        trace["term_suggestions"] = term_check["suggestions"]
                    unsafe_join_markers = [
                        "cartesian",
                        "cross join",
                        "unjoined",
                        "without a shared variable",
                        "without a direct relationship",
                        "does not actually join",
                        "no join",
                        "row explosion",
                        "multiply rows",
                        "time out",
                        "timeout",
                    ]
                    if severity == "hard_error" and any(marker in str(reason).lower() for marker in unsafe_join_markers):
                        hard_stop_reasons.append("unsafe unjoined graph pattern")
                    if severity == "hard_error":
                        trace["pre_scan_warning"] = "LLM Pre_Scan hard_error after retries: " + reason

                    if hard_stop_reasons:
                        print(f"   [!] Pre_Scan_Validate found hard stop: {', '.join(hard_stop_reasons)}.")
                        trace["short_circuit_stage"] = "Pre_Scan_Validate"
                        trace["failure_stage"] = "Pre_Scan_Validate"

                        final_result = self.registry["Explain"]({
                            "query": initial_query,
                            "data": [],
                            "context": (
                                "Generated SPARQL was not executable after "
                                f"{max_retries} Pre_Scan_Validate attempt(s): {', '.join(hard_stop_reasons)}."
                            )
                        })
                        if isinstance(final_result, dict):
                            final_result["trace"] = trace
                        result["sparql"] = sparql_to_scan
                        return False, result, final_result

                    print("   [!] Max Pre_Scan_Validate retries reached. Continuing to Scan with warning.")
                    trace["pre_scan_validation_is_valid"] = False
                    trace["pre_scan_validation_reason"] = reason
                    trace["pre_scan_warning"] = reason
                    result["sparql"] = inputs.get("sparql", "")
                    return True, result, None

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
                print("   [+] SPARQL regenerated after Pre_Scan_Validate failure.")

            result["sparql"] = inputs.get("sparql", "")
            return False, result, None

        def run_scan_refine_loop(inputs: Dict[str, Any], max_retries: int) -> tuple[Dict[str, Any], Any]:
            attempt = 0
            result = {}

            while attempt < max_retries:
                result = self.registry["Scan"](inputs)

                if result.get("status") != "error":
                    # A successful HTTP/SPARQL request with no rows can still be a retrieval
                    # planning problem (for example, a mismatched value datatype or an overly
                    # narrow field/filter selection). Re-plan the raw Query_Spec, not the
                    # later Processing/Final specs. The final attempt is preserved as a valid
                    # empty result because some questions genuinely have no matching rows.
                    if result.get("data") or attempt + 1 >= max_retries:
                        return result, None
                    attempt += 1
                    print(f"   [!] Scan returned zero raw rows. Regenerating [Query_Spec] (Attempt {attempt}/{max_retries})...")
                    query_spec_inputs = dict(inputs)
                    query_spec_inputs["spec_feedback"] = json.dumps({
                        "error_type": "empty_raw_scan",
                        "reason": "The executable raw retrieval returned zero rows.",
                        "failed_sparql": inputs.get("sparql", ""),
                        "hint": "Re-evaluate schema-valid source fields, filters, literal datatypes, and date boundaries. Preserve the question's intended constraints; do not invent data."
                    }, indent=2)
                    regenerated_spec = self.registry["Query_Spec"](query_spec_inputs)
                    candidate_spec = regenerated_spec.get("query_spec", {}) if isinstance(regenerated_spec, dict) else {}
                    if isinstance(candidate_spec, dict) and not candidate_spec.get("contract_errors"):
                        inputs["query_spec"] = candidate_spec
                        inputs["logic_feedback"] = query_spec_inputs["spec_feedback"]
                        trace["self_heal_attempts"] += 1
                        regenerated_sparql = self.registry["Generate"](inputs)
                        inputs["sparql"] = regenerated_sparql.get("sparql", "")
                        trace["generated_sparql"] = inputs["sparql"]
                        _, pre_check_result, final_result = run_pre_scan_validation_loop(inputs, PRE_SCAN_VALIDATE_MAX_RETRIES)
                        if final_result is not None:
                            return pre_check_result, final_result
                        inputs["sparql"] = pre_check_result.get("sparql", inputs["sparql"])
                        continue
                    # If an LLM returns an invalid replacement spec, retain the successful
                    # empty result rather than executing an uncontracted query.
                    return result, None

                attempt += 1
                print(f"   [!] SPARQL Error Caught: {result.get('error_message')}")
                trace["scan_status"] = "error"
                trace["scan_error"] = result.get("error_message", "")
                trace["unknown_terms"] = result.get("unknown_terms", trace["unknown_terms"])
                trace["term_suggestions"] = result.get("term_suggestions", trace["term_suggestions"])
                if result.get("unknown_terms"):
                    trace["refine_reason"] = "Unknown RDF terms before Scan"

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

                if not result.get("failed_sparql"):
                    print(f"   [+] No SPARQL was available. Triggering [Generate] again (Attempt {attempt}/{max_retries})...")
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
                    query_spec_inputs["spec_feedback"] = json.dumps({
                        "error_type": "raw_schema_failure",
                        "reason": result.get("error_message", ""),
                        "unknown_terms": result.get("unknown_terms", []),
                        "term_suggestions": result.get("term_suggestions", {}),
                        "failed_sparql": result.get("failed_sparql", ""),
                        "hint": "Choose only schema-valid source class properties and required raw fields."
                    }, indent=2)
                    regenerated_spec = self.registry["Query_Spec"](query_spec_inputs)
                    candidate_spec = regenerated_spec.get("query_spec", {}) if isinstance(regenerated_spec, dict) else {}
                    if isinstance(candidate_spec, dict) and not candidate_spec.get("contract_errors"):
                        inputs["query_spec"] = candidate_spec
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
                logic_feedback = {
                    "unknown_terms": result.get("unknown_terms", []),
                    "suggestions": result.get("term_suggestions", {}),
                    "error_type": "timeout" if is_timeout else "sparql_error",
                    "hint": (
                        "The previous SPARQL timed out. Treat this as a query-plan problem, "
                        "not a syntax problem. Do not produce the same WHERE pattern. Use "
                        "cardinality_hints to avoid flat joins between classes through literal "
                        "properties that are many_per_value on both sides. Prefer direct object "
                        "relationships, fewer classes, or subqueries/pre-aggregation before joining."
                        if is_timeout
                        else "Rewrite using only valid RDF graph terms. Do not invent predicates or classes."
                    )
                }
                refine_inputs = {
                    "failed_sparql": result.get("failed_sparql"),
                    "error_message": result.get("error_message"),
                    "logic_feedback": json.dumps(logic_feedback, indent=2),
                    "query": initial_query,
                    "query_spec": inputs.get("query_spec", {}),
                }
                refine_result = self.registry["Refine"](refine_inputs)
                new_sparql = refine_result.get("sparql", "")
                if is_timeout and sparql_too_similar(result.get("failed_sparql", ""), new_sparql):
                    print("   [!] Refined SPARQL is too similar to the timed-out query. Forcing Generate with stronger feedback.")
                    inputs["logic_feedback"] = json.dumps({
                        "error_type": "similar_timeout_rewrite",
                        "failed_sparql": result.get("failed_sparql", ""),
                        "hint": (
                            "The previous rewrite was too similar to a timed-out query. Produce a "
                            "structurally different SPARQL query. Use cardinality_hints to avoid "
                            "flat many_per_value joins through shared literal properties. Use "
                            "subqueries/pre-aggregation, direct object relationships, or fewer classes."
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
                print(f"   [+] SPARQL Refined. Retrying [Scan]...")

            return result, None

        def execute_spec_steps(spec: Dict[str, Any], datasets: Dict[str, Any]) -> tuple[list, list]:
            """Execute LLM-produced JSON specs through the existing deterministic operators."""
            from .spec_contracts import flatten_identifiers, normalize_spec
            def flatten_input_ids(value: Any) -> list[str]:
                return flatten_identifiers(value)

            spec = normalize_spec(spec)
            available = {name: value for name, value in datasets.items() if isinstance(value, list)}
            execution_log = []
            # Final_Spec maps every requested measure to an explicit operator declaration.
            # Compile those declarations into the existing deterministic Filter_Aggregate
            # operator; this is schema-driven and independent of table/field names.
            compiled_spec = dict(spec)
            final_measures = spec.get("final_measures", []) if isinstance(spec, dict) else []
            if isinstance(final_measures, list) and final_measures:
                merge_steps = list(spec.get("merge_steps", []) or [])
                merge_outputs = [str(step.get("output") or step.get("id") or "") for step in merge_steps if isinstance(step, dict)]
                default_input = merge_outputs[-1] if merge_outputs else (next(iter(available), "raw"))
                measure_steps = []
                for index, measure in enumerate(final_measures, 1):
                    if not isinstance(measure, dict):
                        continue
                    output_column = str(measure.get("output_column") or "")
                    operation = str(measure.get("operation") or "").lower()
                    if not output_column or operation not in {"count", "sum", "avg", "average", "min", "max"}:
                        continue
                    measure_steps.append({
                        "id": f"final_measure_{index}",
                        "operator": "Filter_Aggregate",
                        "input": measure.get("input") or default_input,
                        "operation": operation,
                        "group_by": measure.get("group_by") or spec.get("final_group_by", []),
                        "target_column": measure.get("input_column") or measure.get("target_column"),
                        "output_column": output_column,
                        # The JSON spec has declared the complete measure contract. Do not
                        # let a legacy natural-language convenience heuristic add metrics.
                        "strict_aggregation": True,
                        "output": f"final_measure_{index}",
                    })
                if measure_steps:
                    declared_groupings = {
                        tuple(step["group_by"] if isinstance(step["group_by"], list) else [])
                        for step in measure_steps
                    }
                    if len(declared_groupings) == 1:
                        compiled_spec["final_group_by"] = list(next(iter(declared_groupings)))
                    declared_steps = [step for step in list(spec.get("final_steps", []) or []) if isinstance(step, dict)]
                    # Transformations that create a grouping/measure source must run before
                    # final aggregation. Formulas, filters, ordering, and limiting run after.
                    pre_measure_steps = [step for step in declared_steps if step.get("operator") in {"Date_Extract", "Bucket"}]
                    post_measure_steps = [
                        step for step in declared_steps
                        if step.get("operator") in {"Math_Compute", "Order_By"}
                        or (step.get("operator") == "Filter_Aggregate" and str(step.get("operation", "")).lower() in {"filter", "where"})
                    ]
                    compiled_spec["final_steps"] = pre_measure_steps + measure_steps + post_measure_steps
                    if len(measure_steps) > 1:
                        compiled_spec["final_output"] = ""
                    elif len(measure_steps) == 1 and not derived_steps:
                        compiled_spec["final_output"] = measure_steps[0]["output"]
            spec = compiled_spec
            ordered_steps = list(spec.get("merge_steps", []) or []) + list(spec.get("final_steps", []) or [])
            if "steps" in spec:
                ordered_steps = list(spec.get("steps", []) or [])
            for index, step in enumerate(ordered_steps, 1):
                if not isinstance(step, dict):
                    continue
                op_name = step.get("operator")
                if op_name not in self.registry:
                    continue
                raw_inputs = step.get("inputs", step.get("input", "raw"))
                input_ids = flatten_input_ids(raw_inputs)
                uses_previous = "previous" in input_ids
                input_ids = [item for item in input_ids if item not in {"", "previous"}]
                if uses_previous and available:
                    input_ids.append(next(reversed(available)))
                selected = [available[item] for item in input_ids if item in available]
                missing_inputs = [item for item in input_ids if item not in available]
                if missing_inputs:
                    execution_log.append({
                        "stage": "Spec_Execution", "code": "MISSING_INPUT_DATASET",
                        "step": str(step.get("id") or index), "datasets": missing_inputs,
                    })
                    return [], execution_log
                if not selected and available:
                    selected = [next(reversed(available.values()))]
                step_inputs = {
                    **step,
                    "query": initial_query,
                    "original_query": initial_query,
                    "strict_spec": True,
                }
                if op_name in {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Union", "Difference"}:
                    step_inputs["branch_data_lists"] = selected
                    if selected:
                        step_inputs["list_a"] = selected[0]
                    if len(selected) > 1:
                        step_inputs["list_b"] = selected[1]
                else:
                    step_inputs["data"] = selected[0] if selected else []
                result = self.registry[op_name](step_inputs)
                output = result.get("data", []) if isinstance(result, dict) else []
                output_id = str(step.get("output") or step.get("id") or f"step_{index}")
                available[output_id] = output if isinstance(output, list) else []
                execution_log.append({"id": output_id, "operator": op_name, "row_count": len(available[output_id])})

            final_id = str(spec.get("final_output") or spec.get("output") or "")
            # Independent measures can originate from the same raw branch. Merge terminal
            # measure tables deterministically when the spec leaves final_id empty.
            if not final_id and ordered_steps:
                produced_ids = [str(step.get("output") or step.get("id") or f"step_{index + 1}") for index, step in enumerate(ordered_steps) if isinstance(step, dict)]
                consumed_ids = {
                    item
                    for step in ordered_steps if isinstance(step, dict)
                    for item in flatten_input_ids(step.get("inputs", step.get("input")))
                    if item not in {"", "raw", "previous"}
                }
                terminal_ids = [item for item in produced_ids if item in available and item not in consumed_ids]
                merge_key = spec.get("entity_grain") or spec.get("final_group_by") or []
                if len(terminal_ids) > 1 and merge_key and "Integrate" in self.registry:
                    merged = self.registry["Integrate"]({
                        "branch_data_lists": [available[item] for item in terminal_ids],
                        "join_key": merge_key,
                        "query": initial_query,
                        "original_query": initial_query,
                    })
                    final_id = "__combined_terminal_measures__"
                    available[final_id] = merged.get("data", []) if isinstance(merged, dict) else []
                    execution_log.append({"id": final_id, "operator": "Integrate", "row_count": len(available[final_id])})
                elif len(terminal_ids) > 1 and all(len(available[item]) == 1 for item in terminal_ids):
                    # Global scalar metrics have no grouping key; combine their one-row results
                    # horizontally without inventing a cartesian/raw-data merge.
                    combined = {}
                    for terminal_id in terminal_ids:
                        combined.update(available[terminal_id][0])
                    final_id = "__combined_terminal_measures__"
                    available[final_id] = [combined]
                    execution_log.append({"id": final_id, "operator": "Combine_Scalars", "row_count": 1})
                elif terminal_ids:
                    final_id = terminal_ids[-1]
            data = available.get(final_id)
            if data is None:
                data = next(reversed(available.values())) if available else []
            projection = spec.get("projection", [])
            if isinstance(projection, list) and projection:
                data = [{key: row.get(key) for key in projection if key in row} for row in data if isinstance(row, dict)]
            rounding = spec.get("rounding")
            if isinstance(rounding, (int, float)):
                data = [
                    {key: round(value, int(rounding)) if isinstance(value, float) else value for key, value in row.items()}
                    for row in data if isinstance(row, dict)
                ]
            return data, execution_log

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

            branch_scoped_operators = {"Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Refine", "Check_Schema", "Classify"}
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
                    candidate = operator_func(inputs)
                    candidate_spec = candidate.get("query_spec", {}) if isinstance(candidate, dict) else {}
                    trace["query_specs"].append({
                        "attempt": spec_attempt + 1,
                        "query_spec": candidate_spec,
                    })
                    contract_errors = candidate_spec.get("contract_errors", []) if isinstance(candidate_spec, dict) else ["Query_Spec was not produced."]
                    if not contract_errors and "Query_Spec_Validate" in self.registry:
                        semantic_check = self.registry["Query_Spec_Validate"]({**inputs, "query_spec": candidate_spec})
                        semantic_result = semantic_check.get("query_spec_validation", {}) if isinstance(semantic_check, dict) else {}
                        if not semantic_result.get("is_valid", False):
                            contract_errors = [
                                "Query_Spec semantic coverage failed: " + str(semantic_result.get("reason", "unknown reason")),
                                str(semantic_result.get("repair_hint", "Regenerate the raw retrieval contract.")),
                            ]
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
                        final_result = self.registry["Explain"]({"query": initial_query, "data": [], "context": "; ".join(str(error) for error in contract_errors)})
                        if isinstance(final_result, dict):
                            final_result["trace"] = trace
                        return final_result
                    print("   [!] Query_Spec contract failed; regenerating raw retrieval plan.")
                    inputs["spec_feedback"] = "; ".join(str(error) for error in contract_errors)

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

            # THE LOGIC VALIDATION LOOP (Semantic Errors)

            #|| Making validation loop for max_retires
            # THE LOGIC VALIDATION LOOP
            elif op_name == "Processing_Spec":
                processing_spec = {}
                result = {}
                for spec_attempt in range(3):
                    candidate = operator_func(inputs)
                    candidate_spec = candidate.get("processing_spec", {}) if isinstance(candidate, dict) else {}
                    trace["processing_specs"].append({
                        "attempt": spec_attempt + 1,
                        "processing_spec": candidate_spec,
                    })
                    contract_errors = candidate_spec.get("contract_errors", []) if isinstance(candidate_spec, dict) else []
                    if not contract_errors:
                        result = candidate if isinstance(candidate, dict) else {}
                        processing_spec = candidate_spec
                        break
                    trace["repair_log"].append({
                        "stage": "Processing_Spec",
                        "attempt": spec_attempt + 1,
                        "errors": [str(error) for error in contract_errors],
                        "action": "stop" if spec_attempt == 2 else "regenerate",
                    })
                    if spec_attempt == 2:
                        trace["failure_stage"] = "Processing_Spec"
                        final_result = self.registry["Explain"]({"query": initial_query, "data": [], "context": "; ".join(str(error) for error in contract_errors)})
                        if isinstance(final_result, dict):
                            final_result["trace"] = trace
                        return final_result
                    print("   [!] Processing_Spec contract failed; regenerating the local plan.")
                    inputs["spec_feedback"] = "; ".join(str(error) for error in contract_errors)
                processed_data, execution_log = execute_spec_steps(
                    processing_spec if isinstance(processing_spec, dict) else {},
                    {"raw": inputs.get("data", [])},
                )
                if not isinstance(result, dict):
                    result = {}
                result["data"] = processed_data
                result["processing_execution"] = execution_log
                result["processing_context"] = {
                    "raw_data": inputs.get("data", []),
                    "query_spec": inputs.get("query_spec", {}),
                    "subquestion": inputs.get("subquestion", {}),
                    "subquestion_id": inputs.get("subquestion_id"),
                }

            elif op_name == "Final_Spec":
                processed_datasets = []
                datasets = {}
                processing_contexts = []
                for pred in dag.predecessors(node):
                    predecessor = results_cache.get(pred, {})
                    if not isinstance(predecessor, dict):
                        continue
                    processing_spec = predecessor.get("processing_spec", {})
                    dataset_id = str(
                        processing_spec.get("output_id")
                        if isinstance(processing_spec, dict) else pred
                    )
                    rows = predecessor.get("data", [])
                    datasets[dataset_id] = rows if isinstance(rows, list) else []
                    fields = []
                    for row in datasets[dataset_id][:10]:
                        if isinstance(row, dict):
                            fields.extend(key for key in row if key not in fields)
                    processed_datasets.append({
                        "id": dataset_id,
                        "row_count": len(datasets[dataset_id]),
                        "fields": fields,
                        "sample": datasets[dataset_id][:3],
                    })
                    context = predecessor.get("processing_context")
                    if isinstance(context, dict):
                        processing_contexts.append({"id": dataset_id, **context})
                inputs["processed_datasets"] = processed_datasets
                final_spec = {}
                result = {}
                for spec_attempt in range(3):
                    candidate = operator_func(inputs)
                    candidate_spec = candidate.get("final_spec", {}) if isinstance(candidate, dict) else {}
                    trace["final_spec"] = candidate_spec
                    contract_errors = candidate_spec.get("contract_errors", []) if isinstance(candidate_spec, dict) else []
                    if not contract_errors:
                        result = candidate if isinstance(candidate, dict) else {}
                        final_spec = candidate_spec
                        break
                    trace["repair_log"].append({
                        "stage": "Final_Spec",
                        "attempt": spec_attempt + 1,
                        "errors": [str(error) for error in contract_errors],
                        "action": "stop" if spec_attempt == 2 else "regenerate",
                    })
                    if spec_attempt == 2:
                        trace["failure_stage"] = "Final_Spec"
                        final_result = self.registry["Explain"]({"query": initial_query, "data": [], "context": "; ".join(str(error) for error in contract_errors)})
                        if isinstance(final_result, dict):
                            final_result["trace"] = trace
                        return final_result
                    print("   [!] Final_Spec omitted a branch; regenerating the final plan once.")
                    inputs["spec_feedback"] = "; ".join(str(error) for error in contract_errors)
                final_data, execution_log = execute_spec_steps(
                    final_spec if isinstance(final_spec, dict) else {},
                    datasets,
                )
                if not isinstance(result, dict):
                    result = {}
                result["data"] = final_data
                result["final_execution"] = execution_log
                # Internal-only context for stage-specific validation repair. It is not written
                # to the final-only CSV report.
                result["processed_datasets"] = processed_datasets
                result["branch_datasets"] = datasets
                result["processing_contexts"] = processing_contexts

            elif op_name == "Validate":
                query_spec_for_validation = inputs.get("query_spec", {})
                # A Final_Spec has already combined every branch. Regenerating the last branch's
                # SPARQL cannot repair a final merge/aggregation mistake.
                # A final-answer failure must repair Final_Spec itself, not immediately give up
                # or rewrite already-correct raw SPARQL.
                # Three validations means two real Final_Spec repairs after the original plan.
                max_logic_retries = 3 if inputs.get("final_spec") else POST_SCAN_VALIDATE_MAX_RETRIES
                attempt = 0

                # Ensure Validate knows about all downstream operators executed in the DAG
                if not inputs.get("operator_plan"):
                    dag_ops = []
                    topo = list(nx.topological_sort(dag))
                    c_idx = topo.index(node)
                    for anc in topo[:c_idx]:
                        op = dag.nodes[anc].get("operator")
                        if op in {"Filter_Aggregate", "Order_By", "Math_Compute", "Integrate", "Set_Intersect", "Union", "Difference"}:
                            exp_in = dag.nodes[anc].get("explicit_inputs", {})
                            dag_ops.append({"operator": op, **exp_in})
                    if dag_ops:
                        inputs["operator_plan"] = dag_ops

                while attempt < max_logic_retries:
                    result = operator_func(inputs)
                    is_valid = result.get("validation", {}).get("is_valid", False)
                    reason = result.get("validation", {}).get("reason", "")
                    trace["validation_is_valid"] = is_valid
                    trace["validation_reason"] = reason

                    if not is_valid:
                        attempt += 1
                        print(f"   [!] Validation Failed: {reason}")

                        if inputs.get("final_spec") and attempt < max_logic_retries:
                            processed_datasets = inputs.get("processed_datasets", [])
                            branch_datasets = inputs.get("branch_datasets", {})
                            if isinstance(processed_datasets, list) and isinstance(branch_datasets, dict):
                                processing_contexts = inputs.get("processing_contexts", [])
                                # Route by declared schema lineage, never finance words in the
                                # validation prose. Processing is repaired only if a declared
                                # Final_Spec measure requires an input column absent from its
                                # processed branch; all other failures stay at Final_Spec.
                                fields_by_dataset = {
                                    str(profile.get("id")): set(profile.get("fields", []))
                                    for profile in processed_datasets
                                    if isinstance(profile, dict) and profile.get("id")
                                }
                                local_contract_missing = False
                                current_final_spec = inputs.get("final_spec", {})
                                for measure in current_final_spec.get("final_measures", []) if isinstance(current_final_spec, dict) else []:
                                    if not isinstance(measure, dict):
                                        continue
                                    source_id = str(measure.get("input") or "")
                                    source_column = str(measure.get("input_column") or measure.get("target_column") or "")
                                    if source_id and source_column and source_id in fields_by_dataset:
                                        if source_column not in fields_by_dataset[source_id]:
                                            local_contract_missing = True
                                            break
                                if local_contract_missing and isinstance(processing_contexts, list) and processing_contexts:
                                    print("   [+] Regenerating affected branch-local Processing_Spec plans...")
                                    rebuilt_datasets = {}
                                    rebuilt_profiles = []
                                    for context in processing_contexts:
                                        if not isinstance(context, dict) or not context.get("id"):
                                            continue
                                        dataset_id = str(context["id"])
                                        local_inputs = {
                                            "query": initial_query,
                                            "original_query": initial_query,
                                            "query_spec": context.get("query_spec", {}),
                                            "subquestion": context.get("subquestion", {}),
                                            "subquestion_id": context.get("subquestion_id"),
                                            "data": context.get("raw_data", []),
                                            "spec_feedback": "Validation reported a missing or incorrect local aggregation: " + str(reason),
                                        }
                                        rebuilt = self.registry["Processing_Spec"](local_inputs)
                                        rebuilt_spec = rebuilt.get("processing_spec", {}) if isinstance(rebuilt, dict) else {}
                                        if not isinstance(rebuilt_spec, dict) or rebuilt_spec.get("contract_errors"):
                                            rebuilt_datasets = {}
                                            break
                                        rebuilt_spec["output_id"] = dataset_id
                                        rebuilt_rows, _ = execute_spec_steps(rebuilt_spec, {"raw": local_inputs["data"]})
                                        rebuilt_datasets[dataset_id] = rebuilt_rows
                                        fields = []
                                        for row in rebuilt_rows[:10]:
                                            if isinstance(row, dict):
                                                fields.extend(key for key in row if key not in fields)
                                        rebuilt_profiles.append({
                                            "id": dataset_id,
                                            "row_count": len(rebuilt_rows),
                                            "fields": fields,
                                            "sample": rebuilt_rows[:3],
                                        })
                                    if rebuilt_datasets and len(rebuilt_datasets) == len(processing_contexts):
                                        branch_datasets = rebuilt_datasets
                                        processed_datasets = rebuilt_profiles
                                        inputs["branch_datasets"] = branch_datasets
                                        inputs["processed_datasets"] = processed_datasets
                                print(f"   [+] Regenerating [Final_Spec] from validation feedback (Attempt {attempt}/{max_logic_retries - 1})...")
                                repair_inputs = {
                                    "query": initial_query,
                                    "original_query": initial_query,
                                    "decomposition": decomposition,
                                    "processed_datasets": processed_datasets,
                                    "previous_final_spec": inputs.get("final_spec", {}),
                                    "previous_final_execution": inputs.get("final_execution", []),
                                    "spec_feedback": (
                                        "Validation rejected the final answer: " + str(reason) +
                                        ". Use every processed dataset and correct the merge, final aggregation, ranking, or projection."
                                    ),
                                }
                                repaired = self.registry["Final_Spec"](repair_inputs)
                                repaired_spec = repaired.get("final_spec", {}) if isinstance(repaired, dict) else {}
                                repair_errors = repaired_spec.get("contract_errors", []) if isinstance(repaired_spec, dict) else []
                                if not repair_errors:
                                    healed_data, healed_execution = execute_spec_steps(repaired_spec, branch_datasets)
                                    inputs["final_spec"] = repaired_spec
                                    inputs["data"] = healed_data
                                    inputs["final_execution"] = healed_execution
                                    trace["final_operator_data"] = healed_data
                                    trace["self_heal_attempts"] += 1
                                    continue
                                print("   [!] Repaired Final_Spec still violates its branch contract.")
                                # This is a final-stage plan failure. Retrying raw SPARQL would
                                # only re-fetch the same branch rows and cannot repair the plan.
                                # Continue to the next Final_Spec repair attempt instead.
                                continue

                        if inputs.get("final_spec"):
                            # Final-stage validation has its own three-attempt loop above.
                            # Do not fall through to Generate/Scan after those attempts.
                            print("   [!] Final_Spec retries exhausted. Short-circuiting directly to Explain.")
                            trace["short_circuit_stage"] = "Final_Spec"
                            trace["failure_stage"] = "Final_Spec"
                            final_result = self.registry["Explain"]({
                                "query": initial_query,
                                "data": inputs.get("data", []),
                            })
                            if isinstance(final_result, dict):
                                final_result["trace"] = trace
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result

                        failed_sparql = inputs.get("sparql", "")

                        if not failed_sparql:
                            print("   [-] No SPARQL found to refine. Skipping self-healing.")
                            result = {"data": inputs.get("data", [])}
                            break

                        if attempt == max_logic_retries:
                            print("   [!] Max logic retries reached. Short-circuiting directly to Explain.")
                            trace["short_circuit_stage"] = "Validate"
                            trace["failure_stage"] = "Validate"
                            if inputs.get("data"):
                                explain_inputs = {
                                    "query": initial_query,
                                    "data": inputs.get("data", []),
                                }
                            else:
                                explain_inputs = {
                                    "query": initial_query,
                                    "data": [],
                                    "context": "No data was found in the knowledge graph. The requested entity may not exist."
                                }
                            final_result = self.registry["Explain"](explain_inputs)
                            if isinstance(final_result, dict):
                                final_result["trace"] = trace
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result

                        print(f"   [+] Fetching actual properties from KG for failed query...")
                        actual_props = get_actual_properties_for_failed_query(failed_sparql, self.rdf_graph)

                        logic_feedback = {
                            "error_type": "post_scan_validation_failed",
                            "reason": reason,
                            "query_spec": inputs.get("query_spec", {}),
                            "failed_sparql": failed_sparql,
                            "actual_properties_on_node": actual_props if actual_props else "Unknown - ensure you are using exact prefixes and LCASE()",
                            "hint": (
                                "Regenerate SPARQL so that it satisfies Query_Spec and fixes the "
                                "post-scan validation failure. The new query must still pass Pre_Scan_Validate."
                            )
                        }
                        trace["refine_reason"] = "Validation failed or zero rows"

                        print(f"   [+] Triggering [Generate] to rewrite logic (Attempt {attempt}/{max_logic_retries})...")

                        # Pass the rich JSON feedback back to Generate
                        inputs["logic_feedback"] = json.dumps(logic_feedback, indent=2)

                        # Generate new SPARQL with awareness of the actual properties
                        trace["self_heal_attempts"] += 1
                        new_sparql_result = self.registry["Generate"](inputs)
                        inputs["sparql"] = new_sparql_result["sparql"]
                        trace["generated_sparql"] = inputs["sparql"]

                        _, pre_check_result, final_result = run_pre_scan_validation_loop(inputs, PRE_SCAN_VALIDATE_MAX_RETRIES)
                        if final_result is not None:
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result
                        inputs["sparql"] = pre_check_result.get("sparql", inputs["sparql"])

                        print(f"   [+] Rerunning [Scan] with updated logic...")
                        scan_result, final_result = run_scan_refine_loop(inputs, SCAN_REFINE_MAX_RETRIES)
                        if final_result is not None:
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result
                        healed_data = scan_result.get("data", [])

                        # 1. Re-run intermediate post-scan DAG nodes between Scan and Validate
                        post_scan_ops_rerun = False
                        topo_order = list(nx.topological_sort(dag))
                        curr_idx = topo_order.index(node)
                        for intermediate_node in topo_order[:curr_idx]:
                            inter_data = dag.nodes[intermediate_node]
                            inter_op = inter_data.get("operator")
                            if inter_op in {"Filter_Aggregate", "Order_By", "Math_Compute", "Integrate", "Union", "Difference"}:
                                if intermediate_node in nx.ancestors(dag, node):
                                    post_scan_ops_rerun = True
                                    inter_inputs = inter_data.get("explicit_inputs", {}).copy()
                                    step_inputs = {**inputs, **inter_inputs, "data": healed_data}
                                    op_res = self.registry[inter_op](step_inputs)
                                    if isinstance(op_res, dict) and "data" in op_res:
                                        healed_data = op_res["data"]
                                        results_cache[intermediate_node] = op_res

                        # 2. If no intermediate DAG nodes were rerun, check query_spec operator_plan
                        if not post_scan_ops_rerun and isinstance(query_spec_for_validation, dict):
                            for step in query_spec_for_validation.get("operator_plan", []):
                                if isinstance(step, dict):
                                    step_op = step.get("operator")
                                    if step_op in self.registry and step_op in {"Filter_Aggregate", "Order_By", "Math_Compute"}:
                                        step_inputs = {**inputs, **step, "data": healed_data}
                                        op_res = self.registry[step_op](step_inputs)
                                        if isinstance(op_res, dict) and "data" in op_res:
                                            healed_data = op_res["data"]
                        inputs["data"] = healed_data
                        trace["final_operator_data"] = healed_data
                        trace["scan_status"] = scan_result.get("status", trace["scan_status"])
                        trace["scan_row_count"] = len(healed_data)
                        trace["scan_error"] = scan_result.get("error_message", trace["scan_error"])
                        trace["scan_raw_rows"] = json.dumps(scan_result.get("data", []), ensure_ascii=False)
                        trace["unknown_terms"] = scan_result.get("unknown_terms", trace["unknown_terms"])
                        trace["term_suggestions"] = scan_result.get("term_suggestions", trace["term_suggestions"])
                    else:
                        print("   [+] Validation Passed.")
                        break

            # THE ILLEGAL MATH SHORT-CIRCUIT
            elif op_name == "Classify":
                result = operator_func(inputs)
                classification = normalize_classification(result.get("classification", {}), initial_query)
                result["classification"] = classification
                intent = classification.get("intent", "")
                reason = classification.get("reason", "")

                if intent == "out_of_domain_unanswerable":
                    print(f"   [!] Classify caught unanswerable math logic: {reason}. Short-circuiting to Explain.")
                    trace["short_circuit_stage"] = "Classify"
                    explain_inputs = {
                        "query": initial_query,
                        "data": [],
                        "context": f"The query asks for a mathematical calculation on a text field, which is not supported by the data model. Reason: {reason}"
                    }
                    final_result = self.registry["Explain"](explain_inputs)
                    if isinstance(final_result, dict):
                        final_result["trace"] = trace
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result
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
                    if validation and not validation.get("is_valid", False):
                        trace["failure_stage"] = "Validate"
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
