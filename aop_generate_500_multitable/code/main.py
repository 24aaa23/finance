import os
import re
import sys
import json
import time
import datetime
import pandas as pd
import networkx as nx
import concurrent.futures

from code.config import (
    LOCAL_MODEL, PLANNER_MODEL, REFINE_MODEL, VALIDATE_MODEL, EXPLAIN_MODEL,
    SPARQL_GENERATION_MODEL, PIPELINE_VERSION, TEST_QUERY_LIMIT, TEST_QUERY_OFFSET,
    TEST_MAX_WORKERS, REPORT_FILE, INPUT_SAMPLE_FILE, SCHEMA_FILE, INSTANCE_FILE,
    build_llm_client, build_openai_planner_client, build_openai_sparql_client,
    api_logger, GPT_OSS_MODEL, LLMClient
)
from code.kg.loader import load_rdf_knowledge_graph, setup_rdf_graph, add_cardinality_hints, get_lightweight_table_index
from code.kg.alias import check_and_rebuild_alias_map

# Operators
from code.operators.base import preprocess_user_query
from code.operators.semantic.retrieve import semantic_retrieve
from code.operators.semantic.generate import semantic_generate_sparql
from code.operators.semantic.refine import semantic_refine
from code.operators.semantic.validate import semantic_validate
from code.operators.semantic.explain import semantic_explain_results
from code.operators.semantic.classify import semantic_classify_query
from code.operators.semantic.filter import semantic_filter_aggregate
from code.operators.semantic.order import semantic_order_by
from code.operators.semantic.integrate import semantic_integrate
from code.operators.semantic.link import semantic_link
from code.operators.semantic.extract import semantic_extract_entities

from code.operators.pre_programmed.scan import pre_programmed_scan
from code.operators.pre_programmed.schema import pre_programmed_check_schema
from code.operators.pre_programmed.math import (
    pre_programmed_math_compute, pre_programmed_set_intersect,
    pre_programmed_union, pre_programmed_difference
)

from code.planner.planner import AdvancedAOPPlanner
from code.executor.executor import AOPExecutor
from code.grading.evaluator import evaluate_results


def main():
    print("\n" + "="*50)
    print("INITIALIZING AOP PIPELINE (MODULAR)")
    print("="*50)

    # Ensure alias map is up to date
    check_and_rebuild_alias_map()

    generalist_client = build_llm_client()
    planner_client = build_openai_planner_client()
    sparql_generation_client = build_openai_sparql_client()

    print(f"[SYSTEM] Bedrock region: {os.getenv('BEDROCK_REGION') or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')}")
    print(f"[SYSTEM] GPT-OSS model: {GPT_OSS_MODEL}")
    print(f"[SYSTEM] Default model: {LOCAL_MODEL}")
    print(f"[SYSTEM] Planner model: {PLANNER_MODEL}")
    print(f"[SYSTEM] Refine model: {REFINE_MODEL}")
    print(f"[SYSTEM] Generate model: {SPARQL_GENERATION_MODEL}")
    print(f"[SYSTEM] Validate model: {VALIDATE_MODEL}")
    print(f"[SYSTEM] Explain model: {EXPLAIN_MODEL}")
    print(f"[SYSTEM] DAG planner mode: {os.getenv('DAG_PLANNER_MODE', 'multi_candidate')}")
    print(f"[SYSTEM] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()

    # LOAD RDF KNOWLEDGE GRAPH
    kg_metadata = load_rdf_knowledge_graph(SCHEMA_FILE, INSTANCE_FILE)
    rdf_graph = setup_rdf_graph(INSTANCE_FILE)
    kg_metadata = add_cardinality_hints(kg_metadata, rdf_graph)

    if not kg_metadata:
        print("[!] ERROR: Could not load Knowledge Graph. Please check RDF files.")
        return

    lightweight_index = get_lightweight_table_index(kg_metadata)

    # Operator Registry mapping
    operator_registry = {
        "Retrieve": lambda inputs: semantic_retrieve({**inputs, "table_index": lightweight_index}, generalist_client, LOCAL_MODEL),
        "Generate": lambda inputs: semantic_generate_sparql({**inputs, "global_schema": kg_metadata}, sparql_generation_client, SPARQL_GENERATION_MODEL),
        "Refine": lambda inputs: semantic_refine({**inputs, "global_schema": kg_metadata}, generalist_client, REFINE_MODEL),
        "Scan": lambda inputs: pre_programmed_scan(inputs, rdf_graph),
        "Validate": lambda inputs: semantic_validate(inputs, generalist_client, VALIDATE_MODEL),
        "Explain": lambda inputs: semantic_explain_results(inputs, generalist_client, EXPLAIN_MODEL),
        "Check_Schema": lambda inputs: pre_programmed_check_schema(inputs, rdf_graph),
        "Math_Compute": lambda inputs: pre_programmed_math_compute(inputs),
        "Set_Intersect": lambda inputs: pre_programmed_set_intersect(inputs),
        "Set_Union": lambda inputs: pre_programmed_union(inputs),
        "Set_Difference": lambda inputs: pre_programmed_difference(inputs),
        "Classify": lambda inputs: semantic_classify_query({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Filter_Aggregate": lambda inputs: semantic_filter_aggregate({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Order_By": lambda inputs: semantic_order_by({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Integrate": lambda inputs: semantic_integrate(inputs, generalist_client, LOCAL_MODEL),
        "Link": lambda inputs: semantic_link({**inputs, "schema_details": kg_metadata}, generalist_client, LOCAL_MODEL),
        "Extract": lambda inputs: semantic_extract_entities(inputs, generalist_client, LOCAL_MODEL)
    }

    planner = AdvancedAOPPlanner(planner_client, operator_registry, model=PLANNER_MODEL)
    executor = AOPExecutor(operator_registry, rdf_graph)

    try:
        print(f"\n[SYSTEM] Loading {INPUT_SAMPLE_FILE}...")
        df_all = pd.read_csv(INPUT_SAMPLE_FILE)

        if {"question", "ground_truth_answer"}.issubset(df_all.columns):
            normalized_records = pd.DataFrame({
                "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
                "Question": df_all["question"].astype(str),
                "Ground Truth": df_all["ground_truth_answer"].astype(str),
                "Status": "NEW_BENCHMARK",
            })
            test_records = normalized_records.iloc[TEST_QUERY_OFFSET:TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} benchmark queries.")
        else:
            if "Sample Row ID" not in df_all.columns:
                df_all.insert(0, "Sample Row ID", range(1, len(df_all) + 1))
            if "Status" in df_all.columns:
                df_failed = df_all[df_all['Status'].astype(str).str.strip().str.lower() == 'mismatch'].copy()
            else:
                df_failed = df_all.copy()
            test_records = df_failed.iloc[TEST_QUERY_OFFSET:TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} queries.")
    except Exception as e:
        print(f"\n[!] ERROR loading CSV/Excel file: {e}")
        return

    def run_single_test(record):
        query_start_time = time.perf_counter()
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        time.sleep(2)
        query = record.get('Question', '')
        ground_truth = str(record.get('Ground Truth', ''))
        old_status = record.get('Status', '')
        sample_row_id = record.get('Sample Row ID', '')
        trace = {}
        dag_sequence = ""

        try:
            safe_query = preprocess_user_query(query)
            dag = planner.plan_optimal_dag(safe_query)
            dag_sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
            result = executor.execute_dag(dag, safe_query)
            trace = result.get("trace", {}) if isinstance(result, dict) else {}
            new_output = result.get('final_answer', json.dumps(result))

            trace_fields = {
                "DAG Sequence": dag_sequence,
                "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])),
                "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False),
                "Generated SPARQL": trace.get("generated_sparql", ""),
                "Scan Status": trace.get("scan_status", ""),
                "Scan Row Count": trace.get("scan_row_count", ""),
                "Scan Error": trace.get("scan_error", ""),
                "Scan Raw Rows": trace.get("scan_raw_rows", ""),
                "Unknown Terms": json.dumps(trace.get("unknown_terms", []), ensure_ascii=False),
                "Term Suggestions": json.dumps(trace.get("term_suggestions", {}), ensure_ascii=False),
                "Refine Reason": trace.get("refine_reason", ""),
                "Validation Is Valid": trace.get("validation_is_valid", ""),
                "Validation Reason": trace.get("validation_reason", ""),
                "Self Heal Attempts": trace.get("self_heal_attempts", 0),
                "Short Circuit Stage": trace.get("short_circuit_stage", ""),
                "Failure Stage": trace.get("failure_stage", ""),
            }

            # Call pluggable grading system
            new_status, comments = evaluate_results(query, ground_truth, new_output, generalist_client)

            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                "Old Status": old_status,
                "New Pipeline Result": new_output,
                "New Status": new_status,
                "Comparison / Comments": comments,
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                **trace_fields,
            }
        except Exception as e:
            import traceback; traceback.print_exc()
            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                "Old Status": old_status,
                "New Pipeline Result": f"ERROR: {str(e)}",
                "New Status": "CRASH",
                "Comparison / Comments": "Pipeline threw a fatal exception.",
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                "DAG Sequence": dag_sequence,
                "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])) if trace else "",
                "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False) if trace else "[]",
                "Generated SPARQL": trace.get("generated_sparql", "") if trace else "",
                "Scan Status": trace.get("scan_status", "") if trace else "",
            }

    # Parallel processing loop
    results_list = []
    print(f"\n[SYSTEM] Running retests with Max Workers = {TEST_MAX_WORKERS}...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=TEST_MAX_WORKERS) as pool:
        futures = {pool.submit(run_single_test, rec): rec for rec in test_records}
        completed = 0
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results_list.append(res)
            completed += 1
            print(f"[SYSTEM] [{completed}/{len(test_records)}] Query ID {res['Sample Row ID']} finished with Status = {res['New Status']}. (Elapsed: {res['Elapsed Seconds']}s)")

    # Save to report file
    try:
        df_out = pd.DataFrame(results_list)
        # Reorder columns to match original exactly
        col_order = [
            "Pipeline Version", "Sample Row ID", "Question", "Ground Truth", "New Pipeline Result",
            "New Status", "Old Status", "Comparison / Comments", "Started At", "Elapsed Seconds",
            "DAG Sequence", "AOP Operator Sequence", "Retrieved Classes", "Generated SPARQL",
            "Scan Status", "Scan Row Count", "Scan Error", "Scan Raw Rows", "Unknown Terms",
            "Term Suggestions", "Refine Reason", "Validation Is Valid", "Validation Reason",
            "Self Heal Attempts", "Short Circuit Stage", "Failure Stage"
        ]
        # Keep only existing columns
        col_order = [c for c in col_order if c in df_out.columns]
        df_out = df_out[col_order]
        df_out.to_csv(REPORT_FILE, index=False)
        print(f"\n[SYSTEM] Successfully saved {len(results_list)} results to {REPORT_FILE}")
    except Exception as e:
        print(f"\n[!] ERROR saving report CSV: {e}")

    total_elapsed = round(time.perf_counter() - script_start_time, 2)
    print(f"\n[SYSTEM] Retest complete! Total Elapsed Time: {total_elapsed} seconds.")
    api_logger.save()

if __name__ == "__main__":
    main()
