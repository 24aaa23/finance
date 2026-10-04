#!/usr/bin/env python3
"""Split a 1,000-row report into eight grader inputs and recombine outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path


FIELD_LIMIT = sys.maxsize
while True:
    try:
        csv.field_size_limit(FIELD_LIMIT)
        break
    except OverflowError:
        FIELD_LIMIT //= 10

SHARD_COUNT = 8
ROWS_PER_SHARD = 125
EXPECTED_ROWS = SHARD_COUNT * ROWS_PER_SHARD


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_ids(rows: list[dict[str, str]], label: str) -> list[str]:
    ids = [row.get("Sample Row ID", "") for row in rows]
    if not all(ids):
        raise ValueError(f"{label} contains an empty Sample Row ID")
    if len(ids) != len(set(ids)):
        duplicates = [key for key, count in Counter(ids).items() if count > 1]
        raise ValueError(f"{label} contains duplicate IDs: {duplicates[:5]}")
    return ids


def split(raw_report: Path, work_dir: Path) -> None:
    fieldnames, rows = read_csv(raw_report)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"Expected {EXPECTED_ROWS} raw rows, found {len(rows)}")
    ids = validate_ids(rows, "raw report")
    inputs = work_dir / "input"
    for index in range(SHARD_COUNT):
        start = index * ROWS_PER_SHARD
        shard = rows[start:start + ROWS_PER_SHARD]
        write_csv(inputs / f"shard_{index + 1:02d}.csv", fieldnames, shard)
    manifest = {
        "raw_report": str(raw_report.resolve()),
        "raw_sha256": sha256(raw_report),
        "row_count": len(rows),
        "unique_id_count": len(set(ids)),
        "shard_count": SHARD_COUNT,
        "rows_per_shard": ROWS_PER_SHARD,
        "ordered_ids": ids,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {SHARD_COUNT} shards with {ROWS_PER_SHARD} rows each in {inputs}")


def combine_if_ready(work_dir: Path, combined_report: Path) -> bool:
    manifest = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
    ordered_ids = manifest["ordered_ids"]
    graded_dir = work_dir / "graded"
    all_rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    for index in range(1, SHARD_COUNT + 1):
        path = graded_dir / f"shard_{index:02d}_graded.csv"
        if not path.exists():
            print(f"Combination deferred: missing {path}")
            return False
        shard_fields, shard_rows = read_csv(path)
        if len(shard_rows) != ROWS_PER_SHARD:
            print(f"Combination deferred: {path} has {len(shard_rows)}/{ROWS_PER_SHARD} rows")
            return False
        if not fieldnames:
            fieldnames = shard_fields
        elif shard_fields != fieldnames:
            raise ValueError(f"Column mismatch in {path}")
        all_rows.extend(shard_rows)

    ids = validate_ids(all_rows, "graded shards")
    if set(ids) != set(ordered_ids):
        missing = sorted(set(ordered_ids) - set(ids))
        extra = sorted(set(ids) - set(ordered_ids))
        raise ValueError(f"Graded ID mismatch; missing={missing[:5]}, extra={extra[:5]}")
    by_id = {row["Sample Row ID"]: row for row in all_rows}
    ordered_rows = [by_id[sample_id] for sample_id in ordered_ids]
    write_csv(combined_report, fieldnames, ordered_rows)

    statuses = Counter(row.get("New Status", "") for row in ordered_rows)
    summary = {
        "combined_report": str(combined_report.resolve()),
        "row_count": len(ordered_rows),
        "unique_id_count": len(ids),
        "status_counts": dict(sorted(statuses.items())),
        "grader_models": sorted({row.get("Direct LLM Grader Model", "") for row in ordered_rows}),
        "combined_sha256": sha256(combined_report),
    }
    summary_path = combined_report.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    split_parser = subparsers.add_parser("split")
    split_parser.add_argument("--raw-report", type=Path, required=True)
    split_parser.add_argument("--work-dir", type=Path, required=True)
    combine_parser = subparsers.add_parser("combine-if-ready")
    combine_parser.add_argument("--work-dir", type=Path, required=True)
    combine_parser.add_argument("--combined-report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "split":
        split(args.raw_report, args.work_dir)
    else:
        combine_if_ready(args.work_dir, args.combined_report)


if __name__ == "__main__":
    main()
