import datetime
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Callable

import networkx as nx
import pandas as pd

from script_diff_llm.evaluation.reporting import (
    build_trace_fields,
    make_exception_row,
    make_result_row,
)


_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PREFERRED_BENCHMARK_SHEETS = ("Benchmark", "benchmark")
_ALL_BENCHMARK_SHEETS_SENTINELS = {"__ALL__", "ALL_BENCHMARK_SHEETS", "ALL"}
_BENCHMARK_REQUIRED_COLUMNS = {"global_question_id", "question", "ground_truth_answer"}


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(f"{{{_XLSX_MAIN_NS}}}v")
    if value_node is None:
        inline_string = cell.find(f"{{{_XLSX_MAIN_NS}}}is")
        if inline_string is not None:
            return "".join(text_node.text or "" for text_node in inline_string.iter(f"{{{_XLSX_MAIN_NS}}}t"))
        return ""
    raw_value = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return raw_value
    return raw_value


def _xlsx_column_index(cell_reference: str) -> int:
    letters = "".join(character for character in str(cell_reference or "") if character.isalpha()).upper()
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - ord("A") + 1)
    return max(index - 1, 0)


def _read_xlsx_sheet_from_zip(workbook_zip: zipfile.ZipFile, target: str) -> pd.DataFrame:
    normalized_target = target.lstrip("/")
    worksheet_root = ET.fromstring(workbook_zip.read(normalized_target))
    sheet_data = worksheet_root.find(f"{{{_XLSX_MAIN_NS}}}sheetData")
    if sheet_data is None:
        return pd.DataFrame()

    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in workbook_zip.namelist():
        shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
        for string_item in shared_root:
            shared_strings.append(
                "".join(text_node.text or "" for text_node in string_item.iter(f"{{{_XLSX_MAIN_NS}}}t"))
            )

    parsed_rows: list[list[str]] = []
    for row in sheet_data:
        cells = list(row)
        if not cells:
            parsed_rows.append([])
            continue
        max_index = max(_xlsx_column_index(cell.attrib.get("r", "")) for cell in cells)
        values = [""] * (max_index + 1)
        for cell in cells:
            values[_xlsx_column_index(cell.attrib.get("r", ""))] = _xlsx_cell_value(cell, shared_strings)
        parsed_rows.append(values)

    if not parsed_rows:
        return pd.DataFrame()

    header = [str(value or "") for value in parsed_rows[0]]
    body = parsed_rows[1:]
    normalized_body = []
    for row in body:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        normalized_body.append(row[:len(header)])
    return pd.DataFrame(normalized_body, columns=header)


def _combine_benchmark_sheets(sheet_frames: list[pd.DataFrame]) -> pd.DataFrame:
    benchmark_frames = []
    for frame in sheet_frames:
        columns = {str(column) for column in frame.columns}
        if _BENCHMARK_REQUIRED_COLUMNS.issubset(columns):
            benchmark_frames.append(frame)
    if not benchmark_frames:
        return pd.DataFrame()
    return pd.concat(benchmark_frames, ignore_index=True)


def _load_xlsx_sheet_without_openpyxl(sample_file: str, input_sample_sheet: str = "") -> pd.DataFrame:
    with zipfile.ZipFile(sample_file) as workbook_zip:
        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        sheets_parent = workbook_root.find(f"{{{_XLSX_MAIN_NS}}}sheets")
        if sheets_parent is None:
            raise ValueError(f"Workbook {sample_file} has no sheets.")

        workbook_rels = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
            for rel in workbook_rels
        }

        sheets: list[tuple[str, str]] = []
        for sheet in sheets_parent:
            sheet_name = str(sheet.attrib.get("name") or "")
            rel_id = str(sheet.attrib.get(f"{{{_XLSX_REL_NS}}}id") or "")
            target = relationship_targets.get(rel_id, "")
            if target:
                sheets.append((sheet_name, target))
        if not sheets:
            raise ValueError(f"Workbook {sample_file} has no readable worksheet targets.")

        if input_sample_sheet.strip().upper() in _ALL_BENCHMARK_SHEETS_SENTINELS:
            frames = [_read_xlsx_sheet_from_zip(workbook_zip, target) for _, target in sheets]
            combined = _combine_benchmark_sheets(frames)
            if combined.empty:
                raise ValueError(f"Workbook {sample_file} has no benchmark-shaped sheets to combine.")
            return combined

        selected_target = ""
        if input_sample_sheet:
            for sheet_name, target in sheets:
                if sheet_name == input_sample_sheet:
                    selected_target = target
                    break
            if not selected_target:
                available = ", ".join(name for name, _ in sheets)
                raise ValueError(
                    f"Sheet '{input_sample_sheet}' not found in {sample_file}. Available sheets: {available}"
                )
        else:
            for preferred_sheet in _PREFERRED_BENCHMARK_SHEETS:
                for sheet_name, target in sheets:
                    if sheet_name == preferred_sheet:
                        selected_target = target
                        break
                if selected_target:
                    break
            if not selected_target:
                selected_target = sheets[0][1]
        return _read_xlsx_sheet_from_zip(workbook_zip, selected_target)


def load_input_samples(sample_file: str, input_sample_sheet: str = "") -> pd.DataFrame:
    extension = sample_file.rsplit(".", 1)[-1].lower() if "." in sample_file else ""
    if extension in {"xlsx", "xls"}:
        try:
            if input_sample_sheet.strip().upper() in _ALL_BENCHMARK_SHEETS_SENTINELS:
                workbook = pd.read_excel(sample_file, sheet_name=None)
                combined = _combine_benchmark_sheets(list(workbook.values()))
                if combined.empty:
                    raise ValueError(f"Workbook {sample_file} has no benchmark-shaped sheets to combine.")
                return combined
            if input_sample_sheet:
                return pd.read_excel(sample_file, sheet_name=input_sample_sheet)
            return pd.read_excel(sample_file, sheet_name="Benchmark")
        except ImportError:
            return _load_xlsx_sheet_without_openpyxl(sample_file, input_sample_sheet)
        except ValueError:
            if input_sample_sheet:
                raise
            try:
                return pd.read_excel(sample_file)
            except ImportError:
                return _load_xlsx_sheet_without_openpyxl(sample_file, input_sample_sheet)
    return pd.read_csv(sample_file)


def load_ground_truth_overrides(override_file: str) -> dict[str, str]:
    if not override_file:
        return {}
    with open(override_file, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(
            f"Ground truth override file {override_file} must contain a JSON object keyed by question ID."
        )
    overrides: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        overrides[key] = json.dumps(value, ensure_ascii=False, default=str)
    return overrides


def normalize_benchmark_records(
    df_all: pd.DataFrame,
    *,
    offset: int,
    limit: int,
    ground_truth_overrides: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if {"question", "ground_truth_answer"}.issubset(df_all.columns):
        overrides = ground_truth_overrides or {}
        override_count = 0
        ground_truth_series = df_all["ground_truth_answer"].astype(str).copy()
        if overrides:
            question_ids = df_all.get("question_id", pd.Series([""] * len(df_all))).astype(str)
            global_ids = df_all.get("global_question_id", pd.Series([""] * len(df_all))).astype(str)
            updated_values = []
            for original_ground_truth, question_id, global_question_id in zip(
                ground_truth_series.tolist(),
                question_ids.tolist(),
                global_ids.tolist(),
            ):
                replacement = overrides.get(question_id)
                if replacement is None:
                    replacement = overrides.get(global_question_id)
                if replacement is not None:
                    override_count += 1
                    updated_values.append(replacement)
                else:
                    updated_values.append(original_ground_truth)
            ground_truth_series = pd.Series(updated_values, index=df_all.index, dtype="object")

        normalized_records = pd.DataFrame({
            "Sample Row ID": df_all.get("global_question_id", pd.Series(range(1, len(df_all) + 1))).astype(str),
            "Question": df_all["question"].astype(str),
            "Ground Truth": ground_truth_series.astype(str),
            "Difficulty": df_all.get("difficulty", pd.Series([""] * len(df_all))).astype(str),
            "Category": df_all.get("category", pd.Series([""] * len(df_all))).astype(str),
            "Query Type": df_all.get("query_type", pd.Series([""] * len(df_all))).astype(str),
            "Source CSV": df_all.get("source_csv", pd.Series([""] * len(df_all))).astype(str),
            "Status": "NEW_BENCHMARK",
        })
        records = normalized_records.iloc[offset:offset + limit].to_dict(orient="records")
        if override_count:
            print(f"[SYSTEM] Applied full ground-truth overrides to {override_count} benchmark row(s).")
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
