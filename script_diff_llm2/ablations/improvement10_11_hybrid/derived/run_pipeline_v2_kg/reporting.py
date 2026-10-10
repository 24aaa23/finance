"""Dataset loading and lossless JSONL-report helpers."""

import json
from pathlib import Path

from .common import INPUT_SAMPLE_SHEET, os, pd


def load_input_samples(sample_file: str) -> pd.DataFrame:
    """Load benchmark questions from CSV, Excel, JSON, or JSONL."""
    extension = os.path.splitext(sample_file)[1].lower()
    if extension in {".xlsx", ".xls"}:
        if INPUT_SAMPLE_SHEET:
            return pd.read_excel(sample_file, sheet_name=INPUT_SAMPLE_SHEET)
        return pd.read_excel(sample_file)
    if extension == ".jsonl":
        return pd.read_json(sample_file, lines=True, dtype=False)
    if extension == ".json":
        return pd.read_json(sample_file, dtype=False)
    return pd.read_csv(sample_file)


def _decode_json_value(value):
    """Expose table-shaped answers as JSON values in the JSONL sidecar."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value or value[0] not in "[{":
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def jsonl_result_record(record: dict) -> dict:
    """Return a lossless, grader-friendly representation of a report row."""
    payload = dict(record)
    payload["ground_truth_json"] = _decode_json_value(payload.get("Ground Truth", ""))
    payload["pipeline_result_json"] = _decode_json_value(payload.get("New Pipeline Result", ""))
    return payload


def write_jsonl_atomic(path: str, records: list[dict]) -> None:
    """Write one complete JSON object per line, replacing partial files atomically."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(jsonl_result_record(record), ensure_ascii=False, default=str))
            handle.write("\n")
    os.replace(temporary, destination)
