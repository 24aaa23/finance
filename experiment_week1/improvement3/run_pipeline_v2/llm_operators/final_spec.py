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


def _compile_execution_names(spec: Dict[str, Any], branch_ids: list[str]) -> Dict[str, Any]:
    """Assign deterministic internal dataset names to a declarative Final_Spec.

    The model chooses operators, columns, grouping and join keys.  It must not need to
    coordinate arbitrary temporary names such as ``joined`` or ``calc_total``.  Legacy
    names are accepted as aliases during this conversion so a repair can still use a
    previous plan, but execution only sees compiler-owned names.
    """
    aliases = {branch_id: branch_id for branch_id in branch_ids}

    def remap(value: Any) -> Any:
        ids = _flatten_input_ids(value)
        mapped = [aliases.get(item, item) for item in ids]
        return mapped[0] if len(mapped) == 1 else mapped

    compiled = dict(spec)
    merge_steps = []
    for index, raw_step in enumerate(spec.get("merge_steps", []) or [], 1):
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        previous_names = [str(step.get(key) or "") for key in ("id", "output")]
        step["inputs"] = remap(step.get("inputs", step.get("input", [])))
        step.pop("input", None)
        internal = f"__final_merge_{index}"
        step["id"] = internal
        step["output"] = internal
        for name in previous_names:
            if name:
                aliases[name] = internal
        aliases[internal] = internal
        merge_steps.append(step)

    measures = []
    for raw_measure in spec.get("final_measures", []) or []:
        if not isinstance(raw_measure, dict):
            continue
        measure = dict(raw_measure)
        if "input" in measure:
            measure["input"] = remap(measure["input"])
        measures.append(measure)

    final_steps = []
    for index, raw_step in enumerate(spec.get("final_steps", []) or [], 1):
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        previous_names = [str(step.get(key) or "") for key in ("id", "output", "output_column")]
        if "inputs" in step:
            step["inputs"] = remap(step["inputs"])
        elif "input" in step:
            step["input"] = remap(step["input"])
        else:
            # Sequential post-aggregate operations naturally consume the last result.
            step["input"] = "previous"
        internal = f"__final_step_{index}"
        step["id"] = internal
        step["output"] = internal
        for name in previous_names:
            if name:
                aliases[name] = internal
        aliases[internal] = internal
        final_steps.append(step)

    compiled["merge_steps"] = merge_steps
    compiled["final_measures"] = measures
    compiled["final_steps"] = final_steps
    requested_output = str(spec.get("final_output") or "")
    compiled["final_output"] = aliases.get(requested_output, requested_output)
    compiled["execution_name_map"] = {
        name: internal for name, internal in aliases.items()
        if name != internal and name not in branch_ids
    }
    return compiled


def semantic_build_final_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """Plan deterministic merging and final aggregation after all branches are processed."""
    query = inputs.get("original_query", inputs.get("query", ""))
    branches = inputs.get("processed_datasets", [])
    decomposition = inputs.get("decomposition", {})
    answer_requirements = decomposition.get("answer_requirements", {}) if isinstance(decomposition, dict) else {}
    spec_feedback = inputs.get("spec_feedback", "")
    previous_final_spec = inputs.get("previous_final_spec", {})
    previous_final_execution = inputs.get("previous_final_execution", [])
    prompt = f"""
You are the Final_Spec operator. Combine already processed branch datasets into the final answer.

Original question: {query}
Selected decomposition: {json.dumps(decomposition, indent=2)}
Required answer shape from Decompose: {json.dumps(answer_requirements, indent=2)}
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
Retain every required raw display/entity field that is available in processed inputs. Use
the declared final grouping fields and metric outputs. Preserve declared null groups.
Do not provide `id`, `output`, or `final_output`: the deterministic compiler creates those
internal execution names. In a final step, use a processed branch ID or `previous` as input;
never invent a temporary dataset name. When a step follows another final step, use `previous`.
For exactly one processed branch, do not create a merge step: aggregate or compute directly
from that branch and return the terminal final-step output.

Repair feedback from a previous invalid plan, if any: {spec_feedback}
Previous Final_Spec, if this is a repair: {json.dumps(previous_final_spec, indent=2)}
Previous Final Execution, if this is a repair: {json.dumps(previous_final_execution, indent=2)}

{{
  "merge_steps": [
    {{"operator": "Integrate", "inputs": ["branch_a", "branch_b"],
      "join_key": ["entity_id"], "join_type": "inner"}}
  ],
  "final_group_by": ["final grouping columns"],
  "final_measures": [
    {{"output_column": "final_metric", "operation": "count|sum|avg|min|max",
      "input_column": "source_metric_or_record_id", "input": "previous_or_processed_branch_id",
      "group_by": ["optional grouping columns"]}}
  ],
  "final_steps": [
    {{"operator": "Filter_Aggregate", "input": "previous",
      "operation": "sum|avg|count|min|max|filter", "group_by": ["group_dimension"],
      "target_column": "metric", "output_column": "final_metric", "filters": []}}
  ],
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
    # Convert only temporary execution identifiers to compiler-owned names.  Columns,
    # joins, operators, measures, expressions and ranking choices remain LLM-planned.
    spec = _compile_execution_names(spec, ids)
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
    merge_output_ids = [str(step.get("output") or step.get("id") or "") for step in spec["merge_steps"]]
    # Pre-aggregate transformations are a separate deterministic stage.  Register
    # their output lineage before checking measures, so Date_Extract(date -> month)
    # may legitimately be a final grouping key.
    pre_measure_steps = [
        step for step in spec["final_steps"]
        if step.get("operator") in {"Date_Extract", "Bucket"}
    ]
    for index, step in enumerate(pre_measure_steps, 1):
        contract_errors.extend(validate_step_contract(step, produced_fields, available_datasets | {"previous"}))
        output_column = step.get("output_column")
        if output_column:
            produced_fields.add(str(output_column))
        output_id = str(step.get("output") or step.get("id") or f"pre_final_step_{index}")
        fields_by_dataset[output_id] = set(produced_fields)
        available_datasets.add(output_id)
    # ``previous`` is the declarative reference to the final merge (or lone branch),
    # or to the final pre-aggregate transformation when one exists.
    pre_output_ids = [str(step.get("output") or step.get("id") or "") for step in pre_measure_steps]
    default_measure_input = (
        pre_output_ids[-1]
        if pre_output_ids else (merge_output_ids[-1] if merge_output_ids else next(iter(fields_by_dataset), ""))
    )
    for measure in spec["final_measures"]:
        measure_inputs = flatten_identifiers(measure.get("input"))
        source_id = (
            default_measure_input
            if measure_inputs == ["previous"]
            else (measure_inputs[0] if len(measure_inputs) == 1 else default_measure_input)
        )
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
    measure_groupings = {
        tuple(flatten_identifiers(measure.get("group_by") or spec.get("final_group_by")))
        for measure in spec["final_measures"]
        if isinstance(measure, dict)
    }
    if len(spec["final_measures"]) > 1 and spec["final_steps"] and len(measure_groupings) > 1:
        contract_errors.append(
            "Final_Spec derived/order steps require multiple final measures to share one final group_by."
        )
    # Final measure tables are combined on their declared grouping keys; their output fields
    # become available to derived calculations and projection.
    final_fields = set(produced_fields)
    for index, step in enumerate(spec["final_steps"], 1):
        if step.get("operator") in {"Date_Extract", "Bucket"}:
            continue
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
    required_projection = [str(field) for field in answer_requirements.get("required_projection", []) if field]
    # A field that never reached any processed branch is a Query_Spec issue.  Only
    # demand Final_Spec projection of fields that are already available here.
    missing_required_projection = [
        field for field in required_projection
        if field in produced_fields and field not in projection
    ]
    required_groups = [str(field) for field in answer_requirements.get("group_by", []) if field]
    declared_groups = set(flatten_identifiers(spec.get("final_group_by")))
    for measure in spec["final_measures"]:
        declared_groups.update(flatten_identifiers(measure.get("group_by")))
    for step in spec["final_steps"]:
        declared_groups.update(flatten_identifiers(step.get("group_by")))
    missing_required_groups = [field for field in required_groups if field not in declared_groups]
    required_metric_outputs = [
        str(metric.get("output_column"))
        for metric in answer_requirements.get("metrics", [])
        if isinstance(metric, dict) and metric.get("output_column")
    ]
    missing_metric_outputs = [field for field in required_metric_outputs if field not in projection]
    if len(ids) > 1 and missing_branches:
        contract_errors.append(f"Final_Spec does not reference processed branches: {missing_branches}")
    if missing_projection:
        contract_errors.append(
            "Final_Spec projection fields have no source or producing step: " + ", ".join(missing_projection)
        )
    if missing_required_projection:
        contract_errors.append(
            "Final_Spec omits required available projection fields: " + ", ".join(missing_required_projection)
        )
    if missing_required_groups:
        contract_errors.append(
            "Final_Spec omits required final grouping fields: " + ", ".join(missing_required_groups)
        )
    if missing_metric_outputs:
        contract_errors.append(
            "Final_Spec omits required metric output fields: " + ", ".join(missing_metric_outputs)
        )
    if answer_requirements.get("preserve_null_groups") and not spec.get("preserve_null_groups", False):
        contract_errors.append("Final_Spec must preserve declared null groups.")
    spec["contract_errors"] = contract_errors
    return {"final_spec": spec}
