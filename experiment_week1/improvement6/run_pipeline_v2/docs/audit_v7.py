"""Snapshot completed CSV rows and reference SQL for an offline, reproducible review.

This file is an analysis tool, never imported by inference. Re-run after grading
finishes to refresh the snapshot. No model or database calls are made.
"""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
OUT = ROOT / "docs" / "v7_audit"
csv.field_size_limit(20_000_000)


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {"captured_at": datetime.now(timezone.utc).isoformat(), "files": {}, "cohorts": {}}
    def read(path):
        raw = path.read_bytes()
        manifest["files"][path.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

    workbook = BASE.parent / "improvement2/dataset/verification_results_v2_sql_correct_442.xlsx"
    manifest["reference_sha256"] = hashlib.sha256(workbook.read_bytes()).hexdigest()
    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    values = iter(wb["SQL_Correct_442"].values)
    header = next(values)
    refs = {r["global_question_id"]: r for row in values if (r := dict(zip(header, row)))}
    wb.close()
    evidence = []
    for cohort in ("success_55", "non_success_part1_69", "non_success_part2_68"):
        name = "v7_multistep_contract_" + cohort
        raw = read(BASE / "pipelien_output" / (name + ".csv"))
        debug = {r["Sample Row ID"]: r for r in read(BASE / "pipelien_output" / (name + "_debug.csv"))}
        grades = {r["Sample Row ID"]: r for r in read(BASE / "pipelien_output" / ("graded_" + name + "_terra.csv"))}
        inputs = read(BASE / "dataset" / ("v4_input_" + cohort + ".csv"))
        saved_manifest = json.loads((BASE / "pipelien_output" / (name + ".csv.manifest.json")).read_text(encoding="utf-8-sig"))
        hashes = saved_manifest.get("source_files", {})
        drift = [name for name, digest in hashes.items()
                 if not (BASE / "run_pipeline_v7" / name).exists()
                 or hashlib.sha256((BASE / "run_pipeline_v7" / name).read_bytes()).hexdigest() != digest]
        manifest["cohorts"][cohort] = {"input_rows": len(inputs), "raw_rows": len(raw), "debug_rows": len(debug),
            "graded_rows": len(grades), "grades": dict(Counter(r.get("Grade Status") for r in grades.values())),
            "source_drift": drift, "source_hash_count": len(hashes), "run_identity": saved_manifest.get("run_identity")}
        for row in raw:
            key = row["Sample Row ID"]
            ref = refs.get(key, {})
            trace = debug.get(key, {})
            grade = grades.get(key, {})
            parsed = {}
            for field in ("Debug Subquestions", "Debug Query Specs", "Debug SPARQL", "Debug Final Spec", "Debug Execution Log", "Debug Repair Log"):
                try:
                    parsed[field] = json.loads(trace.get(field) or "null")
                except (ValueError, TypeError):
                    parsed[field] = {"unparseable": trace.get(field)}
            evidence.append({"id": key, "cohort": cohort, "question": row["Question"],
                "grade": grade.get("Grade Status", "PENDING"), "reason": grade.get("Grade Reason", ""),
                "status": row["New Status"], "failure_stage": row.get("Failure Stage"),
                "answer": row["New Pipeline Result"], "reference": row["Ground Truth"],
                "question_matches_reference": row["Question"] == ref.get("question"),
                "sql": ref.get("sql_query"), "sql_reason": ref.get("sql_reason"), **parsed})
    mc = [r for r in evidence if ":MC-" in r["id"]]
    manifest["all_grades"] = dict(Counter(r["grade"] for r in evidence))
    manifest["mc_grades"] = dict(Counter(r["grade"] for r in mc))
    (OUT / "snapshot.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "questions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["id", "cohort", "question", "grade", "reason", "status", "failure_stage", "sql", "sql_reason"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(evidence)
    lines = []
    for r in mc:
        plan = r.get("Debug Final Spec") or {}
        lines += [r["id"] + " " + r["grade"], r["question"], r["reason"], "SQL: " + str(r["sql"]),
                  "BRANCHES: " + json.dumps(r["Debug Subquestions"], ensure_ascii=False),
                  "PLAN: " + json.dumps({k: v for k, v in plan.items() if k in {"final_steps", "projection", "contract_errors"}}, ensure_ascii=False), ""]
    (OUT / "comparative_digest.txt").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
