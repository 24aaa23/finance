"""Cross-branch final specification operator."""

from ..common import Any, Dict, LOCAL_MODEL, api_logger, json
from ..clients import build_llm_messages
from ..utils import parse_llm_json
from ..spec_contracts import flatten_identifiers, normalize_spec, validate_step_contract


def _flatten_input_ids(value: Any) -> list[str]:
    """Normalize scalar or arbitrarily nested LLM input references."""
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_input_ids(item))
        return flattened
    return []


def semantic_build_final_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """Plan deterministic merging and final aggregation after all branches are processed."""
    query = inputs.get("original_query", inputs.get("query", ""))
    branches = inputs.get("processed_datasets", [])
    decomposition = inputs.get("decomposition", {})
    spec_feedback = inputs.get("spec_feedback", "")
    previous_final_spec = inputs.get("previous_final_spec", {})
    previous_final_execution = inputs.get("previous_final_execution", [])
    prompt = f"""
You are the Final_Spec operator. Combine already processed branch datasets into the final answer.

Original question: {query}
Selected decomposition: {json.dumps(decomposition, indent=2)}
Available processed datasets (schemas/small samples only): {json.dumps(branches, indent=2)}

Return JSON only. Never write SPARQL and never request raw source fields. Use only
Integrate, Set_Intersect, Set_Union, Set_Difference, Filter_Aggregate, Math_Compute, Date_Extract, Bucket, or
Order_By. Merge using explicit key(s), including composite keys where required. Do not join
raw fact tables: inputs are already branch-local processed results. For comparative queries,
declare the final group_by and operation for every metric. Preserve null groups unless the
question explicitly excludes them. Apply ranking/limit only after final aggregation.
Every available processed dataset must be referenced by a merge-step input when there is
more than one branch, or directly by a declared final measure/step. Do not return a partial
one-branch answer. Treat each selected decomposition subquestion as a required condition.
When final_steps exist, final_output must name their terminal output (never a raw branch ID).
For exactly one processed branch, do not create a merge step: aggregate or compute directly
from that branch and return the terminal final-step output.

Repair feedback from a previous invalid plan, if any: {spec_feedback}
Previous Final_Spec, if this is a repair: {json.dumps(previous_final_spec, indent=2)}
Previous Final Execution, if this is a repair: {json.dumps(previous_final_execution, indent=2)}

{{
  "merge_steps": [
    {{"id": "merge_1", "operator": "Integrate", "inputs": ["branch_a", "branch_b"],
      "join_key": ["entity_id"], "join_type": "inner", "output": "merged"}}
  ],
  "final_group_by": ["final grouping columns"],
  "final_measures": [
    {{"output_column": "final_metric", "operation": "count|sum|avg|min|max",
      "input_column": "source_metric_or_record_id", "input": "merged_or_processed_branch",
      "group_by": ["optional grouping columns"]}}
  ],
  "final_steps": [
    {{"id": "final_1", "operator": "Filter_Aggregate", "input": "merged",
      "operation": "sum|avg|count|min|max|filter", "group_by": ["group_dimension"],
      "target_column": "metric", "output_column": "final_metric", "filters": []}}
  ],
  "final_output": "final_1_or_branch_id",
  "preserve_null_groups": true,
  "rounding": 2,
  "projection": ["final columns"]
}}
"""
    api_logger.log_call(query, "Final_Spec")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("final_spec", prompt),
        **({} if model.lower().startswith("gpt-5") else {"temperature": 0.0}),
    )
    ids = [str(branch.get("id")) for branch in branches if isinstance(branch, dict) and branch.get("id")]
    merge_strategy = decomposition.get("merge_strategy", {}) if isinstance(decomposition, dict) else {}
    default_merge_steps = []
    if len(ids) > 1:
        default_merge_steps = [{
            "id": "merged_branches",
            "operator": merge_strategy.get("operator") or "Integrate",
            "inputs": ids,
            "join_key": merge_strategy.get("join_key"),
            "join_type": merge_strategy.get("join_type") or merge_strategy.get("how") or "inner",
            "output": "merged_branches",
        }]
    default = {"merge_steps": default_merge_steps, "final_group_by": [], "final_measures": [], "final_steps": [], "final_output": "merged_branches" if default_merge_steps else (ids[0] if ids else ""), "preserve_null_groups": True, "rounding": 2, "projection": []}
    spec = parse_llm_json(response.choices[0].message.content, default, "Final_Spec")
    if not isinstance(spec, dict):
        spec = default
    spec.setdefault("merge_steps", default_merge_steps)
    spec.setdefault("final_group_by", [])
    spec.setdefault("final_measures", [])
    spec.setdefault("final_steps", [])
    spec.setdefault("final_output", default["final_output"])
    spec.setdefault("preserve_null_groups", True)
    spec.setdefault("rounding", 2)
    spec.setdefault("projection", [])
    spec = normalize_spec(spec)
    allowed = {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Filter_Aggregate", "Math_Compute", "Date_Extract", "Bucket", "Order_By"}
    spec["merge_steps"] = [step for step in spec["merge_steps"] if isinstance(step, dict) and step.get("operator") in allowed]
    spec["final_steps"] = [step for step in spec["final_steps"] if isinstance(step, dict) and step.get("operator") in allowed]
    spec["final_measures"] = [
        measure for measure in spec["final_measures"]
        if isinstance(measure, dict)
        and measure.get("output_column")
        and str(measure.get("operation", "")).lower() in {"count", "sum", "avg", "average", "min", "max"}
    ]
    # Aggregates have one canonical representation. Keeping another aggregate in
    # final_steps creates two plans for the same metric and lets execution reorder them.
    if spec["final_measures"]:
        spec["final_steps"] = [
            step for step in spec["final_steps"]
            if step.get("operator") != "Filter_Aggregate"
        ]
    # A single branch has nothing to merge. An invented self-merge can multiply raw rows and
    # make a correct aggregate step unreachable.
    if len(ids) <= 1:
        spec["merge_steps"] = []
    if len(ids) > 1 and not spec["merge_steps"]:
        spec["merge_steps"] = default_merge_steps
        spec["final_output"] = "merged_branches"
    produced = [str(step.get("output") or step.get("id") or "") for step in spec["final_steps"]]
    consumed = {
        str(item)
        for step in spec["final_steps"]
        for item in _flatten_input_ids(step.get("inputs", step.get("input")))
        if item not in {"", "raw", "previous"}
    }
    terminals = [item for item in produced if item and item not in consumed]
    requested_final_output = str(spec.get("final_output") or "")
    # Final computations must win over a default/raw branch output. With independent terminal
    # measures, leave final_output blank so the deterministic interpreter combines them.
    if len(terminals) == 1 and requested_final_output not in terminals:
        spec["final_output"] = terminals[0]
    elif len(terminals) > 1 and (requested_final_output in terminals or requested_final_output in ids or not requested_final_output):
        spec["final_output"] = ""
        spec["auto_combine_terminal_measures"] = True
    referenced = {item for item in _flatten_input_ids(spec.get("inputs")) if item}
    for step in spec["merge_steps"]:
        raw_inputs = _flatten_input_ids(step.get("inputs", step.get("input")))
        referenced.update(item for item in raw_inputs if item and item != "previous")
    for measure in spec["final_measures"]:
        referenced.update(item for item in _flatten_input_ids(measure.get("input")) if item and item != "previous")
    for step in spec["final_steps"]:
        referenced.update(item for item in _flatten_input_ids(step.get("inputs", step.get("input"))) if item and item != "previous")
    missing_branches = [branch_id for branch_id in ids if branch_id not in referenced]
    fields_by_dataset = {
        str(branch.get("id")): set(flatten_identifiers(branch.get("fields", [])))
        for branch in branches if isinstance(branch, dict) and branch.get("id")
    }
    available_datasets = set(fields_by_dataset)
    produced_fields = set().union(*fields_by_dataset.values()) if fields_by_dataset else set()
    contract_errors = []
    # Merge outputs have lineage from their declared input datasets. A branch identity is
    # retained for every measure so a same-named field in another branch cannot satisfy it.
    for index, step in enumerate(spec["merge_steps"], 1):
        contract_errors.extend(validate_step_contract(step, produced_fields, available_datasets))
        merge_inputs = flatten_identifiers(step.get("inputs", step.get("input")))
        merge_fields = set().union(*(fields_by_dataset.get(item, set()) for item in merge_inputs))
        output_id = str(step.get("output") or step.get("id") or f"merge_{index}")
        fields_by_dataset[output_id] = merge_fields
        available_datasets.add(output_id)
    default_measure_input = next(iter(fields_by_dataset), "")
    for measure in spec["final_measures"]:
        measure_inputs = flatten_identifiers(measure.get("input"))
        source_id = measure_inputs[0] if len(measure_inputs) == 1 else default_measure_input
        if len(measure_inputs) > 1:
            contract_errors.append("Final_Spec measure must declare exactly one input dataset.")
        source_column = str(measure.get("input_column") or measure.get("target_column") or "")
        if source_id not in fields_by_dataset:
            contract_errors.append(f"Final_Spec measure input dataset does not exist: {source_id}")
            continue
        if not source_column or source_column not in fields_by_dataset[source_id]:
            contract_errors.append(f"Final_Spec measure source field does not exist on {source_id}: {source_column}")
        for field in flatten_identifiers(measure.get("group_by") or spec.get("final_group_by")):
            if field not in fields_by_dataset[source_id]:
                contract_errors.append(f"Final_Spec measure group field does not exist on {source_id}: {field}")
        output_column = str(measure.get("output_column"))
        if output_column in produced_fields:
            contract_errors.append(f"Final_Spec measure output overwrites an existing field: {output_column}")
        produced_fields.add(output_column)
    # Final measure tables are combined on their declared grouping keys; their output fields
    # become available to derived calculations and projection.
    final_fields = set(produced_fields)
    for index, step in enumerate(spec["final_steps"], 1):
        contract_errors.extend(validate_step_contract(step, final_fields, available_datasets | {"previous"}))
        output_column = step.get("output_column")
        if output_column:
            final_fields.add(str(output_column))
        # Execution exposes a step under ``output`` or ``id``. Register the same dataset
        # lineage here so a following declared step can consume it without a false error.
        output_id = str(step.get("output") or step.get("id") or f"final_step_{index}")
        fields_by_dataset[output_id] = set(final_fields)
        available_datasets.add(output_id)
    produced_fields = final_fields
    projection = [str(field) for field in spec.get("projection", []) if field]
    missing_projection = [field for field in projection if field not in produced_fields]
    if len(ids) > 1 and missing_branches:
        contract_errors.append(f"Final_Spec does not reference processed branches: {missing_branches}")
    if missing_projection:
        contract_errors.append(
            "Final_Spec projection fields have no source or producing step: " + ", ".join(missing_projection)
        )
    spec["contract_errors"] = contract_errors
    return {"final_spec": spec}
