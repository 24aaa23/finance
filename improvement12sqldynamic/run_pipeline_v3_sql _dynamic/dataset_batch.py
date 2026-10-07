"""Prepare the eight-sheet benchmark as independent, lossless JSONL manifests."""

from __future__ import annotations

import json
import csv
import io
import re
from pathlib import Path
from typing import Any, Iterable



QUESTION_TYPE_SHEETS = (
    "Benchmark",
    "At-Risk Critical",
    "Batch Status",
    "Enrichment Context",
    "Multi-Step Comparative",
    "Reference Compliance",
    "Scoring Quantitative",
    "Temporal Transaction",
)

REQUIRED_COLUMNS = {
    "global_question_id",
    "question_id",
    "question",
    "ground_truth_answer",
}


def question_type_slug(name: str) -> str:
    """Create stable folder names from workbook sheet names."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _read_jsonl_answers(path: Path) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or "question_id" not in item:
            raise ValueError(f"{path}:{line_number} must contain an object with question_id.")
        answer = item.get("ground_truth_answer", item.get("answer", item.get("result")))
        answers[str(item["question_id"])] = answer
    return answers


def load_full_answer_overrides(path: str | Path) -> dict[str, Any]:
    """Load answer overrides from a keyed JSON object or record-oriented JSONL."""
    if path is None:
        return {}
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        return _read_jsonl_answers(source)
    value = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        return {str(key): answer for key, answer in value.items()}
    if isinstance(value, list):
        answers: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict) or "question_id" not in item:
                raise ValueError(f"{source} must be keyed by question_id or contain question_id records.")
            answers[str(item["question_id"])] = item.get(
                "ground_truth_answer", item.get("answer", item.get("result"))
            )
        return answers
    raise ValueError(f"Unsupported full-answer JSON structure in {source}.")


def _json_safe(value: Any) -> Any:
    import pandas as pd
    if pd.isna(value):
        return ""
    return value.item() if hasattr(value, "item") else value


def prepare_question_type_manifests(
    workbook: str | Path,
    full_answers: str | Path,
    output_root: str | Path,
    sheets: Iterable[str] | None = None,
) -> dict[str, Path]:
    """Create one JSONL input manifest in each requested type's output folder."""
    import pandas as pd
    workbook_path = Path(workbook)
    output_path = Path(output_root)
    requested_sheets = tuple(sheets or QUESTION_TYPE_SHEETS)
    with pd.ExcelFile(workbook_path) as excel_workbook:
        available_sheets = set(excel_workbook.sheet_names)
    missing_sheets = [sheet for sheet in requested_sheets if sheet not in available_sheets]
    if missing_sheets:
        raise ValueError(f"Workbook is missing expected question sheets: {', '.join(missing_sheets)}")

    answer_overrides = load_full_answer_overrides(full_answers)
    manifests: dict[str, Path] = {}
    seen_question_ids: set[str] = set()
    for sheet in requested_sheets:
        frame = pd.read_excel(workbook_path, sheet_name=sheet, dtype=object)
        missing_columns = REQUIRED_COLUMNS.difference(frame.columns)
        if missing_columns:
            raise ValueError(f"Sheet '{sheet}' is missing columns: {', '.join(sorted(missing_columns))}")
        records = []
        for source_record in frame.to_dict(orient="records"):
            record = {key: _json_safe(value) for key, value in source_record.items()}
            question_id = str(record["question_id"])
            if question_id in seen_question_ids:
                raise ValueError(f"Duplicate question_id in selected sheets: {question_id}")
            seen_question_ids.add(question_id)
            record["dataset_type"] = sheet
            record["ground_truth_source"] = "excel"
            if question_id in answer_overrides:
                record["ground_truth_answer"] = json.dumps(answer_overrides[question_id], ensure_ascii=False)
                record["ground_truth_source"] = "full_answer_json"
            records.append(record)

        type_dir = output_path / question_type_slug(sheet)
        type_dir.mkdir(parents=True, exist_ok=True)
        manifest = type_dir / "input_questions.jsonl"
        payload = "".join(json.dumps(record, ensure_ascii=False, default=str) + "\n" for record in records)
        archived = [{"Sample Row ID": str(row["global_question_id"]), "Question": str(row["question"]),
                     "Ground Truth": row["ground_truth_answer"], "Dataset Type": sheet} for row in records]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["Sample Row ID", "Question", "Ground Truth", "Dataset Type"])
        writer.writeheader()
        writer.writerows(archived)
        outputs = {manifest: payload, type_dir / "input_questions.csv": buffer.getvalue()}
        for path, text in outputs.items():
            if path.exists() and path.read_bytes() != text.encode("utf-8"):
                raise ValueError(f"Inputs changed: {path}. Use a fresh output root to preserve this run.")
        for path, text in outputs.items():
            if not path.exists():
                path.write_bytes(text.encode("utf-8"))
        manifests[sheet] = manifest
    return manifests
