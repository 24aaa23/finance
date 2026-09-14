"""Replay only saved V4 comparative plans locally; never a correctness grade.

Uses saved samples, which may have no overlapping entities across branches.
No model calls or database writes. Reference answers never enter inference.
"""
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

from audit_v4 import rows

HERE = Path(__file__).resolve().parent
V4 = HERE.parent / "run_pipeline_v4"


def main():
    location = V4 / "docs/completed_run_audit/replay_final_plans.py"
    spec = importlib.util.spec_from_file_location("comparative_replay", location)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    support = replay.support_for("run_pipeline_v4")
    records, sources = [], []
    for path in sorted((HERE.parent / "pipelien_output").glob("v4_simple*_debug.csv")):
        sources.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in rows(path):
            if not row["Sample Row ID"].startswith("wealth_management_multi_step_comparative_"):
                continue
            record = {"id": row["Sample Row ID"].split(":")[-1], "source": path.name,
                      "saved_status": row["New Status"]}
            records.append(record)
            saved = replay.parse(row.get("Debug Final Spec"), {})
            if not isinstance(saved, dict) or not replay.DECLARATIONS.intersection(saved):
                record["replay"] = {"status": "no_saved_plan"}
                continue
            schemas = {key: value for key, value in saved.get("dataset_schemas", {}).items()
                       if not key.startswith("__spec_step_")}
            if not schemas:
                record["replay"] = {"status": "no_saved_schemas"}
                continue
            samples = {}
            for entry in replay.parse(row.get("Debug Operator Audit"), []):
                if entry.get("operator") == "Processing_Spec" and entry.get("subquestion_id"):
                    samples[str(entry["subquestion_id"]) + "_processed"] = entry.get("output_sample", [])
            plan = {key: value for key, value in saved.items() if key in replay.DECLARATIONS}
            record["replay"] = replay.run_plan(support, plan, schemas, samples)
    report = {
        "scope": "Current compiler and executor, historical V4 comparative plans, saved samples only. No model run or correctness grading. Empty sample outputs do not establish correct joins.",
        "sources": sources,
        "source_hashes": {str(path.relative_to(V4)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(V4.rglob("*.py")) if "tests" not in path.parts},
        "cases": len(records),
        "saved_statuses": dict(Counter(row["saved_status"] for row in records)),
        "replay_statuses": dict(Counter(row["replay"]["status"] for row in records)),
        "records": records,
    }
    (HERE / "comparative_plan_replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("scope", "cases", "saved_statuses", "replay_statuses")}, indent=2))


if __name__ == "__main__":
    main()
