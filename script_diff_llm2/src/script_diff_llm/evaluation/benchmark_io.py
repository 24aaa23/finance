import datetime
import json
import time
from typing import Any, Callable

import networkx as nx
import pandas as pd

from script_diff_llm.evaluation.reporting import (
    build_trace_fields,
    make_exception_row,
    make_result_row,
)


def load_input_samples(sample_file: str, input_sample_sheet: str = "") -> pd.DataFrame:
    extension = sample_file.rsplit(".", 1)[-1].lower() if "." in sample_file else ""
    if extension in {"xlsx", "xls"}:
        if input_sample_sheet:
            return pd.read_excel(sample_file, sheet_name=input_sample_sheet)
        return pd.read_excel(sample_file)
    return pd.read_csv(sample_file)


def normalize_benchmark_records(
    df_all: pd.DataFrame,
    *,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], str]:
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
        records = normalized_records.iloc[offset:offset + limit].to_dict(orient="records")
        return records, "new_benchmark"

    working = df_all.copy()
    if "Sample Row ID" not in working.columns:
        working.insert(0, "Sample Row ID", range(1, len(working) + 1))
    if "Status" in working.columns:
        working = working[working["Status"].astype(str).str.strip().str.lower() == "mismatch"].copy()
    records = working.iloc[offset:offset + limit].to_dict(orient="records")
    return records, "legacy_report"


def run_single_benchmark_record(
    record: dict[str, Any],
    *,
    preprocess_user_query: Callable[[str], str],
    planner: Any,
    executor: Any,
    pipeline_version: str,
    is_quota_exhaustion_error: Callable[[Any], bool],
    start_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    query_start_time = time.perf_counter()
    started_at = datetime.datetime.now().isoformat(timespec="seconds")
    if start_delay_seconds > 0:
        time.sleep(start_delay_seconds)
    query = record.get("Question", "")
    ground_truth = str(record.get("Ground Truth", ""))
    old_status = record.get("Status", "")
    sample_row_id = record.get("Sample Row ID", "")
    row_metadata = {
        "Difficulty": record.get("Difficulty", ""),
        "Category": record.get("Category", ""),
        "Query Type": record.get("Query Type", ""),
        "Source CSV": record.get("Source CSV", ""),
    }
    trace: dict[str, Any] = {}
    dag_sequence = ""

    try:
        safe_query = preprocess_user_query(query)
        dag = planner.plan_optimal_dag(safe_query)
        dag_sequence_parts = []
        for node in nx.topological_sort(dag):
            node_data = dag.nodes[node]
            backend = node_data.get("backend", "")
            operator = node_data.get("operator", "")
            dag_sequence_parts.append(f"{node}:{operator}({backend or 'set'})")
        dag_sequence = " -> ".join(dag_sequence_parts)
        result = executor.execute_dag(dag, safe_query)
        trace = result.get("trace", {}) if isinstance(result, dict) else {}
        new_output = result.get("final_answer", json.dumps(result))
        trace_fields = build_trace_fields(trace, dag_sequence)

        failure_stage = str(trace.get("failure_stage", "") or trace.get("short_circuit_stage", ""))
        final_status = str(trace.get("final_status", "")).lower()
        node_statuses = trace.get("node_statuses", {}) if isinstance(trace.get("node_statuses", {}), dict) else {}
        failed_node_status = any(str(status).lower() in {"error", "skipped"} for status in node_statuses.values())
        elapsed_seconds = round(time.perf_counter() - query_start_time, 3)

        if "Pre_Scan_Validate" in failure_stage:
            return make_result_row(
                pipeline_version=pipeline_version,
                sample_row_id=sample_row_id,
                query=query,
                ground_truth=ground_truth,
                row_metadata=row_metadata,
                old_status=old_status,
                new_output=new_output,
                new_status="PRE_SCAN_ERROR",
                comments="Stopped before Scan because generated SPARQL failed Pre_Scan_Validate after retries.",
                started_at=started_at,
                elapsed_seconds=elapsed_seconds,
                trace_fields=trace_fields,
            )

        if "Scan" in failure_stage or str(trace.get("scan_status", "")).lower() == "error":
            return make_result_row(
                pipeline_version=pipeline_version,
                sample_row_id=sample_row_id,
                query=query,
                ground_truth=ground_truth,
                row_metadata=row_metadata,
                old_status=old_status,
                new_output=new_output,
                new_status="SCAN_ERROR",
                comments="Scan could not complete successfully after retries.",
                started_at=started_at,
                elapsed_seconds=elapsed_seconds,
                trace_fields=trace_fields,
            )

        if final_status == "error" or failed_node_status:
            return make_result_row(
                pipeline_version=pipeline_version,
                sample_row_id=sample_row_id,
                query=query,
                ground_truth=ground_truth,
                row_metadata=row_metadata,
                old_status=old_status,
                new_output=new_output,
                new_status="DAG_NODE_ERROR",
                comments="Subquery DAG had one or more failed or skipped nodes.",
                started_at=started_at,
                elapsed_seconds=elapsed_seconds,
                trace_fields=trace_fields,
            )

        return make_result_row(
            pipeline_version=pipeline_version,
            sample_row_id=sample_row_id,
            query=query,
            ground_truth=ground_truth,
            row_metadata=row_metadata,
            old_status=old_status,
            new_output=new_output,
            new_status="PIPELINE_SUCCESS",
            comments="Raw pipeline output saved; run the separate grader script for MATCH/MISMATCH/PARTIAL.",
            started_at=started_at,
            elapsed_seconds=elapsed_seconds,
            trace_fields=trace_fields,
        )

    except Exception as error:
        elapsed_seconds = round(time.perf_counter() - query_start_time, 3)
        quota_exhausted = is_quota_exhaustion_error(error)
        return make_exception_row(
            pipeline_version=pipeline_version,
            sample_row_id=sample_row_id,
            query=query,
            ground_truth=ground_truth,
            row_metadata=row_metadata,
            old_status=old_status,
            error_message=f"ERROR: {str(error)}",
            new_status="QUOTA_EXHAUSTED" if quota_exhausted else "CRASH",
            comments=(
                "OpenAI quota was exhausted; stopping the run without marking remaining rows."
                if quota_exhausted
                else "Pipeline threw a fatal exception."
            ),
            started_at=started_at,
            elapsed_seconds=elapsed_seconds,
            dag_sequence=dag_sequence,
            trace=trace,
        )
