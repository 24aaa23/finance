"""Freeze a QUERY_SPEC_ERROR-only input cohort without altering prior reports."""

import csv
import io
import json
import os
import sys
from pathlib import Path

from .run_identity import sha256_file


def prepare_query_spec_retry(source_report, retry_dir):
    """Return (manifest, count); reuse the frozen cohort when resuming.

    The caller holds the source and destination report locks. A fresh cohort
    reads only the existing CSV, never the workbook or unattempted questions.
    """
    source = Path(source_report).resolve()
    destination = Path(retry_dir) / "input_questions.jsonl"
    if destination.exists():
        records = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            if record.get("Retry Source Report") != str(source) or record.get("Retry Source Status") != "QUERY_SPEC_ERROR":
                raise ValueError(f"Retry manifest does not belong to this source: {destination}")
        return destination, len(records)
    if (Path(retry_dir) / "raw_pipeline_v9.csv").exists():
        raise ValueError("Retry report exists without its frozen input manifest; use a new output root.")
    if not source.is_file():
        raise FileNotFoundError(f"No saved SQL report to retry: {source}")
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 10
    # Take one snapshot while the source report lock is held.
    content = source.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content, newline=""))
    required = {"Sample Row ID", "Question", "Ground Truth", "New Status"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f"Source report lacks required columns: {source}")
    rows = list(reader)
    ids = [row["Sample Row ID"] for row in rows]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Source report must have unique, nonempty Sample Row IDs.")
    selected = [row for row in rows if row["New Status"].strip().upper() == "QUERY_SPEC_ERROR"]
    if not selected:
        return destination, 0
    fingerprint = sha256_file(source)
    identity_path = Path(str(source) + ".manifest.json")
    identity = json.loads(identity_path.read_text(encoding="utf-8")) if identity_path.exists() else {}
    fields = ("Sample Row ID", "Question", "Ground Truth", "Difficulty", "Category", "Query Type", "Source CSV", "Dataset Type")
    records = [{**{key: row.get(key, "") for key in fields},
                "Retry Source Report": str(source), "Retry Source SHA256": fingerprint,
                "Retry Source Run Identity": identity.get("run_identity", ""),
                "Retry Source Status": "QUERY_SPEC_ERROR"} for row in selected]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temporary, destination)
    return destination, len(records)


def completed_retry_ids(records):
    """Rerun only remaining Query_Spec failures; retain all other outcomes."""
    return {str(row["Sample Row ID"]) for row in records
            if str(row.get("New Status", "")).strip().upper() != "QUERY_SPEC_ERROR"}


def replace_retry_result(records, result):
    """Checkpoint one replacement without discarding not-yet-retried failures."""
    for index, existing in enumerate(records):
        if str(existing["Sample Row ID"]) == str(result["Sample Row ID"]):
            records[index] = result
            return
    records.append(result)
