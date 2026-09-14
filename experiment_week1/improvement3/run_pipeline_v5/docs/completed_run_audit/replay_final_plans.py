"""Compare V3 and V4 execution of retained plans on saved samples, without APIs.

This is compatibility evidence, not a new pipeline success/correctness score.
Old truncated JSON and missing declarations cannot be recovered or fabricated.
"""
import csv
import hashlib
import importlib.util
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1]
EXPERIMENT = V4.parent
csv.field_size_limit(2**28)
DECLARATIONS = {"steps", "merge_steps", "pre_steps", "final_steps", "final_measures",
                "projection", "final_output", "output", "final_group_by", "distinct",
                "distinct_on", "rounding", "preserve_null_groups", "output_schema"}


def parse(value, default):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def support_for(package):
    spec = importlib.util.spec_from_file_location("_replay_support_" + package, EXPERIMENT / package / "tests/support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_plan(support, plan, schemas, samples):
    try:
        compiled = support.load("spec_runtime").compile_spec(plan, schemas)
        if compiled["contract_errors"]:
            return {"status": "compile_error", "errors": compiled["contract_errors"]}
        if set(schemas) - set(samples):
            return {"status": "compiled_without_samples", "errors": []}
        output, log = support.load("execution").execute_spec(plan, {name: samples[name] for name in schemas},
                                                              support.registry(), dataset_schemas=schemas)
        errors = support.load("execution").execution_errors(log)
        return {"status": "runtime_error" if errors else "sample_execution_pass",
                "errors": [error.get("error", str(error)) for error in errors], "sample_output_rows": len(output)}
    except Exception as exc:
        return {"status": "exception", "errors": [type(exc).__name__ + ": " + str(exc)]}


def main():
    old = support_for("run_pipeline_v3") if (EXPERIMENT / "run_pipeline_v3/tests/support.py").exists() else None
    new = support_for("run_pipeline_v4")
    previous_path = HERE / "final_plan_replay.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    previous_sources = {source["file"]: source["sha256"] for source in previous.get("sources", [])}
    previous_rows = {(row["source"], row["id"]): row for row in previous.get("records", [])}
    sources, results = [], []
    for name in ("v3_simplified_v7_success_55_debug.csv", "v3_simplified_v7_non_success_137_debug.csv"):
        path = EXPERIMENT / "pipelien_output" / name
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        sources.append({"file": name, "sha256": digest})
        for row in csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))):
            saved = parse(row.get("Debug Final Spec"), None)
            record = {"id": row["Sample Row ID"], "source": name, "original_status": row["New Status"]}
            results.append(record)
            if saved is None:
                record["skip"] = "old_json_truncated_or_invalid"
                continue
            if not isinstance(saved, dict) or not DECLARATIONS.intersection(saved):
                record["skip"] = "no_retained_final_declarations"
                continue
            schemas = {key: value for key, value in saved.get("dataset_schemas", {}).items() if not key.startswith("__spec_step_")}
            if not schemas:
                record["skip"] = "no_retained_input_schemas"
                continue
            audit = parse(row.get("Debug Operator Audit"), [])
            samples = {}
            if isinstance(audit, list):
                for entry in audit:
                    if entry.get("operator") == "Processing_Spec" and entry.get("subquestion_id"):
                        samples[str(entry["subquestion_id"]) + "_processed"] = entry.get("output_sample", [])
            plan = {key: value for key, value in saved.items() if key in DECLARATIONS}
            record["sample_input_rows"] = {key: len(value) for key, value in samples.items()}
            prior = previous_rows.get((name, row["Sample Row ID"]), {})
            record["v3"] = run_plan(old, plan, schemas, samples) if old else (
                prior["v3"] if previous_sources.get(name) == digest and "v3" in prior else
                {"status": "baseline_not_available", "errors": []})
            record["v4"] = run_plan(new, plan, schemas, samples)
    replayed = [row for row in results if "v4" in row]
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "sources": sources,
        "baseline_origin": "current V3 execution" if old else "Previously saved offline V3 results on identical source hashes; V3 directory unavailable.",
        "scope": "Same recorded plans and schemas; at most five saved rows per branch. No model, database query, full-result comparison, or correctness grading.",
        "saved_rows": len(results), "replayed": len(replayed),
        "skips": dict(Counter(row["skip"] for row in results if "skip" in row)),
        "v3": dict(Counter(row["v3"]["status"] for row in replayed)),
        "v4": dict(Counter(row["v4"]["status"] for row in replayed)),
        "newly_executable_on_samples": sum(row["v3"]["status"] != "sample_execution_pass" and row["v4"]["status"] == "sample_execution_pass" for row in replayed),
        "sample_execution_regressions": [row["id"] for row in replayed if row["v3"]["status"] == "sample_execution_pass" and row["v4"]["status"] != "sample_execution_pass"],
        "records": results,
    }
    (HERE / "final_plan_replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "sources"}}, indent=2))


if __name__ == "__main__":
    main()
