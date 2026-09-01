import json
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd


REPORT_COLUMNS = [
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
    "DAG Sequence",
    "AOP Operator Sequence",
    "Retrieved Classes",
    "Query Spec",
    "Generated SPARQL",
    "Pre Scan Validation Is Valid",
    "Pre Scan Validation Reason",
    "Pre Scan Warning",
    "Scan Status",
    "Scan Row Count",
    "Scan Error",
    "Scan Raw Rows",
    "Unknown Terms",
    "Term Suggestions",
    "Refine Reason",
    "Validation Is Valid",
    "Validation Reason",
    "Self Heal Attempts",
    "Short Circuit Stage",
    "Failure Stage",
    "Final Query Status",
    "Node Statuses",
    "Node Dependencies",
    "DAG Execution Levels",
    "Node Backends",
    "Node Traces",
]


@dataclass(frozen=True)
class ResumeState:
    results_list: list[dict[str, Any]]
    completed_row_ids: set[str]
    retry_count: int
    resume_enabled: bool


def build_trace_fields(trace: dict[str, Any], dag_sequence: str) -> dict[str, Any]:
    return {
        "DAG Sequence": dag_sequence,
        "AOP Operator Sequence": " | ".join(str(s) for s in trace.get("operator_sequence", [])),
        "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False),
        "Query Spec": json.dumps(trace.get("query_spec", {}), ensure_ascii=False),
        "Generated SPARQL": trace.get("generated_sparql", ""),
        "Pre Scan Validation Is Valid": trace.get("pre_scan_validation_is_valid", ""),
        "Pre Scan Validation Reason": trace.get("pre_scan_validation_reason", ""),
        "Pre Scan Warning": trace.get("pre_scan_warning", ""),
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
        "Final Query Status": trace.get("final_status", ""),
        "Node Statuses": json.dumps(trace.get("node_statuses", {}), ensure_ascii=False),
        "Node Dependencies": json.dumps(trace.get("node_dependencies", {}), ensure_ascii=False),
        "DAG Execution Levels": json.dumps(trace.get("dag_execution_levels", []), ensure_ascii=False),
        "Node Backends": json.dumps(trace.get("node_backends", {}), ensure_ascii=False),
        "Node Traces": json.dumps(trace.get("node_traces", {}), ensure_ascii=False),
    }


def make_result_row(
    *,
    pipeline_version: str,
    sample_row_id: str,
    query: str,
    ground_truth: str,
    row_metadata: dict[str, Any],
    old_status: str,
    new_output: str,
    new_status: str,
    comments: str,
    started_at: str,
    elapsed_seconds: float,
    trace_fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "Pipeline Version": pipeline_version,
        "Sample Row ID": sample_row_id,
        "Question": query,
        "Ground Truth": ground_truth,
        **row_metadata,
        "Old Status": old_status,
        "New Pipeline Result": new_output,
        "New Status": new_status,
        "Comparison / Comments": comments,
        "Started At": started_at,
        "Elapsed Seconds": elapsed_seconds,
        **trace_fields,
    }


def make_exception_row(
    *,
    pipeline_version: str,
    sample_row_id: str,
    query: str,
    ground_truth: str,
    row_metadata: dict[str, Any],
    old_status: str,
    error_message: str,
    new_status: str,
    comments: str,
    started_at: str,
    elapsed_seconds: float,
    dag_sequence: str,
    trace: dict[str, Any],
) -> dict[str, Any]:
    return {
        "Pipeline Version": pipeline_version,
        "Sample Row ID": sample_row_id,
        "Question": query,
        "Ground Truth": ground_truth,
        **row_metadata,
        "Old Status": old_status,
        "New Pipeline Result": error_message,
        "New Status": new_status,
        "Comparison / Comments": comments,
        "Started At": started_at,
        "Elapsed Seconds": elapsed_seconds,
        "DAG Sequence": dag_sequence,
        "AOP Operator Sequence": " -> ".join(trace.get("operator_sequence", [])) if trace else "",
        "Retrieved Classes": json.dumps(trace.get("retrieved_classes", []), ensure_ascii=False) if trace else "[]",
        "Query Spec": json.dumps(trace.get("query_spec", {}), ensure_ascii=False) if trace else "{}",
        "Generated SPARQL": trace.get("generated_sparql", "") if trace else "",
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
        "Final Query Status": trace.get("final_status", "") if trace else "error",
        "Node Statuses": json.dumps(trace.get("node_statuses", {}), ensure_ascii=False) if trace else "{}",
        "Node Dependencies": json.dumps(trace.get("node_dependencies", {}), ensure_ascii=False) if trace else "{}",
        "DAG Execution Levels": json.dumps(trace.get("dag_execution_levels", []), ensure_ascii=False) if trace else "[]",
    }


def save_report(rows: list[dict[str, Any]], output_filename: str, report_columns: list[str] | None = None) -> None:
    columns = report_columns or REPORT_COLUMNS
    df_report = pd.DataFrame(rows)
    for column in columns:
        if column not in df_report.columns:
            df_report[column] = ""
    df_report = df_report[columns]
    temporary_file = f"{output_filename}.tmp"
    df_report.to_csv(temporary_file, index=False)
    os.replace(temporary_file, output_filename)


def load_resume_state(output_filename: str, pipeline_version: str) -> ResumeState:
    results_list: list[dict[str, Any]] = []
    completed_row_ids: set[str] = set()
    retry_count = 0
    resume_enabled = False

    if not os.path.exists(output_filename):
        return ResumeState(results_list, completed_row_ids, retry_count, resume_enabled)

    existing_report = pd.read_csv(output_filename)
    if "Sample Row ID" not in existing_report.columns:
        return ResumeState(results_list, completed_row_ids, retry_count, resume_enabled)

    if "Pipeline Version" in existing_report.columns:
        stale_mask = existing_report["Pipeline Version"].astype(str).ne(pipeline_version)
    else:
        stale_mask = pd.Series(True, index=existing_report.index)
    status_series = existing_report.get("New Status", "").astype(str).str.upper()
    retry_mask = stale_mask | status_series.isin({"CRASH", "QUOTA_EXHAUSTED"})
    retry_count = int(retry_mask.sum())
    existing_report = existing_report[~retry_mask].copy()
    results_list = existing_report.to_dict(orient="records")
    completed_row_ids = set(existing_report["Sample Row ID"].astype(str))
    resume_enabled = True
    return ResumeState(results_list, completed_row_ids, retry_count, resume_enabled)


def compute_pending_records(
    test_records: list[dict[str, Any]],
    completed_row_ids: set[str],
) -> tuple[list[dict[str, Any]], int]:
    pending_records = []
    for record in test_records:
        row_id = str(record.get("Sample Row ID", ""))
        if row_id in completed_row_ids:
            continue
        pending_records.append(record)
    skipped_count = len(test_records) - len(pending_records)
    return pending_records, skipped_count
