"""Run the improvement8 SQL AOP pipeline with supplied domain knowledge."""

import sys
import traceback
from copy import deepcopy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .common import (
    EXPLAIN_MODEL,
    SQLITE_DB_PATH,
    SQL_SCAN_TIMEOUT_SECONDS,
    GPT_OSS_MODEL,
    INPUT_SAMPLE_FILE,
    PIPELINE_VERSION,
    PLANNER_MODEL,
    QUERY_SPEC_MODEL,
    RAG_MODEL,
    REFINE_MODEL,
    REPORT_FILE,
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
from .common import (QUERY_UNDERSTANDING, CONTRACT_CHECKS, AGENT_CONSULTATION, DOMAIN_INTRO_FILE,
                     BUSINESS_RULES_FILE, TABLE_METADATA_DIR, KNOWLEDGE_CACHE_DIR)
from .business_context import configure_business_context
from .knowledge import load_documents, annotate_schema, compile_knowledge, prompt_pack, digest
from .query_understanding import understand_query, UnderstandingError, VERSION as UNDERSTANDING_VERSION
from .consultation import ConsultationSession, InterpretationRevised
from .reporting import load_input_samples, write_jsonl_atomic
from .sqlite_backend import check_sqlite_health
from .hybrid_backend import (
    load_hybrid_metadata as load_yaml_metadata, get_hybrid_index as get_lightweight_table_index,
    load_hybrid_documents as load_documents, configure_context as configure_business_context,
    dispatch as hybrid_dispatch, scan as hybrid_scan,
)
from .utils import is_quota_exhaustion_error, is_transient_connection_error, preprocess_user_query
from .llm_operators import (
    semantic_retrieve,
    semantic_decompose_question,
    semantic_build_query_spec,
    semantic_build_processing_spec,
    semantic_build_final_spec,
    semantic_generate_sparql,
    semantic_pre_scan_validate,
    semantic_refine,
    semantic_validate,
    semantic_explain_results,
    semantic_filter_aggregate,
    semantic_order_by,
    semantic_integrate,
)
from .non_llm_operators import (
    pre_programmed_scan,
    pre_programmed_math_compute,
    pre_programmed_set_intersect,
    pre_programmed_union,
    pre_programmed_difference,
    pre_programmed_date_extract,
    pre_programmed_bucket,
)
from .planner import AdvancedAOPPlanner
from .executor import AOPExecutor
from .retry_batch import (completed_retry_ids, replace_retry_result, read_retry_report,
                         failed_retry_rows, prepare_in_place_retry, save_retry_manifest)
from .performance import RunTiming, query_delay, REPORT_METRIC_COLUMNS


def _main(timing=None):
    from .runtime_guard import progress, wait_for_memory
    timing = timing or RunTiming()
    timing.metadata.update(model=GPT_OSS_MODEL, report_file=REPORT_FILE)
    delay_seconds = query_delay(os.getenv("QUERY_DELAY_SECONDS", "0"))
    retry_in_place = os.getenv("RETRY_ERRORS_IN_PLACE", "0") == "1"
    retry_columns, retry_rows, retry_pending = [], [], []
    if retry_in_place:
        retry_columns, retry_rows = read_retry_report(REPORT_FILE)
        retry_pending = failed_retry_rows(retry_rows)
        if not retry_pending:
            progress("[SKIP] No saved execution failures. Report unchanged; no model calls.")
            return
    print("\n" + "="*50)
    print("INITIALIZING AOP PIPELINE")
    print("="*50)

    #CONFIGURATION & API SETUP
    print("[SYSTEM] Scan backend: SQLite + RDF/SPARQL (hybrid ablation)")
    print(f"[SYSTEM] SQLite database: {SQLITE_DB_PATH}")
    print(f"[SYSTEM] SQL scan timeout: {SQL_SCAN_TIMEOUT_SECONDS:g} seconds")
    with timing.stage("database_health"):
        check_sqlite_health(SQLITE_DB_PATH)

    with timing.stage("client_setup"):
        gpt_oss_client = timing.client(build_gpt_oss_client())
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
    print("[SYSTEM] DAG planner mode: fixed V9 operator flow")
    print(f"[SYSTEM] Report file: {REPORT_FILE}")
    input_manifest = os.getenv("INPUT_QUERY_FILE", os.getenv("INPUT_QUERY_CSV", "")).strip()
    retry_query_spec_only = os.getenv("RETRY_QUERY_SPEC_ERRORS_ONLY", "0") == "1"
    with timing.stage("schema_and_documents"):
        physical_metadata = load_yaml_metadata(TABLE_METADATA_DIR)
        documents = load_documents(DOMAIN_INTRO_FILE, BUSINESS_RULES_FILE, TABLE_METADATA_DIR)
    knowledge_status = {}
    with timing.stage("Domain"):
        knowledge_pack, knowledge_identity = compile_knowledge(
            documents, physical_metadata, gpt_oss_client, GPT_OSS_MODEL, KNOWLEDGE_CACHE_DIR,
            diagnostics=knowledge_status)
    cache_hit = knowledge_status["cache_hit"]
    timing.metadata.update(knowledge_cache_hit=cache_hit, knowledge_identity=knowledge_identity,
                           query_delay_seconds=delay_seconds)
    progress(f"[CACHE] Knowledge {'hit' if cache_hit else 'compiled'} in {timing.stages[-1]['seconds']:.3f}s")
    from run_pipeline_v2_kg.kg_backend import check_kg_health
    check_kg_health(os.environ['SPARQL_ENDPOINT'],
                    {k:v for k,v in physical_metadata.items() if v.get('backend')=='rdf'},60)
    business_pack = prompt_pack(knowledge_pack)
    configure_business_context(business_pack)
    kg_metadata = annotate_schema(physical_metadata, documents)
    print(f"[SYSTEM] Knowledge identity: {knowledge_identity}; query understanding: {QUERY_UNDERSTANDING}")
    from .run_identity import build_run_identity
    source_identity, source_manifest = build_run_identity(
        os.path.dirname(__file__),
        {"questions": input_manifest or INPUT_SAMPLE_FILE, "sqlite_database": SQLITE_DB_PATH,
         "ontology": os.environ["ONTOLOGY_FILE"], "kg_instances": os.environ["INSTANCE_FILE"]},
        {"model": GPT_OSS_MODEL, "pipeline_version": PIPELINE_VERSION,
         "spec_first": "v9",
         "final_semantic_review": False,
         "query_offset": TEST_QUERY_OFFSET, "query_limit": TEST_QUERY_LIMIT,
         "shuffle_seed": os.getenv("QUERY_SHUFFLE_SEED", ""),
         "workers": 1, "scan_backend": "sql_and_kg",
         "knowledge_identity": knowledge_identity, "knowledge_pack_hash": digest(knowledge_pack),
         "query_understanding": QUERY_UNDERSTANDING, "contract_checks": CONTRACT_CHECKS,
         "agent_consultation": AGENT_CONSULTATION,
         "query_delay_seconds": delay_seconds,
         "understanding_version": UNDERSTANDING_VERSION,
         "retry_query_spec_errors_only": retry_query_spec_only},
    )
    manifest_file = REPORT_FILE + ".manifest.json"
    # Report identity includes code and data hashes. Never resume rows from another
    # implementation merely because it reused a configurable version label.
    if os.path.exists(REPORT_FILE):
        previous_identity = ""
        previous_manifest = {}
        if os.path.exists(manifest_file):
            with open(manifest_file, encoding="utf-8") as handle:
                previous_manifest = json.load(handle)
                previous_identity = previous_manifest.get("run_identity", "")
        if retry_in_place:
            stem = os.path.splitext(REPORT_FILE)[0]
            source_manifest = prepare_in_place_retry(REPORT_FILE, source_manifest,
                [row["Sample Row ID"] for row in retry_pending],
                [stem + "_debug.csv", os.getenv("RESULT_JSONL_FILE", stem + ".jsonl"),
                 os.getenv("DEBUG_JSONL_FILE", stem + "_debug.jsonl")])
            progress(f"[BACKUP] {source_manifest['retry_history'][-1]['backup_directory']}")
            progress(f"[RETRY] Replacing {len(retry_pending)} failed rows in the existing CSV; keeping all other rows.")
        elif previous_identity != source_identity or previous_manifest.get("mixed_results"):
            raise RuntimeError("Report exists with a different or missing source/data manifest. Set REPORT_FILE to a new filename to preserve the old run.")
    if not retry_in_place:
        with open(manifest_file, "w", encoding="utf-8") as handle:
            json.dump(source_manifest, handle, indent=2)
    print(f"[SYSTEM] Source/data run identity: {source_identity}")



    # Physical tables/columns come from SQLite; business annotations match KG.
    rdf_graph = None

    if not kg_metadata:
        print("[!] ERROR: No tables were found in the SQLite database.")
        return

    # Create the token-saving index
    lightweight_index = get_lightweight_table_index(kg_metadata)




    #INITIALIZE OPERATOR REGISTRY

    operator_registry = {
        # Retrieval & Generation
        # Pass the full schema as 'global_schema' so Generate/Refine can prune it dynamically
        "Retrieve": lambda inputs: semantic_retrieve({**inputs, "table_index": lightweight_index}, retrieve_client, RAG_MODEL),
        "Decompose": lambda inputs: semantic_decompose_question({**inputs, "global_schema": kg_metadata}, target_client, TARGET_MODEL),
        "Query_Spec": lambda inputs: hybrid_dispatch("Query_Spec", {**inputs, "global_schema": kg_metadata}, query_spec_client, QUERY_SPEC_MODEL),
        "Processing_Spec": lambda inputs: semantic_build_processing_spec(inputs, target_client, TARGET_MODEL),
        "Final_Spec": lambda inputs: semantic_build_final_spec({**inputs, "global_schema": kg_metadata, "contract_checks": CONTRACT_CHECKS}, target_client, TARGET_MODEL),
        "Generate": lambda inputs: hybrid_dispatch("Generate",
            {**inputs, "global_schema": kg_metadata},
            sparql_generation_client,
            SPARQL_GENERATION_MODEL,
        ),
        "Pre_Scan_Validate": lambda inputs: hybrid_dispatch("Pre_Scan_Validate", {**inputs, "global_schema": kg_metadata}, validate_client, VALIDATE_MODEL),
        "Refine": lambda inputs: hybrid_dispatch("Refine", {**inputs, "global_schema": kg_metadata}, refine_client, REFINE_MODEL),

        # Execution & Validation
        "Scan": lambda inputs: hybrid_scan(inputs, SQLITE_DB_PATH),
        "Validate": lambda inputs: semantic_validate(inputs, validate_client, VALIDATE_MODEL),
        "Explain": lambda inputs: semantic_explain_results(inputs, explain_client, EXPLAIN_MODEL),

        # Mathematical & Set Operations
        "Math_Compute": lambda inputs: pre_programmed_math_compute(inputs),
        "Date_Extract": lambda inputs: pre_programmed_date_extract(inputs),
        "Bucket": lambda inputs: pre_programmed_bucket(inputs),
        "Set_Intersect": lambda inputs: pre_programmed_set_intersect(inputs),
        "Set_Union": lambda inputs: pre_programmed_union(inputs),
        "Set_Difference": lambda inputs: pre_programmed_difference(inputs),
        "Union": lambda inputs: pre_programmed_union(inputs),
        "Difference": lambda inputs: pre_programmed_difference(inputs),

        # Calculations called by the compiled final plan; these execute in Python.
        "Filter_Aggregate": lambda inputs: semantic_filter_aggregate({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Order_By": lambda inputs: semantic_order_by({**inputs, "schema_details": kg_metadata}, target_client, TARGET_MODEL),
        "Integrate": lambda inputs: semantic_integrate(inputs, target_client, TARGET_MODEL),
    }

    consultation_session = None
    def with_consultation(stage, operator):
        def invoke(inputs):
            if consultation_session is None:
                return operator(inputs)
            return consultation_session.run(stage, operator, inputs)
        return invoke
    if AGENT_CONSULTATION:
        for stage in ("Decompose", "Query_Spec", "Final_Spec"):
            operator_registry[stage] = with_consultation(stage, operator_registry[stage])

    operator_registry = {name: timing.operator(name, operator) for name, operator in operator_registry.items()}
    planner = AdvancedAOPPlanner(planner_client, operator_registry, model=PLANNER_MODEL)
    executor = AOPExecutor(operator_registry, rdf_graph, global_schema=kg_metadata)



# === 1. LOAD AND FILTER FAILED QUERIES ===

    # A selected manifest can be rerun independently; the benchmark file remains
    # the default when INPUT_QUERY_CSV is not set.
    sample_file = input_manifest or INPUT_SAMPLE_FILE

    try:

        print(f"\n[SYSTEM] Loading {sample_file}...")

        df_all = pd.DataFrame(retry_pending) if retry_in_place else load_input_samples(sample_file)

        if {"Sample Row ID", "Question", "Ground Truth"}.issubset(df_all.columns):
            end = TEST_QUERY_OFFSET + TEST_QUERY_LIMIT if TEST_QUERY_LIMIT > 0 else None
            test_records = df_all.iloc[TEST_QUERY_OFFSET:end].to_dict(orient='records')
            print(f"[SYSTEM] Input manifest window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT or 'all remaining'}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} manifest queries.")
        elif {"question", "ground_truth_answer"}.issubset(df_all.columns):
            normalized_records = pd.DataFrame({
                "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
                "Question": df_all["question"].astype(str),
                "Ground Truth": df_all["ground_truth_answer"].astype(str),
                "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
                "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
                "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
                "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
                "Dataset Type": df_all.get("dataset_type", pd.Series([""] * len(df_all))).astype(str),
                "Status": "NEW_BENCHMARK",
            })
            end = TEST_QUERY_OFFSET + TEST_QUERY_LIMIT if TEST_QUERY_LIMIT > 0 else None
            test_records = normalized_records.iloc[TEST_QUERY_OFFSET:end].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} benchmark queries from the new dataset.")
        else:
            if "Sample Row ID" not in df_all.columns:
                df_all.insert(0, "Sample Row ID", range(1, len(df_all) + 1))
            if "Status" in df_all.columns:
                df_failed = df_all[df_all['Status'].astype(str).str.strip().str.lower() == 'mismatch'].copy()
            else:
                df_failed = df_all.copy()
            end = TEST_QUERY_OFFSET + TEST_QUERY_LIMIT if TEST_QUERY_LIMIT > 0 else None
            test_records = df_failed.iloc[TEST_QUERY_OFFSET:end].to_dict(orient='records')
            print(f"[SYSTEM] Query window offset={TEST_QUERY_OFFSET}, limit={TEST_QUERY_LIMIT}.")
            print(f"[SYSTEM] Successfully loaded {len(test_records)} queries.")

    except Exception as e:
        print(f"\n[!] ERROR loading Excel file: {e}")
        return

    def _compact_debug_json(value, max_chars=12000):
        """Serialize diagnostic context without allowing a single CSV cell to grow unbounded."""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
        return text if max_chars is None or len(text) <= max_chars else json.dumps({"truncated": True, "preview": text[:max_chars]}, ensure_ascii=False)

    def _scan_debug_summary(trace):
        raw = trace.get("scan_raw_rows", "") if isinstance(trace, dict) else ""
        rows = []
        if isinstance(raw, str) and raw:
            try:
                parsed = json.loads(raw)
                rows = parsed if isinstance(parsed, list) else []
            except (TypeError, ValueError, json.JSONDecodeError):
                rows = []
        elif isinstance(raw, list):
            rows = raw
        columns = []
        for row in rows[:3]:
            if isinstance(row, dict):
                columns.extend(key for key in row if key not in columns)
        return {
            "row_count": trace.get("scan_row_count", len(rows)) if isinstance(trace, dict) else len(rows),
            "columns": columns,
            "sample_rows": rows[:3],
            "status": trace.get("scan_status", "") if isinstance(trace, dict) else "",
            "error": trace.get("scan_error", "") if isinstance(trace, dict) else "",
        }

    def _debug_fields(trace, dag_sequence="", exception=""):
        """Compact per-query diagnostics; raw scans are represented by schema/count/three rows only."""
        trace = trace if isinstance(trace, dict) else {}
        return {
            "Debug DAG Sequence": dag_sequence,
            "Debug Operator Sequence": " -> ".join(trace.get("operator_sequence", [])),
            "Debug Retrieved Classes": _compact_debug_json(trace.get("retrieved_classes", [])),
            "Debug Subquestions": _compact_debug_json(trace.get("subquestions", [])),
            "Debug Query Specs": _compact_debug_json(trace.get("query_specs", []), max_chars=None),
            "Debug SPARQL": _compact_debug_json(trace.get("executed_sparqls") or trace.get("generated_sparqls", []) or trace.get("generated_sparql", ""), max_chars=None),
            "Debug Scan Summary": _compact_debug_json(_scan_debug_summary(trace)),
            "Debug Processing Specs": _compact_debug_json(trace.get("processing_specs", [])),
            "Debug Final Spec": _compact_debug_json(trace.get("final_spec", {}), max_chars=None),
            "Debug Branch Profiles": _compact_debug_json(trace.get("branch_profiles", []), max_chars=None),
            "Debug Execution Log": _compact_debug_json(trace.get("post_scan_operator_outputs", []), max_chars=None),
            "Debug Repair Log": _compact_debug_json({
                "stage_repairs": trace.get("repair_log", []),
                "agent_consultations": trace.get("agent_consultations", []),
                "decomposition_repairs": trace.get("decomposition_repair_log", []),
            }, max_chars=None),
            "Debug Validation Feedback": str(trace.get("validation_reason", "") or trace.get("pre_scan_validation_reason", "")),
            "Debug Exception": str(exception or ""),
            "Debug Answer Requirements": _compact_debug_json(trace.get("decomposition", {}).get("answer_requirements", {})),
            "Debug Operator Audit": _compact_debug_json(trace.get("operator_audit", []), max_chars=None),
            "Debug Query Understanding": _compact_debug_json(trace.get("query_understanding", {}), max_chars=None),
            "Debug Understanding Attempts": _compact_debug_json(trace.get("understanding_diagnostics", {}), max_chars=None),
            "Knowledge Identity": knowledge_identity,
        }

    def run_single_test(record):
        nonlocal consultation_session
        consultation_session = None
        query_start_time = time.perf_counter()
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        if delay_seconds:
            with timing.stage("query_delay"):
                time.sleep(delay_seconds)
        query = record.get('Question', '')
        ground_truth = str(record.get('Ground Truth', ''))
        old_status = record.get('Status', '')
        sample_row_id = record.get('Sample Row ID', '')
        row_metadata = {
            "Difficulty": record.get('Difficulty', ''),
            "Category": record.get('Category', ''),
            "Query Type": record.get('Query Type', ''),
            "Source CSV": record.get('Source CSV', ''),
            "Dataset Type": record.get('Dataset Type', record.get('dataset_type', '')),
        }
        trace = {}
        understanding_diagnostics = {}
        dag_sequence = ""

        try:
            # Sanitize and Execute
            safe_query = preprocess_user_query(query)
            interpretation = {}
            if QUERY_UNDERSTANDING:
                trace["failure_stage"] = "Query_Understanding"
                with timing.stage("Query_Understanding"):
                    interpretation = understand_query(safe_query, kg_metadata, business_pack, target_client, TARGET_MODEL,
                                                       diagnostics=understanding_diagnostics)
                trace.pop("failure_stage", None)
            if AGENT_CONSULTATION:
                consultation_session = ConsultationSession(safe_query, kg_metadata, documents,
                    business_pack, target_client, TARGET_MODEL, interpretation)
                trace["agent_consultations"] = consultation_session.log
            retrieve_result = operator_registry["Retrieve"]({"query": safe_query, "query_understanding": interpretation})
            retrieve_result["query_understanding"] = interpretation
            decomposition_feedback = ""
            decomposition_repair_log = []
            for decomposition_attempt in range(3):
                decomposition, decomposition_result = {}, {}
                try:
                    decomposition_result = operator_registry["Decompose"]({
                        "query": safe_query,
                        **retrieve_result,
                        "decomposition_feedback": decomposition_feedback,
                        "contract_checks": CONTRACT_CHECKS,
                    })
                    decomposition = decomposition_result.get("selected_decomposition", {})
                    if decomposition.get("contract_errors"):
                        decomposition_feedback = "; ".join(decomposition["contract_errors"])
                        decomposition_repair_log.append({"attempt": decomposition_attempt + 1, "reason": decomposition_feedback})
                        if decomposition_attempt < 2:
                            continue
                        trace = {"failure_stage": "Decompose", "validation_is_valid": False,
                                 "validation_reason": decomposition_feedback, "final_output_produced": False}
                        result = {"final_answer": decomposition_feedback, "trace": trace}
                        break
                    dag = planner.plan_optimal_dag_from_decomposition(safe_query, decomposition)
                    dag_sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
                    result = executor.execute_dag(
                        dag, safe_query, decomposition=decomposition,
                        initial_context={**retrieve_result,
                            "decomposition_candidates": decomposition_result.get("decomposition_candidates", [])},
                    )
                except InterpretationRevised as exc:
                    interpretation = deepcopy(consultation_session.interpretation)
                    decomposition_feedback = str(exc)
                    decomposition_repair_log.append({"attempt": decomposition_attempt + 1,
                        "reason": decomposition_feedback, "action": "restart_with_revised_interpretation"})
                    if decomposition_attempt < 2:
                        retrieve_result = operator_registry["Retrieve"]({"query": safe_query, "query_understanding": interpretation})
                        retrieve_result["query_understanding"] = interpretation
                        continue
                    trace = {"failure_stage": "Decompose", "validation_is_valid": False,
                             "validation_reason": "Interpretation changed but no decomposition attempts remain.",
                             "final_output_produced": False}
                    result = {"final_answer": trace["validation_reason"], "trace": trace}
                    break
                trace = result.get("trace", {}) if isinstance(result, dict) else {}
                failed_query_spec = isinstance(trace, dict) and (str(trace.get("failure_stage", "")) == "Query_Spec" or trace.get("repair_stage") == "Decompose")
                if not failed_query_spec or decomposition_attempt == 2:
                    break
                repair_detail = str(trace.get("validation_reason", "")) + "; " + "; ".join(
                    str(error)
                    for item in trace.get("repair_log", [])
                    if isinstance(item, dict)
                    for error in item.get("errors", [])
                )
                decomposition_repair_log.append({"attempt": decomposition_attempt + 1, "reason": repair_detail})
                decomposition_feedback = (
                    "The prior decomposition/retrieval did not preserve the original requirements. "
                    "Repair the missing sources, predicates, keys, or observation grain; preserve exact literals and all conditions. "
                    + repair_detail
                )
            if isinstance(trace, dict):
                trace["understanding_diagnostics"] = understanding_diagnostics
                trace["agent_consultations"] = consultation_session.log if consultation_session else []
                trace["query_understanding"] = interpretation
                trace["decomposition_repair_log"] = decomposition_repair_log
                trace.setdefault("retrieved_classes", retrieve_result.get("retrieved_tables", []))
                trace.setdefault("decomposition", decomposition)
                trace.setdefault("decomposition_candidates", decomposition_result.get("decomposition_candidates", []))
                trace.setdefault("subquestions", decomposition.get("subquestions", []) if isinstance(decomposition, dict) else [])
            if trace.get("final_output_produced") and not trace.get("failure_stage"):
                final_data_json = json.dumps(trace["final_operator_data"], ensure_ascii=False)
                new_output = final_data_json
            else:
                # The report is deliberately final-output-only.  Compact raw Scan evidence
                # belongs in the adjacent debug CSV, never in an error result cell.
                new_output = result.get('final_answer') or "No executable final output was produced."

            trace_fields = {
                "Scan Status": trace.get("scan_status", ""),
                "Scan Error": trace.get("scan_error", ""),
                "Validation Is Valid": trace.get("validation_is_valid", ""),
                "Validation Reason": trace.get("validation_reason", ""),
                "Answer Review Status": trace.get("answer_review_status", "not_reached"),
                "Failure Stage": trace.get("failure_stage", ""),
                **_debug_fields(trace, dag_sequence),
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
                    "Comparison / Comments": "Stopped before Scan because generated SQL failed Pre_Scan_Validate after retries.",
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
                "Decompose": "DECOMPOSITION_ERROR",
                "Query_Spec": "QUERY_SPEC_ERROR",
                "Processing_Spec": "PROCESSING_SPEC_ERROR",
                "Final_Spec": "FINAL_SPEC_ERROR",
                "Execution": "EXECUTION_ERROR",
            }
            if failure_stage or not trace.get("final_output_produced"):
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
                    "Comparison / Comments": "The pipeline stopped before completing an executable final result.",
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
                "Comparison / Comments": "Final result executed successfully; answer correctness is recorded separately by review/grading.",
                "Started At": started_at,
                "Elapsed Seconds": elapsed_seconds,
                **trace_fields,
            }

        except Exception as e:
            trace["understanding_diagnostics"] = understanding_diagnostics
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
                "New Status": "QUERY_UNDERSTANDING_ERROR" if isinstance(e, UnderstandingError) else ("QUOTA_EXHAUSTED" if quota_exhausted else ("TRANSIENT_ERROR" if transient_error else "CRASH")),
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
                **_debug_fields(trace, dag_sequence, exception=traceback.format_exc(limit=12)),
            }


    print("\n[SYSTEM] Running raw pipeline. Saving incrementally...")
    output_filename = REPORT_FILE
    debug_output_filename = f"{os.path.splitext(output_filename)[0]}_debug.csv"
    result_jsonl_filename = os.getenv("RESULT_JSONL_FILE", f"{os.path.splitext(output_filename)[0]}.jsonl")
    debug_jsonl_filename = os.getenv("DEBUG_JSONL_FILE", f"{os.path.splitext(output_filename)[0]}_debug.jsonl")
    report_columns = [
        "Pipeline Version",
        "Sample Row ID",
        "Question",
        "Ground Truth",
        "Difficulty",
        "Category",
        "Query Type",
        "Source CSV",
        "Dataset Type",
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
        "Answer Review Status",
        "Failure Stage",
    ]
    report_columns.extend(REPORT_METRIC_COLUMNS)
    debug_columns = [
        "Pipeline Version", "Sample Row ID", "Question", "New Status", "Started At", "Elapsed Seconds",
        "Failure Stage", "Scan Status", "Scan Error", "Validation Is Valid", "Validation Reason", "Answer Review Status",
        "Debug DAG Sequence", "Debug Operator Sequence", "Debug Retrieved Classes", "Debug Subquestions",
        "Debug Query Specs", "Debug SPARQL", "Debug Scan Summary", "Debug Processing Specs",
        "Debug Final Spec", "Debug Branch Profiles", "Debug Execution Log", "Debug Repair Log", "Debug Validation Feedback",
        "Debug Exception", "Debug Answer Requirements", "Debug Operator Audit", "Debug Query Understanding", "Debug Understanding Attempts", "Knowledge Identity",
    ]

    debug_columns.extend(REPORT_METRIC_COLUMNS)

    def save_report(rows):
        os.makedirs(os.path.dirname(output_filename) or ".", exist_ok=True)
        df_report = pd.DataFrame(rows)
        columns = list(dict.fromkeys(retry_columns + report_columns)) if retry_in_place else report_columns
        for column in columns:
            if column not in df_report.columns:
                df_report[column] = ""
        df_report = df_report[columns]
        temporary_file = f"{output_filename}.tmp"
        df_report.to_csv(temporary_file, index=False)
        os.replace(temporary_file, output_filename)

    def save_debug_report(records):
        os.makedirs(os.path.dirname(debug_output_filename) or ".", exist_ok=True)
        df_debug = pd.DataFrame(records)
        for column in debug_columns:
            if column not in df_debug.columns:
                df_debug[column] = ""
        df_debug = df_debug[debug_columns]
        temporary_file = f"{debug_output_filename}.tmp"
        df_debug.to_csv(temporary_file, index=False)
        os.replace(temporary_file, debug_output_filename)

    def save_jsonl_reports(rows, debug_rows):
        # JSONL has no spreadsheet cell-length limit and keeps full result tables intact.
        os.makedirs(os.path.dirname(result_jsonl_filename) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(debug_jsonl_filename) or ".", exist_ok=True)
        write_jsonl_atomic(result_jsonl_filename, rows)
        write_jsonl_atomic(debug_jsonl_filename, debug_rows)

    results_list = []
    debug_records = {}
    completed_row_ids = set()
    if retry_in_place:
        results_list = retry_rows
        retry_ids = {row["Sample Row ID"] for row in retry_pending}
        completed_row_ids = {row["Sample Row ID"] for row in retry_rows} - retry_ids
        if os.path.exists(debug_output_filename):
            existing_debug = pd.read_csv(debug_output_filename, dtype=str, keep_default_na=False)
            debug_columns = list(dict.fromkeys(list(existing_debug.columns) + debug_columns))
            debug_records = {str(row["Sample Row ID"]): row for row in existing_debug.to_dict(orient="records")}
    elif os.path.exists(output_filename):
        try:
            existing_report = pd.read_csv(output_filename, dtype=str, keep_default_na=False)
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
                if retry_query_spec_only:
                    results_list = existing_report.to_dict(orient="records")
                    completed_row_ids = completed_retry_ids(results_list)
                    retry_count = len(results_list) - len(completed_row_ids)
                else:
                    existing_report = existing_report[~retry_mask].copy()
                    results_list = existing_report.to_dict(orient="records")
                    completed_row_ids = set(existing_report["Sample Row ID"].astype(str))
                if os.path.exists(debug_output_filename):
                    try:
                        existing_debug = pd.read_csv(debug_output_filename)
                        debug_records = {
                            str(item.get("Sample Row ID", "")): item
                            for item in existing_debug.to_dict(orient="records")
                            if retry_query_spec_only or str(item.get("Sample Row ID", "")) in completed_row_ids
                        }
                    except Exception as debug_error:
                        print(f"[WARN] Could not read debug report for resume: {debug_error}. Rebuilding diagnostics for new rows.")
                print(f"[SYSTEM] Resume enabled: found {len(results_list)} completed rows in {output_filename}.")
                if retry_count:
                    print(f"[SYSTEM] Retrying {retry_count} " + ("QUERY_SPEC_ERROR rows." if retry_query_spec_only else "stale-version or retryable execution rows."))
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
    report_total = len(retry_rows) if retry_in_place else len(test_records)
    if skipped_count:
        print(f"[SYSTEM] Skipping {skipped_count} already completed queries.")
    print(f"[SYSTEM] Pending queries this run: {len(pending_records)}")
    timing.metadata.update(report_file=REPORT_FILE, resumed_rows=len(results_list), pending_rows=len(pending_records))
    timing.ready()
    progress(f"[TIME] Startup ready: {timing.startup_seconds:.3f}s; query delay: {delay_seconds:g}s")

    # Submit nothing ahead of the current question: memory checks must happen
    # before work starts, and quota failures must leave later questions untouched.
    for idx, record in enumerate(pending_records, 1):
        with timing.question(record.get("Sample Row ID", "")) as query_timing:
            with timing.stage("memory_wait"):
                wait_for_memory()
            first_call = len(timing.llm_calls)
            res = run_single_test(record)
            res.update(timing.report_metrics(first_call))
            query_timing.update(processing_seconds=res.get("Elapsed Seconds", 0), status=res["New Status"])
            if str(res.get("New Status", "")).upper() == "QUOTA_EXHAUSTED":
                timing.metadata["stop_reason"] = "quota_exhausted"
                print("[SYSTEM] OpenAI quota exhausted. Preserving remaining rows for resume.")
                break
            if retry_in_place:
                previous = next(row for row in results_list if str(row["Sample Row ID"]) == str(res["Sample Row ID"]))
                replace_retry_result(results_list, {**previous, **res})
            elif retry_query_spec_only:
                replace_retry_result(results_list, res)
            else:
                results_list.append(res)
            debug_records[str(res.get("Sample Row ID", ""))] = res
            with timing.stage("report_writes"):
                save_report(results_list)
                save_debug_report(list(debug_records.values()))
                if retry_in_place:
                    # Keep grader-preferred JSONL sidecars current at each checkpoint.
                    save_jsonl_reports(results_list, list(debug_records.values()))
                    source_manifest["retry_history"][-1]["completed_ids"].append(str(res["Sample Row ID"]))
                    save_retry_manifest(manifest_file, source_manifest)
                if idx % 10 == 0 or idx == len(pending_records):
                    api_logger.save()
        progress(
            f"Processed {idx}/{len(pending_records)} this run "
            f"({len(results_list)}/{report_total} total window): "
            f"{res['New Status']} in {res.get('Elapsed Seconds', '')}s processing; "
            f"model {query_timing['llm_seconds']:.3f}s/{query_timing['llm_calls']} calls; "
            f"{query_timing['cycle_seconds']:.3f}s including wait/save; "
            f"{timing.elapsed():.3f}s since startup"
        )

    if not pending_records and results_list:
        save_report(results_list)
        save_debug_report(list(debug_records.values()))

    # JSONL preserves the full result tables, but repeatedly serializing every
    # completed row rewrites an increasingly large pair of files.  The v3
    # runners only checkpoint CSV reports while work is in progress.  Match
    # that behavior here: CSV/debug CSV remain recoverable after every query,
    # and write the lossless JSONL sidecars once after this run completes.
    if results_list:
        with timing.stage("final_jsonl_writes"):
            save_jsonl_reports(results_list, list(debug_records.values()))

    completed_elapsed_values = []
    for row in results_list:
        try:
            completed_elapsed_values.append(float(row.get("Elapsed Seconds", 0) or 0))
        except (TypeError, ValueError):
            pass
    total_query_generation_seconds = sum(completed_elapsed_values)
    avg_query_seconds = total_query_generation_seconds / len(completed_elapsed_values) if completed_elapsed_values else 0.0

    with timing.stage("final_api_log_write"):
        api_logger.save()
    print(f"\n[SUCCESS] Final report successfully saved to {output_filename}.")
    print(f"[SUCCESS] Debug report successfully saved to {debug_output_filename}.")
    print(f"[SUCCESS] Lossless JSONL report successfully saved to {result_jsonl_filename}.")
    print(f"[TIME] Completed query rows in report: {len(results_list)}")
    print(f"[TIME] Report-wide query time (includes resumed rows): {total_query_generation_seconds:.2f} seconds")
    print(f"[TIME] Report-wide average per-query time: {avg_query_seconds:.2f} seconds")
    print(f"[TIME] Current-run processing: {sum(q.get('processing_seconds', 0) for q in timing.questions):.2f} seconds")
    print(timing.summary())


def main():
    from .runtime_guard import launch
    launch()


if __name__ == "__main__":
    main()
