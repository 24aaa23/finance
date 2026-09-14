"""Branch-local processing specification operator."""

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


def _dataset_profile(data: Any) -> Dict[str, Any]:
    rows = data if isinstance(data, list) else []
    fields = []
    for row in rows[:20]:
        if isinstance(row, dict):
            for field in row:
                if field not in fields:
                    fields.append(field)
    return {"row_count": len(rows), "fields": fields, "sample": rows[:3]}


def semantic_build_processing_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """Plan deterministic transformations for one scanned decomposition branch."""
    query = inputs.get("query", "")
    original_query = inputs.get("original_query", query)
    subquestion = inputs.get("subquestion", {})
    query_spec = inputs.get("query_spec", {})
    profile = _dataset_profile(inputs.get("data", []))
    output_id = str(inputs.get("subquestion_id") or query_spec.get("id") or "branch") + "_processed"

    spec_feedback = inputs.get("spec_feedback", "")
    prompt = f"""
You are the Processing_Spec operator. Plan transformations for ONE scanned dataset only.

Original question: {original_query}
Active decomposition: {json.dumps(subquestion, indent=2)}
Raw Query_Spec: {json.dumps(query_spec, indent=2)}
Scanned dataset profile: {json.dumps(profile, indent=2)}

Return JSON only. Do not write SPARQL. Do not merge another dataset. Do not make a final
cross-branch answer. Use only Filter_Aggregate, Math_Compute, or Date_Extract. Date_Extract
requires input_column, part (year|month|day), and output_column. Every step must read the
previous step or "raw". Explicitly state entity_grain. For a fact table, aggregate to its
natural entity grain before it can later be merged. Use empty steps only when raw rows are
already the correct branch output.

Repair feedback from a previous invalid plan, if any: {spec_feedback}

{{
  "input": "raw",
  "entity_grain": ["entity_id"],
  "steps": [
    {{"id": "step_1", "operator": "Filter_Aggregate", "input": "raw",
      "operation": "sum|avg|count|min|max|filter", "group_by": ["entity_id"],
      "target_column": "numeric_column", "output_column": "descriptive_output",
      "filters": []}}
  ],
  "output": "step_1_or_raw",
  "output_id": "{output_id}",
  "output_schema": ["entity_id", "descriptive_output"]
}}
"""
    api_logger.log_call(query, "Processing_Spec")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("processing_spec", prompt),
        **({} if model.lower().startswith("gpt-5") else {"temperature": 0.0}),
    )
    default = {"input": "raw", "entity_grain": [], "steps": [], "output": "", "output_id": output_id, "output_schema": profile["fields"]}
    spec = parse_llm_json(response.choices[0].message.content, default, "Processing_Spec")
    if not isinstance(spec, dict):
        spec = default
    spec.setdefault("input", "raw")
    spec.setdefault("entity_grain", [])
    spec.setdefault("steps", [])
    # An empty output asks the deterministic interpreter to merge independent
    # terminal measures on entity_grain (for example SUM and AVG from raw rows).
    spec.setdefault("output", "")
    spec.setdefault("output_id", output_id)
    spec.setdefault("output_schema", profile["fields"])
    spec = normalize_spec(spec)
    spec["steps"] = [step for step in spec["steps"] if isinstance(step, dict) and step.get("operator") in {"Filter_Aggregate", "Math_Compute", "Date_Extract"}]
    produced = [str(step.get("output") or step.get("id") or "") for step in spec["steps"]]
    consumed = {
        str(item)
        for step in spec["steps"]
        for item in _flatten_input_ids(step.get("inputs", step.get("input")))
        if item not in {"", "raw", "previous"}
    }
    terminals = [item for item in produced if item and item not in consumed]
    requested_output = str(spec.get("output") or "")
    if len(terminals) == 1 and requested_output not in terminals:
        spec["output"] = terminals[0]
    elif len(terminals) > 1 and (requested_output in terminals or requested_output == "raw" or not requested_output):
        spec["output"] = ""
        spec["auto_combine_terminal_measures"] = True
    available_fields = set(profile["fields"])
    available_datasets = {"raw"}
    contract_errors = []
    for index, step in enumerate(spec["steps"], 1):
        contract_errors.extend(validate_step_contract(step, available_fields, available_datasets))
        output_id = str(step.get("output") or step.get("id") or f"step_{index}")
        output_column = step.get("output_column")
        if output_column:
            output_column = str(output_column)
            if output_column in available_fields and output_column not in flatten_identifiers(step.get("group_by")):
                contract_errors.append(f"processing output_column overwrites an existing field: {output_column}")
            available_fields.add(output_column)
        available_datasets.add(output_id)
    for field in flatten_identifiers(spec.get("entity_grain")):
        if field not in set(profile["fields"]):
            contract_errors.append(f"entity_grain field does not exist in raw rows: {field}")
    declared_output_schema = set(flatten_identifiers(spec.get("output_schema")))
    if declared_output_schema and not declared_output_schema.issubset(available_fields):
        contract_errors.append("Processing_Spec output_schema contains fields with no lineage.")
    spec["contract_errors"] = list(dict.fromkeys(contract_errors))
    return {"processing_spec": spec}
