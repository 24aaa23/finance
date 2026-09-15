"""Recompile saved failures with the current normalizer; no model or graph calls."""
import csv
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "tests"))
from support import load

csv.field_size_limit(100_000_000)


def main():
    source = PACKAGE.parent / "pipelien_output/v8_multistep_contract_non_success_part2_68_debug.csv"
    normalize = load("llm_operators.final_spec").normalize_final_plan
    compile_spec = load("spec_runtime").compile_spec
    results = []
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Failure Stage"] != "Final_Spec":
                continue
            spec = json.loads(row["Debug Final Spec"])
            schemas = {k: v for k, v in spec["dataset_schemas"].items() if not k.startswith("__spec_")}
            classes = {s["id"]: s.get("source_class") for s in json.loads(row["Debug Subquestions"])}
            branches = [{"id": name, "fields": fields, "branch_id": name.removesuffix("_processed"),
                         "retrieval_specs": [{"class": classes.get(name.removesuffix("_processed"))}]}
                        for name, fields in schemas.items()]
            revised = compile_spec(normalize(spec, branches), schemas)
            results.append({"id": row["Sample Row ID"].split(":")[-1],
                            "before": spec["contract_errors"], "after": revised["contract_errors"]})
    (PACKAGE / "docs/v8_repair_replay.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"saved_final_spec_failures": len(results),
                      "now_compile": [r["id"] for r in results if not r["after"]],
                      "still_need_plan_or_contract_repair": sum(bool(r["after"]) for r in results),
                      "execution_or_grading_performed": False}, indent=2))


if __name__ == "__main__":
    main()
