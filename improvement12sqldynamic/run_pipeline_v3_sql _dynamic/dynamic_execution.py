"""Execute selected upfront calculation nodes with the existing strict engine."""
from copy import deepcopy

from .execution import execute_spec, execution_errors, row_schema
from .spec_runtime import compile_spec
from .query_understanding import final_contract_errors


def execute_calculation(step, cache, registry, query):
    parents = step["inputs"]
    datasets = {name: cache[name].get("data", []) for name in parents}
    schemas = {name: row_schema(datasets[name], cache[name].get("data_schema", [])) for name in parents}
    # A single-node spec still receives the existing compiler's exact field,
    # operator, join, null, multiplicity and output-schema checks.
    spec = compile_spec({"final_steps": [deepcopy(step)], "final_output": step["id"]}, schemas)
    if spec["contract_errors"]:
        log = [{"stage": "Spec_Execution", "step": step["id"], "node": step["id"],
                "operator": step["operator"], "inputs": parents, "input_schemas": schemas,
                "code": "SPEC_CONTRACT_ERROR", "error": str(error)} for error in spec["contract_errors"]]
        return {"data": [], "dynamic_execution": log}, spec["contract_errors"]
    data, log = execute_spec(spec, datasets, registry, query, schemas)
    errors = [str(item.get("error") or item) for item in execution_errors(log)]
    for item in log:
        item["node"] = step["id"]
    return {"data": data, "data_schema": spec["compiled_output_schema"],
            "dynamic_execution": log}, errors


def branch_context(plan, cache, decomposition):
    """Describe the original processed sources for final output and repair."""
    schemas, profiles, contexts, datasets = {}, [], [], {}
    for name in plan["branch_fields"]:
        predecessor = cache[name]
        rows = predecessor.get("data", [])
        fields = row_schema(rows, predecessor.get("data_schema", []))
        schemas[name], datasets[name] = fields, rows
        context = predecessor.get("processing_context", {})
        contexts.append({"id": name, **context})
        profiles.append({"id": name, "fields": fields,
            "branch_id": context.get("subquestion_id"),
            "question": context.get("subquestion", {}).get("question", ""),
            "retrieval_specs": context.get("query_spec", {}).get("retrieval_specs", []),
            "executed_sparql": context.get("executed_sparql", ""),
            "source_requirement_ids": context.get("subquestion", {}).get("requirement_ids", []),
            "entity_grain": predecessor.get("processing_spec", {}).get("entity_grain", []),
            "aggregation_policy": "preserve_rows"})
    return {"processed_datasets": profiles, "branch_datasets": datasets, "branch_schemas": schemas,
            "processing_contexts": contexts, "answer_requirements": decomposition.get("answer_requirements", {})}


def canonical_execution_log(plan, execution_log):
    """Map single-node runtime IDs back to the full selected spec's step IDs."""
    mapping = {"__dynamic_calc_" + str(index): step["output"]
               for index, step in enumerate(plan["compiled_spec"]["execution_steps"], 1)}
    log = deepcopy(execution_log)
    for item in log:
        if item.get("node") in mapping:
            item["step" if item.get("error") or item.get("code") else "id"] = mapping[item["node"]]
        item["inputs"] = [mapping.get(name, name) for name in item.get("inputs", [])]
        if "input_schemas" in item:
            item["input_schemas"] = {mapping.get(name, name): fields for name, fields in item["input_schemas"].items()}
    return log


def finish_output(plan, cache, decomposition, registry, query, execution_log):
    """Check the full selected plan again; finalize output without an LLM call."""
    context = branch_context(plan, cache, decomposition)
    spec = compile_spec(plan["spec"], context["branch_schemas"])
    errors = list(spec["contract_errors"])
    if plan.get("contract_checks", True):
        errors.extend(final_contract_errors(spec, decomposition.get("answer_requirements", {}).get("query_understanding", {})))
    if errors:
        return {**context, "final_spec": spec, "final_execution": deepcopy(execution_log)}, errors
    final_name = plan["final_input"]
    final = cache[final_name]
    final_schema = row_schema(final.get("data", []), final.get("data_schema", []))
    # Calculations already ran as DAG nodes. This zero-step spec only applies
    # projection/rounding; distinctness was materialized in the upfront graph.
    output_spec = {"final_steps": [], "final_output": final_name,
                   "projection": plan["spec"]["projection"], "rounding": plan["spec"].get("rounding")}
    data, log = execute_spec(output_spec, {final_name: final.get("data", [])}, registry, query,
                             {final_name: final_schema})
    errors = [str(item.get("error") or item) for item in execution_errors(log)]
    return {"data": data, "data_schema": spec["compiled_output_schema"], "final_spec": spec,
        "final_execution": deepcopy(execution_log) + log, "execution_errors": errors, **context}, errors
