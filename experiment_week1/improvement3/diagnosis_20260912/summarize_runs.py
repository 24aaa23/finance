"""Reproduce counts from existing pipeline/grade logs, with exact ID matching."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**28)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NEW = HERE.parent / "pipelien_output"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    paths = {
        "new_first100": NEW / "v1_queries_1_to_100_debug.csv",
        "new_last92": NEW / "v1_queries_351_to_442_debug.csv",
        "new_grades": NEW / "graded_v1_pipeline_success_terra.csv",
        "old_grades": ROOT / "query_specs_improevemnt/improvement1/pipelien_output/graded_raw_pipeline_442_improvement1_gpt_5_6_terra.csv",
        "baseline_grades": ROOT / "query_specs_improevemnt/improvement0/base_pipeline_gpt_oss_120b_terra (1).csv",
    }
    tables = {name: read(path) for name, path in paths.items()}
    debug = tables["new_first100"] + tables["new_last92"]
    by_id = {row["Sample Row ID"]: row for row in debug}
    assert len(by_id) == len(debug), "Duplicate query IDs in debug files"
    new_grades = {row["Sample Row ID"]: row for row in tables["new_grades"]}
    old = {row["Sample Row ID"]: row for row in tables["old_grades"]}
    baseline = {row["Sample Row ID"]: row for row in tables["baseline_grades"]}
    assert all(q in old and q in baseline for q in by_id)
    assert set(new_grades) == {q for q, r in by_id.items() if r["New Status"] == "PIPELINE_SUCCESS"}
    assert all(old[q]["Ground Truth"] == baseline[q]["Ground Truth"] for q in old)
    assert all(old[q]["Ground Truth"] == new_grades[q]["Ground Truth"] for q in new_grades)

    comparison = {}
    for name, records, grade_key in [("new", new_grades, "Terra Grade Status"),
                                      ("old", old, "New Status"),
                                      ("baseline", baseline, "Grader Verdict")]:
        matched = sum(records.get(q, {}).get(grade_key) == "MATCH" for q in by_id)
        comparison[name] = {"same192_matches": matched,
                            "same192_percent": round(100 * matched / len(by_id), 2),
                            "file_rows": len(records),
                            "file_grade_counts": dict(Counter(r[grade_key] for r in records.values())),
                            "version_labels": sorted({r["Pipeline Version"] for r in records.values()})}

    per_range = {}
    for name in ["new_first100", "new_last92"]:
        queries = tables[name]
        per_range[name] = {"rows": len(queries), "status_counts": dict(Counter(r["New Status"] for r in queries)),
                           "grade_counts": dict(Counter(new_grades[r["Sample Row ID"]]["Terra Grade Status"]
                                                        for r in queries if r["Sample Row ID"] in new_grades))}
    patterns = {
        "missing_step_dataset": "step input dataset does not exist:",
        "missing_final_measure_dataset": "Final_Spec measure input dataset does not exist:",
        "missing_projection_source": "Final_Spec projection fields have no source or producing step:",
        "processing_output_no_lineage": "Processing_Spec output_schema contains fields with no lineage",
        "output_overwrites_field": "overwrites an existing field",
    }
    affected = {key: set() for key in patterns}
    repeated = set()
    stage_queries, stage_events, decomposition_queries, decomposition_events = 0, 0, 0, 0
    for q, row in by_id.items():
        repairs = json.loads(row["Debug Repair Log"] or "{}")
        stage = repairs.get("stage_repairs", [])
        decomp = repairs.get("decomposition_repairs", [])
        stage_queries += bool(stage)
        stage_events += len(stage)
        decomposition_queries += bool(decomp)
        decomposition_events += len(decomp)
        previous = {}
        for event in stage:
            errors = event.get("errors", [])
            for key, pattern in patterns.items():
                if any(pattern in str(error) for error in errors):
                    affected[key].add(q)
            stage_name = event.get("stage")
            if errors and previous.get(stage_name) == errors:
                repeated.add(q)
            previous[stage_name] = errors

    broken_truths = []
    for q, row in old.items():
        try:
            json.loads(row["Ground Truth"])
        except json.JSONDecodeError:
            broken_truths.append({"id": q, "characters": len(row["Ground Truth"]), "new_success": q in new_grades})

    paired = Counter()
    regressions = []
    for q, row in by_id.items():
        old_match = old[q]["New Status"] == "MATCH"
        new_match = new_grades.get(q, {}).get("Terra Grade Status") == "MATCH"
        paired[f"old_{old_match}_new_{new_match}"] += 1
        if old_match and not new_match:
            regressions.append({"id": q, "question": row["Question"], "new_status": row["New Status"],
                                "new_grade": new_grades.get(q, {}).get("Terra Grade Status", "not graded")})

    stats = {
        "interpretation": "Counts of existing grader labels, not independent exact regrading. New evaluation covers only 192 of 442 queries.",
        "source_sha256": {name: {"path": str(path.relative_to(ROOT)),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                          for name, path in paths.items()},
        "rows": len(debug), "status_counts": dict(Counter(r["New Status"] for r in debug)),
        "new_grade_counts": dict(Counter(r["Terra Grade Status"] for r in new_grades.values())),
        "same_id_comparison": comparison, "per_range": per_range,
        "repairs": {"queries_with_stage_repairs": stage_queries, "stage_events": stage_events,
                    "queries_with_decomposition_repairs": decomposition_queries, "decomposition_events": decomposition_events,
                    "queries_repeating_identical_same_stage_errors": len(repeated),
                    "overlapping_error_families": {k: {"queries": len(v), "ids": sorted(v)} for k, v in affected.items()}},
        "invalid_truth_json": broken_truths, "paired_old_new": dict(paired), "old_match_regressions": regressions,
    }
    (HERE / "statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({key: stats[key] for key in ["rows", "status_counts", "new_grade_counts", "same_id_comparison", "per_range", "paired_old_new"]}, indent=2))
    print("Invalid ground truth JSON:", len(broken_truths), "; lengths:", dict(Counter(x["characters"] for x in broken_truths)))
    print("Stage repairs:", stage_queries, "queries,", stage_events, "events; repeated identical:", len(repeated))
    print("Decomposition repairs:", decomposition_queries, "queries,", decomposition_events, "events")
    print("Overlapping error families:", {k: len(v) for k, v in affected.items()})


if __name__ == "__main__":
    main()
