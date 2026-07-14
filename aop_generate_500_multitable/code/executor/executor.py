import networkx as nx
import time
import rdflib
from typing import Dict, Any

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
            "generated_sparql": "",
            "scan_status": "",
            "scan_row_count": "",
            "scan_error": "",
            "scan_raw_rows": "",
            "unknown_terms": [],
            "term_suggestions": {},
            "refine_reason": "",
            "validation_is_valid": "",
            "validation_reason": "",
            "self_heal_attempts": 0,
            "short_circuit_stage": "",
            "failure_stage": "",
        }

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

            # Operator execution & self-healing routing
            if op_name not in self.registry:
                raise ValueError(f"Operator {op_name} not found in registry!")

            operator_func = self.registry[op_name]

            # THE SELF-HEALING LOOP (Syntax & DB Errors)
            #max number of retires can be changed as per needs
            if op_name == "Scan":
                max_retries = SPARQL_SCAN_MAX_RETRIES
                attempt = 0
                while attempt < max_retries:
                    result = operator_func(inputs)

                    if result.get("status") == "error":
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
                            explain_inputs = {
                                "query": initial_query,
                                "data": [],
                                "context": "A database error prevented data retrieval."
                            }
                            final_result = self.registry["Explain"](explain_inputs)
                            if isinstance(final_result, dict):
                                final_result["trace"] = trace
                            print("--- Execution Complete (Short-circuited) ---")
                            return final_result

                        if not result.get("failed_sparql"):
                            print(f"   [+] No SPARQL was available. Triggering [Generate] again (Attempt {attempt}/{max_retries})...")
                            trace["self_heal_attempts"] += 1
                            regenerate_result = self.registry["Generate"](inputs)
                            inputs["sparql"] = regenerate_result.get("sparql", "")
                            trace["generated_sparql"] = inputs["sparql"]
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
                        print(f"   [+] SPARQL Refined. Retrying [Scan]...")
                    else:
                        break

            # THE LOGIC VALIDATION LOOP (Semantic Errors)

            #|| Making validation loop for max_retires
            # THE LOGIC VALIDATION LOOP
            elif op_name == "Validate":
                max_logic_retries = 3
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
                            "error": "empty result - you hallucinated a property or used exact case-matching",
                            "actual_properties_on_node": actual_props if actual_props else "Unknown - ensure you are using exact prefixes and LCASE()",
                            "hint": "Do NOT guess property names. Use ONLY the listed properties above."
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

                        print(f"   [+] Rerunning [Scan] with updated logic...")
                        scan_result = self.registry["Scan"]({"sparql": new_sparql_result["sparql"]})
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
                if "sparql" in result:
                    trace["generated_sparql"] = result.get("sparql", "")
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

