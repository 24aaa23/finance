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

    def execute_dag(self, dag: nx.DiGraph, initial_query: str) -> Any:
        print("\n--- Starting DAG Execution ---")
        results_cache = {"global_query": initial_query}
        trace = {
            "operator_sequence": [],
            "retrieved_classes": [],
            "query_spec": {},
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
            "short_circuit_stage": "",
            "failure_stage": "",
        }
        operator_plan_usage = {}
        retrieval_spec_usage = 0

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

            if op_name in {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference"}:
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

        for node in nx.topological_sort(dag):
            node_data = dag.nodes[node]
            op_name = node_data["operator"]
            trace["operator_sequence"].append(op_name)
            print(f"Executing: [{op_name}] at Node '{node}'...")

            raw_inputs = node_data.get("explicit_inputs", {})
            if not isinstance(raw_inputs, dict):
                raw_inputs = {}

            inputs = raw_inputs.copy()
            inputs["query"] = initial_query

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
            if op_name in {"Set_Intersect", "Set_Union", "Set_Difference", "Integrate"} and len(predecessor_outputs) >= 2:
                inputs.setdefault("list_a", predecessor_outputs[0].get("data", []))
                inputs.setdefault("list_b", predecessor_outputs[1].get("data", []))

            # THE GLOBAL DATA BUS FIX
            #Ensures intermediate routing nodes don't drop the 'retrieved_tables' context
            for past_node, past_result in results_cache.items():
                if isinstance(past_result, dict) and "retrieved_tables" in past_result:
                    if "retrieved_tables" not in inputs:
                        inputs["retrieved_tables"] = []
                    # Safely merge tables without duplicates
                    for tbl in past_result["retrieved_tables"]:
                        if tbl not in inputs["retrieved_tables"]:
                            inputs["retrieved_tables"].append(tbl)
                if isinstance(past_result, dict) and past_result.get("data") and "data" not in inputs:
                    inputs["data"] = past_result["data"]
                if isinstance(past_result, dict) and past_result.get("sparql") and "sparql" not in inputs:
                    inputs["sparql"] = past_result["sparql"]
                if isinstance(past_result, dict) and past_result.get("query_spec") and "query_spec" not in inputs:
                    inputs["query_spec"] = past_result["query_spec"]

            inputs = attach_query_spec_step_inputs(op_name, inputs)

            # Operator execution & self-healing routing
            if op_name not in self.registry:
                raise ValueError(f"Operator {op_name} not found in registry!")

            operator_func = self.registry[op_name]

            # THE SELF-HEALING LOOP (Syntax & DB Errors)
            #max number of retires can be changed as per needs
            if op_name == "Pre_Scan_Validate":
                _, result, final_result = run_pre_scan_validation_loop(inputs, PRE_SCAN_VALIDATE_MAX_RETRIES)
                if final_result is not None:
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result

            elif op_name == "Scan":
                result, final_result = run_scan_refine_loop(inputs, SCAN_REFINE_MAX_RETRIES)
                if final_result is not None:
                    print("--- Execution Complete (Short-circuited) ---")
                    return final_result

            # THE LOGIC VALIDATION LOOP (Semantic Errors)

            #|| Making validation loop for max_retires
            # THE LOGIC VALIDATION LOOP
            elif op_name == "Validate":
                query_spec_for_validation = inputs.get("query_spec", {})
                operator_first_mode = bool(
                    isinstance(query_spec_for_validation, dict)
                    and query_spec_for_validation.get("operator_plan")
                )
                max_logic_retries = 1 if operator_first_mode else POST_SCAN_VALIDATE_MAX_RETRIES
                attempt = 0

                while attempt < max_logic_retries:
                    result = operator_func(inputs)
                    is_valid = result.get("validation", {}).get("is_valid", False)
                    reason = result.get("validation", {}).get("reason", "")

                    if not is_valid:
                        attempt += 1
                        print(f"   [!] Validation Failed: {reason}")
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
                        inputs["data"] = scan_result.get("data", [])
                        trace["scan_status"] = scan_result.get("status", trace["scan_status"])
                        trace["scan_row_count"] = scan_result.get("row_count", trace["scan_row_count"])
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
                    if isinstance(trace["query_spec"], dict):
                        trace["retrieval_specs"] = trace["query_spec"].get("retrieval_specs", [])
                        trace["operator_plan"] = trace["query_spec"].get("operator_plan", [])
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
            print(f" {op_name} completed.")

        last_node = list(nx.topological_sort(dag))[-1]
        print("--- Execution Complete ---")
        final_result = results_cache[last_node]
        if isinstance(final_result, dict):
            final_result["trace"] = trace
        return final_result
