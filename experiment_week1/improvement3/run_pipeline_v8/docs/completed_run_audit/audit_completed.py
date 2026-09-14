"""Summarize saved pipeline reports without grading or contacting any service."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**28)
ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "pipelien_output"
STEMS = [
    "v3_simplified_v7_success_55", "v3_simplified_v7_non_success_137",
    "v4_typed_repair_success_55", "v4_typed_repair_non_success_137",
]
FAMILIES = {
    "missing_explicit_final_plan": "must declare an explicit final plan",
    "duplicate_join_column": "ambiguous duplicate column",
    "missing_selected_input_field": "field does not exist on the selected input",
    "text_forced_to_numeric": "Non-numeric value in arithmetic column",
    "missing_join_keys": "explicit equal-length join_key",
    "unsupported_aggregate_shape": "unsupported aggregate/filter operation: aggregate",
    "unresolved_dataset_name": "Step input dataset does not exist",
    "independent_output_merge": "Independent outputs require an explicit merge",
    "source_dependency_rejection": "Raw retrieval branches must be independently executable",
    "upstream_missing_requirements": "Upstream requirements unavailable",
    "unsupported_join_type_alias": "unsupported join type: left_outer",
    "sql_style_projection_alias": "AS ",
}


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize(rows, debug):
    failures = [row for row in rows if row["New Status"] != "PIPELINE_SUCCESS"]
    evidence = []
    for row in failures:
        trace = debug.get(row["Sample Row ID"], {})
        # Query_Spec failures sometimes leave the top-level reason blank.
        reason = row.get("Validation Reason") or trace.get("Debug Validation Feedback") or ""
        repairs = json.loads(trace.get("Debug Repair Log") or "{}")
        if not reason:
            reason = "; ".join(
                str(error)
                for repair in repairs.get("stage_repairs", [])[-1:]
                for error in repair.get("errors", [])
            )
        evidence.append({
            "id": row["Sample Row ID"], "status": row["New Status"],
            "question": row["Question"], "reason": reason,
            "families": [name for name, text in FAMILIES.items() if text.casefold() in reason.casefold()],
        })
    empty_success_ids = [
        row["Sample Row ID"] for row in rows
        if row["New Status"] == "PIPELINE_SUCCESS" and row["New Pipeline Result"].strip() in ("[]", "{}", "null")
    ]
    return {
        "rows": len(rows), "unique_ids": len({r["Sample Row ID"] for r in rows}),
        "versions": dict(Counter(row["Pipeline Version"] for row in rows)),
        "statuses": dict(Counter(row["New Status"] for row in rows)),
        "failure_family_counts_overlapping": dict(Counter(family for row in evidence for family in row["families"])),
        "empty_success_ids": empty_success_ids, "failures": evidence,
    }


def main():
    result = {"reports": {}, "comparisons": {}}
    groups = {}
    for stem in STEMS:
        rows = read_rows(REPORTS / (stem + ".csv"))
        debug = {r["Sample Row ID"]: r for r in read_rows(REPORTS / (stem + "_debug.csv"))}
        record = summarize(rows, debug)
        manifest = json.loads((REPORTS / (stem + ".csv.manifest.json")).read_text(encoding="utf-8"))
        record["manifest_configuration"] = manifest["configuration"]
        record["manifest_source_count"] = len(manifest["source_files"])
        record["current_v3_source_mismatches"] = [
            relative for relative, expected in manifest["source_files"].items()
            if not (ROOT / "run_pipeline_v3" / relative).exists()
            or hashlib.sha256((ROOT / "run_pipeline_v3" / relative).read_bytes()).hexdigest() != expected
        ]
        expected_rows = read_rows(Path(manifest["input_files"]["questions"]["path"]))
        expected_ids = {r.get("Sample Row ID") for r in expected_rows}
        record["input_rows"] = len(expected_rows)
        record["missing_input_ids"] = sorted(expected_ids - {r["Sample Row ID"] for r in rows})
        result["reports"][stem] = record
        key = "v3" if stem.startswith("v3_") else "v4_saved_typed_repair"
        groups.setdefault(key, []).extend(rows)
    for group, rows in groups.items():
        result["comparisons"][group] = {"rows": len(rows), "statuses": dict(Counter(r["New Status"] for r in rows))}
    grade_rows = read_rows(REPORTS / "graded_v3_simplified_v7_success_55_terra.csv")
    result["v3_grade_subset"] = {
        "rows": len(grade_rows), "grades": dict(Counter(r["Terra Grade Status"] for r in grade_rows)),
        "nonmatch_evidence": [{"id": r["Sample Row ID"], "grade": r["Terra Grade Status"], "reason": r["Terra Grade Reason"]}
                              for r in grade_rows if r["Terra Grade Status"] != "MATCH"],
    }
    output = Path(__file__).with_name("saved_run_audit.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for stem, record in result["reports"].items():
        print(stem, record["rows"], record["statuses"])
        print("Failure families (overlap):", record["failure_family_counts_overlapping"])
        print("Source mismatches to current v3:", record["current_v3_source_mismatches"])
        print("Missing input rows:", len(record["missing_input_ids"]))
    print("Grades", result["v3_grade_subset"]["grades"])
    print("Wrote", output)


if __name__ == "__main__":
    main()
