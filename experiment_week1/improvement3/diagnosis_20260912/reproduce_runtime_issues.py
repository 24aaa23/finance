"""Offline, synthetic probes of the current v3 runtime; no pipeline/API imports.

Extract function ASTs to avoid common.py configuration and client side effects.
These probes document bugs, not benchmark accuracy or hypothetical fixes.
"""
import ast
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "run_pipeline_v3"


def load_functions(relative_path, namespace=None):
    path = SOURCE / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    env = {
        "Any": Any, "Dict": Dict, "pd": pd, "re": re, "json": json,
        "LLMClient": Any, "LOCAL_MODEL": "offline-probe",
    }
    env.update(namespace or {})
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), env)
    return env


def main():
    import copy
    contracts = load_functions("spec_contracts.py", {
        "deepcopy": copy.deepcopy,
        "LIST_FIELDS": {"inputs", "group_by", "join_key", "projection", "entity_grain",
                        "fields", "optional_fields", "entity_key", "output_schema"},
    })
    math_env = load_functions("non_llm_operators/math_compute.py")
    order_env = load_functions("llm_operators/order_by.py")
    aggregate_env = load_functions("llm_operators/filter_aggregate.py")
    aggregate = aggregate_env["semantic_filter_aggregate"]
    math_op = math_env["pre_programmed_math_compute"]
    observations = []

    def record(name, actual, expected, diagnosis, evidence=None):
        observations.append({"probe": name, "actual": actual, "expected": expected,
                             "issue_reproduced": actual != expected, "diagnosis": diagnosis,
                             "evidence": evidence})

    result = math_op({"strict_spec": True,
                      "data": [{"combined_amount": 10, "rebalance_amount": 20}],
                      "expression": "combined_amount + rebalance_amount",
                      "output_column": "total_combined"})
    record("Logged TT-033 Math_Compute shape", result.get("data"),
           [{"combined_amount": 10, "rebalance_amount": 20, "total_combined": 30}],
           "Math_Compute never reads expression; returns missing-column error.", result)

    try:
        ordered = order_env["semantic_order_by"]({
            "data": [{"total": 1}, {"total": 3}], "strict_spec": True,
            "order_by": [{"column": "total", "direction": "desc"}], "limit": 1,
        }, None)
    except Exception as exc:
        ordered = {"exception": type(exc).__name__, "message": str(exc)}
    record("List-shaped Order_By input", ordered.get("data", ordered), [{"total": 3}],
           "Order_By treats a list as a column key and raises TypeError.", ordered)

    tree = ast.parse((SOURCE / "executor.py").read_text(encoding="utf-8-sig"))
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == "execute_spec_steps")
    function.body = [n for n in function.body if not isinstance(n, ast.ImportFrom)]
    env = {"Any": Any, "Dict": Dict, "normalize_spec": contracts["normalize_spec"],
           "flatten_identifiers": contracts["flatten_identifiers"],
           "initial_query": "Synthetic sum of two columns",
           "self": SimpleNamespace(registry={
               "Filter_Aggregate": lambda inputs: aggregate(inputs, None),
               "Math_Compute": math_op,
           })}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE / "executor.py"), "exec"), env)
    execute = env["execute_spec_steps"]
    spec = {"final_measures": [
        {"output_column": "a_sum", "operation": "sum", "input_column": "a", "input": "raw", "group_by": []},
        {"output_column": "b_sum", "operation": "sum", "input_column": "b", "input": "raw", "group_by": []},
    ]}
    data, log = execute(spec, {"raw": [{"a": 10, "b": 1}, {"a": 20, "b": 2}]})
    record("Combine_Scalars consumes stale inputs", data, [{"a_sum": 30, "b_sum": 3}],
           "Combine_Scalars reads selected before resolving its own inputs; sees two raw rows instead of scalar measures.", log)

    spec = {"steps": [{"id": "bad_math", "operator": "Math_Compute", "input": "raw",
                       "expression": "a + b", "output_column": "total"}], "output": "bad_math"}
    data, log = execute(spec, {"raw": [{"a": 10, "b": 20}]})
    error_propagated = any(item.get("code") or item.get("error") for item in log)
    record("Spec executor propagates operator errors", error_propagated, True,
           "Math operator returns error, but executor records only id/operator/row_count; empty data masks failure.")

    count = aggregate({"strict_spec": True, "strict_aggregation": True,
                       "data": [{"amount": None}, {"amount": 5}],
                       "operation": "count", "target_column": "amount", "output_column": "n"}, None)
    record("COUNT(column) excludes nulls", count["data"], [{"n": 1}],
           "Current count branch always counts rows, ignoring target_column; SQL COUNT(column) needs different semantics.")

    payload = {
        "merge_steps": [], "final_group_by": ["investorId"],
        "final_measures": [{"output_column": "total_amount", "operation": "sum",
                            "input_column": "amount", "input": "q1_processed"}],
        "final_steps": [{"operator": "Filter_Aggregate", "input": "previous",
                         "operation": "filter", "filters": [
                             {"field": "total_amount", "operator": ">", "value": 1000}]}],
        "projection": ["investorId", "total_amount"],
    }
    final_env = load_functions("llm_operators/final_spec.py", {
        "flatten_identifiers": contracts["flatten_identifiers"],
        "normalize_spec": contracts["normalize_spec"],
        "validate_step_contract": contracts["validate_step_contract"],
        "api_logger": SimpleNamespace(log_call=lambda *args: None),
        "build_llm_messages": lambda *args: [],
        "parse_llm_json": lambda content, *args: json.loads(content),
    })
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(payload)))]))))
    final_spec = final_env["semantic_build_final_spec"]({
        "original_query": "Investors whose total amount exceeds 1000",
        "processed_datasets": [{"id": "q1_processed", "fields": ["investorId", "amount"]}],
    }, fake_client)["final_spec"]
    record("Final_Spec preserves post-aggregate filter", len(final_spec["final_steps"]), 1,
           "Canonicalization deletes the required filter whenever final_measures is present.", final_spec)

    files = ["executor.py", "spec_contracts.py", "non_llm_operators/math_compute.py",
             "llm_operators/order_by.py", "llm_operators/filter_aggregate.py", "llm_operators/final_spec.py"]
    output = {"scope": "Current source, synthetic offline probes; no production changes or API calls",
              "source_sha256": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in files},
              "observations": observations}
    (HERE / "runtime_probe_results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
