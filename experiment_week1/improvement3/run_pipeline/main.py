"""Run the improvement3 decompose-first modular AOP pipeline."""

import concurrent.futures
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .common import (
    EXPLAIN_MODEL,
    FUSEKI_ENDPOINT,
    FUSEKI_SCAN_TIMEOUT_SECONDS,
    GPT_OSS_MODEL,
    INPUT_SAMPLE_FILE,
    INSTANCE_FILE,
    PIPELINE_VERSION,
    PLANNER_MODEL,
    QUERY_SPEC_MODEL,
    RAG_MODEL,
    REFINE_MODEL,
    REPORT_FILE,
    SCHEMA_FILE,
    SPARQL_GENERATION_MODEL,
    TEST_MAX_WORKERS,
    TEST_QUERY_LIMIT,
    TEST_QUERY_OFFSET,
    VALIDATE_MODEL,
    api_logger,
    datetime,
    json,
    nx,
    os,
    pd,
    time,
)
from .clients import build_gpt_oss_client
from .reporting import load_input_samples
from .schema_loader import (
    add_cardinality_hints,
    get_lightweight_table_index,
    load_rdf_knowledge_graph,
    setup_rdf_graph,
)
from .utils import is_quota_exhaustion_error, is_transient_connection_error, preprocess_user_query
from .llm_operators import (
    semantic_retrieve,
    semantic_decompose_question,
    semantic_build_query_spec,
    semantic_query_spec_validate,
    semantic_build_processing_spec,
    semantic_build_final_spec,
    semantic_generate_sparql,
    semantic_pre_scan_validate,
    semantic_refine,
    semantic_validate,
    semantic_explain_results,
    semantic_classify_query,
    semantic_filter_aggregate,
    semantic_order_by,
    semantic_integrate,
    semantic_link,
    semantic_extract_entities,
)
from .non_llm_operators import (
    pre_programmed_scan,
    pre_programmed_check_schema,
    pre_programmed_math_compute,
    pre_programmed_set_intersect,
    pre_programmed_union,
    pre_programmed_difference,
    pre_programmed_date_extract,
)
from .non_llm_operators.fuseki import check_fuseki_health
from .planner import AdvancedAOPPlanner
from .executor import AOPExecutor


def main():
    print("\n" + "="*50)
    print("INITIALIZING AOP PIPELINE")
    print("="*50)

    #CONFIGURATION & API SETUP
    print("[SYSTEM] Scan backend: Apache Jena Fuseki")
    print(f"[SYSTEM] Fuseki endpoint: {FUSEKI_ENDPOINT}")
    print(f"[SYSTEM] Fuseki scan timeout: {FUSEKI_SCAN_TIMEOUT_SECONDS:g} seconds")
    check_fuseki_health()

    gpt_oss_client = build_gpt_oss_client()
    retrieve_client = gpt_oss_client
    planner_client = gpt_oss_client
    query_spec_client = gpt_oss_client
    sparql_generation_client = gpt_oss_client
    validate_client = gpt_oss_client
    refine_client = gpt_oss_client
    explain_client = gpt_oss_client
    target_client = gpt_oss_client
    TARGET_MODEL = GPT_OSS_MODEL
    print(f"[SYSTEM] GPT-OSS endpoint: {os.getenv('BEDROCK_BASE_URL') or 'bedrock-runtime regional OpenAI-compatible endpoint'}")
    print(f"[SYSTEM] GPT-OSS model: {GPT_OSS_MODEL}")
    print(f"[SYSTEM] RAG/Retrieve model: {RAG_MODEL}")
    print(f"[SYSTEM] Planner model: {PLANNER_MODEL}")
    print(f"[SYSTEM] Query_Spec model: {QUERY_SPEC_MODEL}")
    print(f"[SYSTEM] Refine model: {REFINE_MODEL}")
    print(f"[SYSTEM] Generate model: {SPARQL_GENERATION_MODEL}")
    print(f"[SYSTEM] Validate model: {VALIDATE_MODEL}")
    print(f"[SYSTEM] Explain model: {EXPLAIN_MODEL}")
    print("[SYSTEM] Grading: disabled in pipeline runner; use separate grade_*.py")
    print(f"[SYSTEM] DAG planner mode: {os.getenv('DAG_PLANNER_MODE', 'multi_candidate')}")
    print(f"[SYSTEM] Report file: {REPORT_FILE}")
    script_start_time = time.perf_counter()



    # LOAD RDF KNOWLEDGE GRAPH
    schema_file = SCHEMA_FILE
    instance_file = INSTANCE_FILE

    kg_metadata = load_rdf_knowledge_graph(schema_file, instance_file)
    rdf_graph = setup_rdf_graph(instance_file)
    kg_metadata = add_cardinality_hints(kg_metadata, rdf_graph)

    if not kg_metadata:
        print("[!] ERROR: Could not load Knowledge Graph. Please check RDF files.")
        return

    # Create the token-saving index
    lightweight_index = get_lightweight_table_index(kg_metadata)




    #INITIALIZE OPERATOR REGISTRY

    operator_registry = {
        # Retrieval & Generation
        # Pass the full schema as 'global_schema' so Generate/Refine can prune it dynamically
        "Retrieve": lambda inputs: semantic_retrieve({**inputs, "table_index": lightweight_index}, retrieve_client, RAG_MODEL),
        "Decompose": lambda inputs: semantic_decompose_question({**inputs, "global_schema": kg_metadata}, target_client, TARGET_MODEL),
        "Query_Spec": lambda inputs: semantic_build_query_spec({**inputs, "global_schema": kg_metadata}, query_spec_client, QUERY_SPEC_MODEL),
        "Query_Spec_Validate": lambda inputs: semantic_query_spec_validate({**inputs, "global_schema": kg_metadata}, validate_client, VALIDATE_MODEL),
        "Processing_Spec": lambda inputs: semantic_build_processing_spec(inputs, target_client, TARGET_MODEL),
        "Final_Spec": lambda inputs: semantic_build_final_spec(inputs, target_client, TARGET_MODEL),
        "Generate": lambda inputs: semantic_generate_sparql(
            {**inputs, "global_schema": kg_metadata},
            sparql_generation_client,
            SPARQL_GENERATION_MODEL,
        ),
        "Pre_Scan_Validate": lambda inputs: semantic_pre_scan_validate(inputs, validate_client, VALIDATE_MODEL),
        "Refine": lambda inputs: semantic_refine({**inputs, "global_schema": kg_metadata}, refine_client, REFINE_MODEL),

        # Execution & Validation
        "Scan": lambda inputs: pre_programmed_scan(inputs, rdf_graph),
        "Validate": lambda inputs: semantic_validate(inputs, validate_client, VALIDATE_MODEL),
        "Explain": lambda inputs: semantic_explain_results(inputs, explain_client, EXPLAIN_MODEL),
        "Check_Schema": lambda inputs: pre_programmed_check_schema(inputs, rdf_graph),

        # Mathematical & Set Operations
        "Math_Compute": lambda inputs: pre_programmed_math_compute(inputs),
        "Date_Extract": lambda inputs: pre_programmed_date_extract(inputs),
        "Set_Intersect": lambda inputs: pre_programmed_set_intersect(inputs),
        "Set_Union": lambda inputs: pre_programmed_union(inputs),
        "Set_Difference": lambda inputs: pre_programmed_difference(inputs),
        "Union": lambda inputs: pre_programmed_union(inputs),
        "Difference": lambda inputs: pre_programmed_difference(inputs),

        # Logic & Routing
        "Classify": lambda inputs: semantic_classify_query({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Filter_Aggregate": lambda inputs: semantic_filter_aggregate({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Order_By": lambda inputs: semantic_order_by({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Integrate": lambda inputs: semantic_integrate(inputs, target_client, TARGET_MODEL),
        "Link": lambda inputs: semantic_link({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Extract": lambda inputs: semantic_extract_entities(inputs, target_client, TARGET_MODEL)
    }

    planner = AdvancedAOPPlanner(planner_client, operator_registry, model=PLANNER_MODEL)
    executor = AOPExecutor(operator_registry, rdf_graph)



# === 1. LOAD AND FILTER FAILED QUERIES ===

    # Updated to point to your new Excel file
    sample_file = INPUT_SAMPLE_FILE

    try:

        print(f"\n[SYSTEM] Loading {sample_file}...")

        df_all = load_input_samples(sample_file)

        if {"question", "ground_truth_answer"}.issubset(df_all.columns):
            normalized_records = pd.DataFrame({
                "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
                "Question": df_all["question"].astype(str),
                "Ground Truth": df_all["ground_truth_answer"].astype(str),
                "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
                "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
                "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
                "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
                "Status": "NEW_BENCHMARK",
            })
            test_records = normalized_records.iloc[TEST_QUERY_OFFSET:TEST_QUERY_OFFSET + TEST_QUERY_LIMIT].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} benchmark queries from the new dataset.")
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
        print(f"\n[!] ERROR loading Excel file: {e}")
        return

    def run_single_test(record):
        query_start_time = time.perf_counter()
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        time.sleep(2)
        query = record.get('Question', '')
        ground_truth = str(record.get('Ground Truth', ''))
        old_status = record.get('Status', '')
        sample_row_id = record.get('Sample Row ID', '')
        row_metadata = {
            "Difficulty": record.get('Difficulty', ''),
            "Category": record.get('Category', ''),
            "Query Type": record.get('Query Type', ''),
            "Source CSV": record.get('Source CSV', ''),
        }
        trace = {}
        dag_sequence = ""

        try:
            # Sanitize and Execute
            safe_query = preprocess_user_query(query)
            retrieve_result = operator_registry["Retrieve"]({"query": safe_query})
            decomposition_result = operator_registry["Decompose"]({
                "query": safe_query,
                **retrieve_result,
            })
            decomposition = decomposition_result.get("selected_decomposition", {})
            dag = planner.plan_optimal_dag_from_decomposition(safe_query, decomposition)
            dag_sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
            result = executor.execute_dag(
                dag,
                safe_query,
                decomposition=decomposition,
                initial_context={
                    **retrieve_result,
                    "decomposition_candidates": decomposition_result.get("decomposition_candidates", []),
                },
            )
            trace = result.get("trace", {}) if isinstance(result, dict) else {}
            if isinstance(trace, dict):
                trace.setdefault("retrieved_classes", retrieve_result.get("retrieved_tables", []))
                trace.setdefault("decomposition", decomposition)
                trace.setdefault("decomposition_candidates", decomposition_result.get("decomposition_candidates", []))
                trace.setdefault("subquestions", decomposition.get("subquestions", []) if isinstance(decomposition, dict) else [])
            if trace.get("final_operator_data") and trace["final_operator_data"] != []:
                final_data_json = json.dumps(trace["final_operator_data"], ensure_ascii=False)
                new_output = final_data_json
            else:
                new_output = trace.get("scan_raw_rows") or result.get('final_answer', json.dumps(result))

            trace_fields = {
                "Scan Status": trace.get("scan_status", ""),
                "Scan Error": trace.get("scan_error", ""),
                "Validation Is Valid": trace.get("validation_is_valid", ""),
                "Validation Reason": trace.get("validation_reason", ""),
                "Failure Stage": trace.get("failure_stage", ""),
            }

            failure_stage = str(trace.get("failure_stage", "") or trace.get("short_circuit_stage", ""))
            if failure_stage == "Pre_Scan_Validate":
                elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
                return {
                    "Pipeline Version": PIPELINE_VERSION,
                    "Sample Row ID": sample_row_id,
                    "Question": query,
                    "Ground Truth": ground_truth,
                    **row_metadata,
                    "Old Status": old_status,
                    "New Pipeline Result": new_output,
                    "New Status": "PRE_SCAN_ERROR",
                    "Comparison / Comments": "Stopped before Scan because generated SPARQL failed Pre_Scan_Validate after retries.",
                    "Started At": started_at,
                    "Elapsed Seconds": elapsed_seconds,
                    **trace_fields,
                }

            if failure_stage == "Scan" or str(trace.get("scan_status", "")).lower() == "error":
                elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
                return {
                    "Pipeline Version": PIPELINE_VERSION,
                    "Sample Row ID": sample_row_id,
                    "Question": query,
                    "Ground Truth": ground_truth,
                    **row_metadata,
                    "Old Status": old_status,
                    "New Pipeline Result": new_output,
                    "New Status": "SCAN_ERROR",
                    "Comparison / Comments": "Scan could not complete successfully after retries.",
                    "Started At": started_at,
                    "Elapsed Seconds": elapsed_seconds,
                    **trace_fields,
                }

            stage_statuses = {
                "Query_Spec": "QUERY_SPEC_ERROR",
                "Processing_Spec": "PROCESSING_SPEC_ERROR",
                "Final_Spec": "FINAL_SPEC_ERROR",
            }
            if failure_stage in stage_statuses or trace.get("validation_is_valid") is False:
                elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
                effective_stage = failure_stage or "Final_Spec"
                return {
                    "Pipeline Version": PIPELINE_VERSION,
                    "Sample Row ID": sample_row_id,
                    "Question": query,
                    "Ground Truth": ground_truth,
                    **row_metadata,
                    "Old Status": old_status,
                    "New Pipeline Result": new_output,
                    "New Status": stage_statuses.get(effective_stage, "FINAL_SPEC_ERROR"),
                    "Comparison / Comments": "The pipeline stopped after a structured spec or final validation failure.",
                    "Started At": started_at,
                    "Elapsed Seconds": elapsed_seconds,
                    **trace_fields,
                }

            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                **row_metadata,
                "Old Status": old_status,
                "New Pipeline Result": new_output,
                "New Status": "PIPELINE_SUCCESS",
                "Comparison / Comments": "Raw pipeline output saved; run the separate grader script for MATCH/MISMATCH/PARTIAL.",
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                **trace_fields,
            }

        except Exception as e:
            elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
            quota_exhausted = is_quota_exhaustion_error(e)
            transient_error = is_transient_connection_error(e)
            return {
                "Pipeline Version": PIPELINE_VERSION,
                "Sample Row ID": sample_row_id,
                "Question": query,
                "Ground Truth": ground_truth,
                **row_metadata,
                "Old Status": old_status,
                "New Pipeline Result": f"ERROR: {str(e)}",
                "New Status": "QUOTA_EXHAUSTED" if quota_exhausted else ("TRANSIENT_ERROR" if transient_error else "CRASH"),
                "Comparison / Comments": (
                    "OpenAI quota was exhausted; stopping the run without marking remaining rows."
                    if quota_exhausted
                    else ("Temporary service or connection failure; this row will be retried on resume."
                          if transient_error else "Pipeline threw a fatal exception.")
                ),
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                "DAG Sequence": dag_sequence,
                "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])) if trace else "",
                "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False) if trace else "[]",
                "Decomposition Candidates": json.dumps(trace.get("decomposition_candidates", []), ensure_ascii=False) if trace else "[]",
                "Selected Decomposition": json.dumps(trace.get("decomposition", {}), ensure_ascii=False) if trace else "{}",
                "Subquestions": json.dumps(trace.get("subquestions", []), ensure_ascii=False) if trace else "[]",
                "Query Spec": json.dumps(trace.get("query_spec", {}), ensure_ascii=False) if trace else "{}",
                "Query Specs": json.dumps(trace.get("query_specs", []), ensure_ascii=False) if trace else "[]",
                "Retrieval Specs": json.dumps(trace.get("retrieval_specs", []), ensure_ascii=False) if trace else "[]",
                "Operator Plan": json.dumps(trace.get("operator_plan", []), ensure_ascii=False) if trace else "[]",
                "Generated SPARQL": trace.get("generated_sparql", "") if trace else "",
                "Generated SPARQLs": json.dumps(trace.get("generated_sparqls", []), ensure_ascii=False) if trace else "[]",
                "Post Scan Operator Outputs": json.dumps(trace.get("post_scan_operator_outputs", []), ensure_ascii=False) if trace else "[]",
                "Final Operator Data": json.dumps(trace.get("final_operator_data", []), ensure_ascii=False) if trace else "[]",
                "Pre Scan Validation Is Valid": trace.get("pre_scan_validation_is_valid", "") if trace else "",
                "Pre Scan Validation Reason": trace.get("pre_scan_validation_reason", "") if trace else "",
                "Pre Scan Warning": trace.get("pre_scan_warning", "") if trace else "",
                "Scan Status": trace.get("scan_status", "") if trace else "",
                "Scan Row Count": trace.get("scan_row_count", "") if trace else "",
                "Scan Error": trace.get("scan_error", "") if trace else "",
                "Scan Raw Rows": trace.get("scan_raw_rows", "") if trace else "",
                "Unknown Terms": json.dumps(trace.get("unknown_terms", []), ensure_ascii=False) if trace else "[]",
                "Term Suggestions": json.dumps(trace.get("term_suggestions", {}), ensure_ascii=False) if trace else "{}",
                "Refine Reason": trace.get("refine_reason", "") if trace else "",
                "Validation Is Valid": trace.get("validation_is_valid", "") if trace else "",
                "Validation Reason": trace.get("validation_reason", "") if trace else "",
                "Self Heal Attempts": trace.get("self_heal_attempts", 0) if trace else 0,
                "Short Circuit Stage": trace.get("short_circuit_stage", "") if trace else "",
                "Failure Stage": trace.get("failure_stage", "Exception") if trace else "Exception",
            }


    print("\n[SYSTEM] Running raw pipeline. Saving incrementally...")
    output_filename = REPORT_FILE
    report_columns = [
        "Pipeline Version",
        "Sample Row ID",
        "Question",
        "Ground Truth",
        "Difficulty",
        "Category",
        "Query Type",
        "Source CSV",
        "New Pipeline Result",
        "New Status",
        "Old Status",
        "Comparison / Comments",
        "Started At",
        "Elapsed Seconds",
        "Scan Status",
        "Scan Error",
        "Validation Is Valid",
        "Validation Reason",
        "Failure Stage",
    ]

    def save_report(rows):
        df_report = pd.DataFrame(rows)
        for column in report_columns:
            if column not in df_report.columns:
                df_report[column] = ""
        df_report = df_report[report_columns]
        temporary_file = f"{output_filename}.tmp"
        df_report.to_csv(temporary_file, index=False)
        os.replace(temporary_file, output_filename)

    results_list = []
    completed_row_ids = set()
    if os.path.exists(output_filename):
        try:
            existing_report = pd.read_csv(output_filename)
            if "Sample Row ID" not in existing_report.columns:
                print("[WARN] Existing report has no Sample Row ID, so it cannot safely resume duplicate questions. Starting a fresh report.")
            else:
                if "Pipeline Version" in existing_report.columns:
                    stale_mask = existing_report["Pipeline Version"].astype(str).ne(PIPELINE_VERSION)
                else:
                    stale_mask = pd.Series(True, index=existing_report.index)
                status_series = existing_report.get("New Status", "").astype(str).str.upper()
                retry_mask = stale_mask | status_series.isin({"CRASH", "TRANSIENT_ERROR", "QUOTA_EXHAUSTED", "SCAN_ERROR", "PRE_SCAN_ERROR"})
                retry_count = int(retry_mask.sum())
                existing_report = existing_report[~retry_mask].copy()
                results_list = existing_report.to_dict(orient="records")
                completed_row_ids = set(existing_report["Sample Row ID"].astype(str))
                print(f"[SYSTEM] Resume enabled: found {len(results_list)} completed rows in {output_filename}.")
                if retry_count:
                    print(f"[SYSTEM] Retrying {retry_count} stale-version, previous CRASH, or quota-exhausted rows.")
        except Exception as e:
            print(f"[WARN] Could not read existing report for resume: {e}. Starting fresh.")
            results_list = []
            completed_row_ids = set()

    pending_records = []
    for record in test_records:
        row_id = str(record.get("Sample Row ID", ""))
        if row_id in completed_row_ids:
            continue
        pending_records.append(record)
    skipped_count = len(test_records) - len(pending_records)
    if skipped_count:
        print(f"[SYSTEM] Skipping {skipped_count} already completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=TEST_MAX_WORKERS) as test_runner:
        futures = [test_runner.submit(run_single_test, rec) for rec in pending_records]

        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            res = future.result()
            if str(res.get("New Status", "")).upper() == "QUOTA_EXHAUSTED":
                print("[SYSTEM] OpenAI quota exhausted. Cancelling unscheduled work and preserving remaining rows for resume.")
                for pending_future in futures:
                    pending_future.cancel()
                break
            results_list.append(res)
            print(
                f"Processed {idx}/{len(pending_records)} this run "
                f"({len(results_list)}/{len(test_records)} total window): "
                f"{res['New Status']} in {res.get('Elapsed Seconds', '')}s"
            )


            save_report(results_list)

            if idx % 10 == 0 or idx == len(pending_records):
                api_logger.save()

    if not pending_records and results_list:
        save_report(results_list)

    completed_elapsed_values = []
    for row in results_list:
        try:
            completed_elapsed_values.append(float(row.get("Elapsed Seconds", 0) or 0))
        except (TypeError, ValueError):
            pass
    total_query_generation_seconds = sum(completed_elapsed_values)
    wall_clock_seconds = time.perf_counter() - script_start_time
    avg_query_seconds = total_query_generation_seconds / len(completed_elapsed_values) if completed_elapsed_values else 0.0

    api_logger.save()
    print(f"\n[SUCCESS] Final report successfully saved to {output_filename}.")
    print(f"[TIME] Completed query rows in report: {len(results_list)}")
    print(f"[TIME] Total per-query generation time: {total_query_generation_seconds:.2f} seconds ({total_query_generation_seconds / 60:.2f} minutes)")
    print(f"[TIME] Average per-query time: {avg_query_seconds:.2f} seconds")
    print(f"[TIME] Wall-clock time for this run: {wall_clock_seconds:.2f} seconds ({wall_clock_seconds / 60:.2f} minutes)")


if __name__ == "__main__":
    main()
