"""Offline saved-plan diagnosis. No production changes, queries, or model calls."""
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPORTS = PACKAGE.parent / "pipelien_output"
sys.path.insert(0, str(PACKAGE / "tests"))
from support import load

csv.field_size_limit(100_000_000)
compile_spec = load("spec_runtime").compile_spec


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def first_array(text, key):
    match = re.search(r'"' + key + r'"\s*:\s*', text)
    if match:
        try:
            return json.JSONDecoder().raw_decode(text[match.end():])[0]
        except ValueError:
            pass
    return None


def main():
    summary, details, identities = {}, [], {}
    for part in ("success_55", "non_success_part1_69", "non_success_part2_68"):
        stem = "v8_multistep_contract_" + part
        grade_rows = rows(REPORTS / ("graded_" + stem + "_terra.csv"))
        debug = {r["Sample Row ID"]: r for r in rows(REPORTS / (stem + "_debug.csv"))}
        manifest = json.loads((REPORTS / (stem + ".csv.manifest.json")).read_text())
        identities[part] = {"run_identity": manifest["run_identity"], "source_differences": [
            f for f, h in manifest["source_files"].items()
            if hashlib.sha256((PACKAGE / f).read_bytes()).hexdigest() != h]}
        summary[part] = {"all": dict(Counter(r["Grade Status"] for r in grade_rows)),
                         "MC": dict(Counter(r["Grade Status"] for r in grade_rows if ":MC-" in r["Sample Row ID"]))}
        for grade in grade_rows:
            if ":MC-" not in grade["Sample Row ID"]:
                continue
            saved = debug[grade["Sample Row ID"]]
            plan = json.loads(saved["Debug Final Spec"] or "{}")
            schemas = {k: v for k, v in plan.get("dataset_schemas", {}).items() if not k.startswith("__spec_")}
            errors = plan.get("contract_errors", [])
            repair = json.loads(saved["Debug Repair Log"] or "{}")
            preview = repair.get("preview", "") if isinstance(repair, dict) else ""
            stages = repair.get("stage_repairs", []) if isinstance(repair, dict) else repair
            first_errors = first_array(preview, "errors") if preview else stages[0].get("errors", []) if stages else []
            first_steps = first_array(preview, "final_steps") if preview else stages[0].get("spec", {}).get("final_steps", []) if stages else []
            result = {"id": grade["Sample Row ID"].split(":")[-1], "question": grade["Question"], "part": part,
                      "grade": grade["Grade Status"], "grade_reason": grade["Grade Reason"],
                      "failure_stage": saved["Failure Stage"], "errors": errors,
                      "first_visible_errors": first_errors, "first_visible_steps": first_steps,
                      "repair_log_truncated": bool(preview),
                      "final_steps": plan.get("final_steps", []), "contract": plan.get("comparative_contract", {}),
                      "schemas": schemas}
            if saved["Failure Stage"] == "Final_Spec" and schemas:
                # Counterfactual compile only: it cannot establish execution or correctness.
                changed = deepcopy(plan)
                changed.pop("comparative_contract", None)
                changed.pop("comparative_contract_required", None)
                result["without_contract_compile_errors"] = compile_spec(changed, schemas)["contract_errors"]
                changed = deepcopy(plan)
                for metric in changed.get("comparative_contract", {}).get("metrics", []):
                    if metric.get("inner_aggregate") == "count_rows":
                        metric["source_columns"] = ["*"]
                result["count_rows_metadata_only_compile_errors"] = compile_spec(changed, schemas)["contract_errors"]
            details.append(result)
    skipped = [r for r in details if r["grade"] == "SKIPPED_EXECUTION_FAILURE"]
    contract_only = [r for r in skipped if r["errors"] and all(e.startswith("comparative_contract:") for e in r["errors"])]
    stats = {
        "MC_questions": len(details), "MC_grades": dict(Counter(r["grade"] for r in details)),
        "skipped_stages": dict(Counter(r["failure_stage"] for r in skipped)),
        "contract_only_failures": len(contract_only),
        "compile_without_contract_passes": sum(r.get("without_contract_compile_errors") == [] for r in skipped),
        "first_missing_contract_all_MC": sum(any("declare the comparison" in e for e in (r["first_visible_errors"] or [])) for r in details),
        "first_missing_contract_skipped_MC": sum(any("declare the comparison" in e for e in (r["first_visible_errors"] or [])) for r in skipped),
        "truncated_repair_logs_all_MC": sum(r["repair_log_truncated"] for r in details),
        "count_metadata_only_compile_pass_ids": [r["id"] for r in skipped if r.get("count_rows_metadata_only_compile_errors") == []],
    }
    patterns = {"population": "required population", "outer_none": "outer aggregate none",
                "source_names": "actual source table", "source_columns": "source columns",
                "missing_contract": "declare the comparison"}
    families = {name: [r["id"] for r in skipped if any(pattern in e for e in r["errors"])] for name, pattern in patterns.items()}
    output = {"stats": stats, "summary": summary, "identities": identities, "overlapping_families": families, "questions": details}
    (Path(__file__).parent / "v8_skip_evidence.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    with (Path(__file__).parent / "v8_mc_skip_review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["ID", "Question", "Grade", "Failure Stage", "Errors", "Compiles without comparative contract", "First visible errors", "Repair log truncated"])
        for r in details:
            writer.writerow([r["id"], r["question"], r["grade"], r["failure_stage"], " | ".join(r["errors"]),
                             r.get("without_contract_compile_errors") == [] if "without_contract_compile_errors" in r else "",
                             " | ".join(r["first_visible_errors"] or []), r["repair_log_truncated"]])
    print(json.dumps({"stats": stats, "families": families, "identities": identities}, indent=2))


if __name__ == "__main__":
    main()
