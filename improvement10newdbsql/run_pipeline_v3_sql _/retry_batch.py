"""Freeze a QUERY_SPEC_ERROR-only input cohort without altering prior reports."""

import csv
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .run_identity import sha256_file


EXECUTION_FAILURE_STATUSES = frozenset({
    "QUERY_UNDERSTANDING_ERROR", "DECOMPOSITION_ERROR", "QUERY_SPEC_ERROR",
    "PROCESSING_SPEC_ERROR", "FINAL_SPEC_ERROR", "EXECUTION_ERROR",
    "PRE_SCAN_ERROR", "SCAN_ERROR", "CRASH", "TRANSIENT_ERROR", "QUOTA_EXHAUSTED",
})


def read_retry_report(source_report):
    """Read the saved cohort losslessly; reject reports that cannot be keyed safely."""
    csv.field_size_limit(2**30)
    with Path(source_report).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if not {"Sample Row ID", "Question", "Ground Truth", "New Status"}.issubset(fields):
            raise ValueError("Retry report lacks required columns.")
        rows = list(reader)
    ids = [row["Sample Row ID"] for row in rows]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Retry report must have unique, nonempty Sample Row IDs.")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Retry report contains malformed CSV rows.")
    return fields, rows


def failed_retry_rows(rows):
    return [row for row in rows if row["New Status"].strip().upper() in EXECUTION_FAILURE_STATUSES]


def graded_retry_rows(saved_rows, graded_report):
    """Use grades only to select IDs; preserve raw rows and reject stale grades."""
    _, grades = read_retry_report(graded_report)
    by_id = {row['Sample Row ID']: row for row in grades}
    selected = []
    identity_fields = ('Question', 'Ground Truth', 'New Pipeline Result', 'Category', 'Target Model')
    for row in saved_rows:
        if row['New Status'].strip().upper() in EXECUTION_FAILURE_STATUSES:
            selected.append(row)
            continue
        grade = by_id.get(row['Sample Row ID'])
        if not grade or grade['New Status'].strip().upper() not in {'MISMATCH', 'PARTIAL'}:
            continue
        if any(str(row.get(field, '')) != str(grade.get(field, '')) for field in identity_fields):
            continue  # Grade refers to an older answer; do not retry the new one.
        selected.append(row)
    return selected


def retry_and_pending_rows(saved_rows, input_rows):
    """Retry execution failures and unseen manifest IDs, preserving successes."""
    ids = [str(row.get('Sample Row ID', '')) for row in input_rows]
    if any(not identity for identity in ids) or len(ids) != len(set(ids)):
        raise ValueError('The restart input must have unique, nonempty Sample Row IDs.')
    saved = {str(row['Sample Row ID']): row for row in saved_rows}
    if set(saved) - set(ids):
        raise ValueError('Saved report contains IDs absent from the restart input.')
    selected = []
    for row in input_rows:
        previous = saved.get(str(row['Sample Row ID']))
        if previous is None:
            selected.append(row)
        else:
            if any(str(previous.get(field, '')) != str(row.get(field, '')) for field in ('Question', 'Ground Truth')):
                raise ValueError('Saved question/reference differs from the restart input.')
            if previous['New Status'].strip().upper() in EXECUTION_FAILURE_STATUSES:
                selected.append(previous)
    return selected


def prepare_in_place_retry(source_report, current_manifest, selected_ids, companion_paths=()):
    """Caller holds the report lock. Back up originals and record mixed-run provenance."""
    source = Path(source_report)
    manifest_path = Path(str(source) + ".manifest.json")
    if not manifest_path.is_file():
        raise ValueError("In-place retry requires the original source/data manifest.")
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("questions", "sqlite_database"):
        old_hash = previous.get("input_files", {}).get(name, {}).get("sha256")
        new_hash = current_manifest.get("input_files", {}).get(name, {}).get("sha256")
        if not old_hash or old_hash != new_hash:
            raise ValueError(f"In-place retry requires unchanged {name}; use a separate report for changed inputs.")
    backup = source.parent / ("backup_before_retry_" + str(time.time_ns()))
    backup.mkdir()
    paths = {source.resolve(), manifest_path.resolve()}
    paths.update(Path(path).resolve() for path in companion_paths)
    for path in paths:
        if path.is_file():
            shutil.copy2(path, backup / path.name)
    manifest = {**current_manifest, "mixed_results": True,
                "retry_history": list(previous.get("retry_history", [])) + [{
                    "previous_run_identity": previous.get("run_identity"),
                    "retry_run_identity": current_manifest["run_identity"],
                    "backup_directory": str(backup.resolve()),
                    "selected_ids": list(selected_ids), "completed_ids": [],
                }]}
    save_retry_manifest(manifest_path, manifest)
    return manifest


def save_retry_manifest(path, manifest):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, path)


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
