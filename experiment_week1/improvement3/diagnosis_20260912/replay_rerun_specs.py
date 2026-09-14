"""Recompile actual logged final plans offline, without clients, queries, or API calls.

The default fixture is a fixed snapshot because the source rerun CSVs can still be
appending. Use --refresh-snapshot explicitly to replace it with complete current
rows. This measures contract acceptance, NOT answer correctness or end-to-end
pipeline recovery. There are no ground-truth answers or benchmark-specific repairs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.util
import io
import json
import sys
import types
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "run_pipeline_v3"
DEFAULT_SNAPSHOT = HERE / "rerun_spec_snapshot.json"
DEFAULT_REPORT = HERE / "rerun_spec_replay.json"
DECLARATION_KEYS = {"merge_steps", "pre_steps", "final_measures", "final_steps", "final_output", "projection"}
GENERATED_KEYS = {
    "execution_steps", "compiled_output", "compiled_output_schema", "dataset_schemas",
    "execution_name_map", "aggregation_lineage", "contract_errors", "repair_stage",
}
csv.field_size_limit(2**28)


def json_value(value, default):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return default


def input_schemas(spec: dict, processing_specs: list) -> dict:
    """Discard compiler intermediates; retain only actual incoming branch schemas."""
    intermediate_ids = {
        str(step.get(key))
        for step in spec.get("execution_steps", []) if isinstance(step, dict)
        for key in ("id", "output") if step.get(key)
    }
    schemas = {
        name: fields for name, fields in spec.get("dataset_schemas", {}).items()
        if name not in intermediate_ids
    }
    if schemas:
        return schemas
    # The final builder can reject a plan before compilation. Node entries record
    # accepted processing outputs; unaccepted retry candidates must not supply them.
    for entry in processing_specs:
        if not isinstance(entry, dict) or not entry.get("node"):
            continue
        processing = entry.get("processing_spec", {})
        if processing.get("output_id") and not processing.get("contract_errors"):
            schemas[processing["output_id"]] = processing.get("compiled_output_schema", [])
    return schemas


def processed_samples(processing_specs: list, audit: list) -> dict:
    node_outputs = {
        entry["node"]: entry.get("processing_spec", {}).get("output_id")
        for entry in processing_specs if isinstance(entry, dict) and entry.get("node")
    }
    samples = {}
    for entry in audit:
        if not isinstance(entry, dict) or entry.get("operator") != "Processing_Spec":
            continue
        output_id = node_outputs.get(entry.get("node"))
        if output_id and isinstance(entry.get("output_sample"), list):
            samples[output_id] = entry["output_sample"]
    return samples


def capture_snapshot(path: Path) -> dict:
    sources = []
    records = []
    for source in sorted((HERE.parent / "pipelien_output").glob("v3_rerun_v1_*_debug.csv")):
        # A single byte read is the input snapshot; do not reopen a changing file.
        payload = source.read_bytes()
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        complete = [row for row in rows if row.get("Debug Operator Audit") is not None]
        sources.append({
            "path": str(source.relative_to(HERE.parent)), "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload), "complete_rows": len(complete), "incomplete_rows_excluded": len(rows) - len(complete),
        })
        for row in complete:
            spec = json_value(row.get("Debug Final Spec"), {})
            processing = json_value(row.get("Debug Processing Specs"), [])
            audit = json_value(row.get("Debug Operator Audit"), [])
            if not isinstance(spec, dict):
                spec = {}
            records.append({
                "source": source.name, "sample_id": row.get("Sample Row ID"),
                "question": row.get("Question"), "pipeline_status": row.get("New Status"),
                "recorded_final_spec": spec,
                "input_schemas": input_schemas(spec, processing if isinstance(processing, list) else []),
                "input_samples": processed_samples(processing, audit) if isinstance(processing, list) and isinstance(audit, list) else {},
            })
    if not sources:
        raise FileNotFoundError("No v3_rerun_v1_*_debug.csv files found")
    result = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources, "records": records,
    }
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def load_compiler():
    # Import only pure compiler modules; the real package __init__/common/clients
    # can configure credentials and service clients and are deliberately avoided.
    package = "_v3_recorded_spec_replay"
    module = types.ModuleType(package)
    module.__path__ = [str(SOURCE)]
    sys.modules[package] = module
    return importlib.import_module(package + ".spec_runtime").compile_spec


def load_sample_executor():
    # Reuse the test suite's client-free imports and the actual deterministic
    # operator implementations. No FakeClient is instantiated or called here.
    name = "_v3_recorded_replay_support"
    descriptor = importlib.util.spec_from_file_location(name, SOURCE / "tests" / "support.py")
    support = importlib.util.module_from_spec(descriptor)
    descriptor.loader.exec_module(support)
    return support.load("execution").execute_spec, support.registry()


def replay(snapshot: dict) -> dict:
    compile_spec = load_compiler()
    execute_spec, registry = load_sample_executor()
    records = []
    for saved in snapshot["records"]:
        recorded = saved["recorded_final_spec"]
        result = {key: saved[key] for key in ("source", "sample_id", "question", "pipeline_status")}
        result["recorded_contract_errors"] = recorded.get("contract_errors", [])
        if not recorded:
            result["replay_status"] = "no_recorded_final_spec"
        elif not DECLARATION_KEYS.intersection(recorded):
            result["replay_status"] = "no_recorded_declarations"
        elif not saved["input_schemas"]:
            result["replay_status"] = "no_recorded_input_schemas"
        else:
            # Recompile declarations, never replay stale compiled metadata.
            declarations = {key: value for key, value in recorded.items() if key not in GENERATED_KEYS}
            try:
                compiled = compile_spec(declarations, saved["input_schemas"])
                result["new_compile_errors"] = compiled.get("contract_errors", [])
                result["new_output_schema"] = compiled.get("compiled_output_schema", [])
                result["new_step_count"] = len(compiled.get("execution_steps", []))
                result["replay_status"] = "compile_error" if result["new_compile_errors"] else "compile_pass"
                samples = saved.get("input_samples", {})
                if result["replay_status"] == "compile_pass" and set(saved["input_schemas"]) <= samples.keys():
                    datasets = {name: samples[name] for name in saved["input_schemas"]}
                    output, execution_log = execute_spec(declarations, datasets, registry, dataset_schemas=saved["input_schemas"])
                    errors = [item for item in execution_log if item.get("error") or item.get("code")]
                    result["sample_execution_status"] = "runtime_error" if errors else "runtime_pass"
                    result["sample_execution_errors"] = errors
                    result["sample_input_rows"] = {name: len(rows) for name, rows in datasets.items()}
                    result["sample_output_rows"] = len(output)
                else:
                    result["sample_execution_status"] = "skipped_compile_error" if result["replay_status"] != "compile_pass" else "samples_not_available"
            except Exception as exc:
                result["replay_status"] = "compile_exception"
                result["new_compile_errors"] = [f"{type(exc).__name__}: {exc}"]
        records.append(result)
    attempted = [row for row in records if row["replay_status"] in {"compile_pass", "compile_error", "compile_exception"}]
    return {
        "replayed_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_captured_at_utc": snapshot["captured_at_utc"],
        "scope": "Offline compilation of logged final-plan declarations against logged input schemas; deterministic execution on recorded per-branch samples when available. No API calls, SPARQL queries, full datasets, final semantic validation, or answer grading.",
        "comparison_caveat": "Recorded errors include the former Final_Spec builder's inferred-requirement gates; new errors are compiler errors only. These counts do not establish pipeline success or accuracy.",
        "sources": snapshot["sources"],
        "compiler_source_sha256": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                                   for name in ("spec_runtime.py", "spec_contracts.py")},
        "snapshot_rows": len(records),
        "recorded_pipeline_status_counts": dict(Counter(row["pipeline_status"] for row in records)),
        "replay_status_counts": dict(Counter(row["replay_status"] for row in records)),
        "plans_recompiled": len(attempted),
        "recorded_final_contract_pass": sum(not row["recorded_contract_errors"] for row in attempted),
        "new_compile_pass": sum(row["replay_status"] == "compile_pass" for row in attempted),
        "sample_execution_status_counts": dict(Counter(row.get("sample_execution_status", "not_recompiled") for row in records)),
        "previously_accepted_compile_regressions": [row["sample_id"] for row in attempted
            if not row["recorded_contract_errors"] and row["replay_status"] != "compile_pass"],
        "records": records,
    }


def write_markdown(report: dict, path: Path) -> None:
    counts = report["replay_status_counts"]
    lines = [
        "# Offline replay of captured rerun plans", "",
        f"Snapshot: {report['snapshot_captured_at_utc']}. Replayed: {report['replayed_at_utc']}.", "",
        f"The fixed snapshot contains {report['snapshot_rows']} completed log rows. "
        f"{report['plans_recompiled']} rows retained a declarative final plan and its input schemas.", "",
        "| Check on those retained plans | Accepted |", "| --- | ---: |",
        f"| Recorded final contract (compiler plus old builder gates) | {report['recorded_final_contract_pass']} |",
        f"| Current offline compiler | {report['new_compile_pass']} |", "",
        f"Previously accepted plans that now fail compilation: {len(report['previously_accepted_compile_regressions'])}.", "",
        "This is contract acceptance and execution on recorded samples only. Samples contain "
        "at most five rows per branch, so joins may be empty and aggregate values are incomplete. "
        "This does not recheck retrieval or final semantic validation, grade answers, or predict "
        "the number of successful queries in a full rerun. Earlier-stage failures have no final plan to replay.", "",
        f"Replay dispositions: `{json.dumps(counts, sort_keys=True)}`.", "",
        f"Recorded-sample execution: `{json.dumps(report['sample_execution_status_counts'], sort_keys=True)}`.", "",
        "## Remaining compiler failures", "",
    ]
    failures = [row for row in report["records"] if row["replay_status"] in {"compile_error", "compile_exception"}]
    if not failures:
        lines.append("None among the retained plans.")
    for row in failures:
        lines.append(f"- `{row['sample_id']}`: " + "; ".join(row["new_compile_errors"]).replace("\n", " "))
    lines.extend(["", "## Remaining sample execution failures", ""])
    runtime_failures = [row for row in report["records"] if row.get("sample_execution_status") == "runtime_error"]
    if not runtime_failures:
        lines.append("None among the sampled plans that compiled.")
    for row in runtime_failures:
        lines.append(f"- `{row['sample_id']}`: " + "; ".join(str(error.get("error", error)) for error in row["sample_execution_errors"]).replace("\n", " "))
    lines.extend(["", "To repeat the same snapshot:", "", "```powershell",
                  "python experiment_week1/improvement3/diagnosis_20260912/replay_rerun_specs.py", "```", "",
                  "Use `--refresh-snapshot` only to deliberately capture newer source CSV rows. "
                  "The JSON report records source hashes, compiler hashes, schemas, and per-plan outcomes.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--refresh-snapshot", action="store_true")
    args = parser.parse_args()
    snapshot = capture_snapshot(args.snapshot) if args.refresh_snapshot or not args.snapshot.exists() else json.loads(args.snapshot.read_text(encoding="utf-8"))
    report = replay(snapshot)
    report["snapshot_sha256"] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, args.report.with_suffix(".md"))
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "sources", "compiler_source_sha256"}}, indent=2))


if __name__ == "__main__":
    main()
