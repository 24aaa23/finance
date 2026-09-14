"""Query_Spec operator and its helpers."""

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json


def semantic_build_query_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Query_Spec
    Convert the natural language question into a schema-grounded DAG/operator plan.

    Improvement2 shifts computation out of SPARQL. Query_Spec now describes:
    - smaller KG-answerable retrieval specs
    - the operator sequence to apply after Scan
    - merge/set/math/ranking instructions
    """

    query = inputs.get("query", "")
    retrieved_tables = inputs.get("retrieved_tables", [])

    schema_details = inputs.get("schema_details")
    if not schema_details:
        global_schema = inputs.get("global_schema", {})
        schema_details = {
            cls: global_schema[cls]
            for cls in retrieved_tables
            if cls in global_schema
        }
        if not schema_details:
            schema_details = global_schema

    prompt = f"""
You are the Query_Spec operator for an Agent-Oriented Pipeline.

Your task is NOT to write SPARQL.
Your task is to break the original question into smaller KG-answerable retrievals, then plan
which existing operators should run on the retrieved rows.

User Query:
{query}

Retrieved Classes:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

IMPORTANT RULES:
- Use only classes and fields present in Schema Details.
- Do not invent classes.
- Do not invent fields.
- Do not write SPARQL.
- Keep each retrieval spec simple: one main class, raw fields, and only essential entity/text filters.
- Put SUM, AVG, COUNT, MIN, MAX, ranking, formulas, set logic, and merging into operator_plan, not SPARQL.
- Prefer existing operators only: Filter_Aggregate, Math_Compute, Order_By, Set_Intersect,
  Set_Union, Set_Difference, Integrate.
- If one retrieval cannot answer the full question, create multiple retrieval_specs and a merge_plan.
- Return only valid JSON.

Output JSON in exactly this structure:

{{
  "question_type": "lookup|filter|aggregation|ranking|comparison|set_logic|math|multi_step",
  "subquestions": [
    {{
      "id": "short_unique_id",
      "question": "smaller KG-answerable question",
      "depends_on": []
    }}
  ],
  "retrieval_specs": [
    {{
      "id": "short_unique_id_matching_or_related_to_subquestion",
      "class": "SchemaClassName",
      "fields": ["field_name"],
      "filters": [
        {{
          "field": "field_name",
          "operator": "=|contains|>|<|>=|<=|between|in|not_in",
          "value": "literal value",
          "value_type": "string|number|date|list"
        }}
      ],
      "purpose": "what facts this scan retrieves"
    }}
  ],
  "operator_plan": [
    {{
      "operator": "Filter_Aggregate|Math_Compute|Order_By|Set_Intersect|Set_Union|Set_Difference|Integrate",
      "input": "retrieval_spec_id_or_previous_step_id",
      "output": "short_unique_step_id",
      "operation": "filter|sum|avg|count|min|max|difference|absolute_gap|ratio|percentage_change|sort|merge",
      "group_by": [],
      "target_column": null,
      "left_column": null,
      "right_column": null,
      "output_column": null,
      "column": null,
      "direction": null,
      "limit": null,
      "join_key": null,
      "filters": []
    }}
  ],
  "merge_plan": {{
    "required": false,
    "operator": null,
    "left_input": null,
    "right_input": null,
    "join_key": null,
    "reason": null
  }},
  "required_classes": ["SchemaClassName"],
  "output_schema": ["final_column_name"],
  "reason": "short explanation"
}}
"""

    default_spec = {
        "question_type": "multi_step",
        "subquestions": [],
        "retrieval_specs": [
            {
                "id": "main",
                "class": retrieved_tables[0] if retrieved_tables else None,
                "fields": [],
                "filters": [],
                "purpose": "Retrieve raw facts for the original question.",
            }
        ],
        "operator_plan": [],
        "merge_plan": {
            "required": False,
            "operator": None,
            "left_input": None,
            "right_input": None,
            "join_key": None,
            "reason": None,
        },
        "required_classes": retrieved_tables,
        "output_schema": [],
        "reason": "Query_Spec failed to parse model output.",
    }

    api_logger.log_call(query, "Query_Spec")
    request = {
        "model": model,
        "messages": build_llm_messages("query_spec", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    parsed_spec = parse_llm_json(
        response.choices[0].message.content,
        default_spec,
        "Query_Spec",
    )
    if not isinstance(parsed_spec, dict):
        parsed_spec = {**default_spec, "reason": "Query_Spec returned non-dict output."}

    parsed_spec = cleanup_query_spec(parsed_spec, query, retrieved_tables)
    return {"query_spec": parsed_spec}


def cleanup_query_spec(query_spec: Dict[str, Any], query: str, retrieved_tables: list) -> Dict[str, Any]:
    """Normalize Query_Spec output for the operator-first execution contract."""
    if not isinstance(query_spec, dict):
        return query_spec

    cleaned = json.loads(json.dumps(query_spec))
    cleanup_notes = []

    question_type = str(cleaned.get("question_type") or cleaned.get("query_type") or "multi_step").lower()
    if question_type not in {"lookup", "filter", "aggregation", "ranking", "comparison", "set_logic", "math", "multi_step"}:
        question_type = "multi_step"
        cleanup_notes.append("unknown question_type normalized to multi_step")
    cleaned["question_type"] = question_type
    cleaned["query_type"] = question_type

    retrieval_specs = cleaned.get("retrieval_specs", [])
    if not isinstance(retrieval_specs, list):
        retrieval_specs = []
    if not retrieval_specs:
        retrieval_specs = [
            {
                "id": "main",
                "class": retrieved_tables[0] if retrieved_tables else None,
                "fields": [],
                "filters": [],
                "purpose": "Retrieve raw facts for the original question.",
            }
        ]
        cleanup_notes.append("retrieval_specs filled from retrieved classes")
    for index, spec in enumerate(retrieval_specs):
        if not isinstance(spec, dict):
            retrieval_specs[index] = {"id": f"scan_{index + 1}", "class": None, "fields": [], "filters": []}
            continue
        spec.setdefault("id", f"scan_{index + 1}")
        spec.setdefault("fields", [])
        spec.setdefault("filters", [])
        spec.setdefault("purpose", "")
    cleaned["retrieval_specs"] = retrieval_specs

    if not cleaned.get("required_classes"):
        cleaned["required_classes"] = [
            spec.get("class")
            for spec in retrieval_specs
            if isinstance(spec, dict) and spec.get("class")
        ] or retrieved_tables
        cleanup_notes.append("required_classes filled from retrieval_specs")

    operator_plan = cleaned.get("operator_plan", [])
    if not isinstance(operator_plan, list):
        operator_plan = []
        cleanup_notes.append("operator_plan normalized to empty list")
    for index, step in enumerate(operator_plan):
        if not isinstance(step, dict):
            operator_plan[index] = {"operator": "Integrate", "input": None, "output": f"step_{index + 1}"}
            continue
        step.setdefault("output", f"step_{index + 1}")
        step.setdefault("filters", [])
        step.setdefault("group_by", [])
    cleaned["operator_plan"] = operator_plan

    merge_plan = cleaned.get("merge_plan", {})
    if not isinstance(merge_plan, dict):
        merge_plan = {}
    merge_plan.setdefault("required", False)
    merge_plan.setdefault("operator", None)
    merge_plan.setdefault("left_input", None)
    merge_plan.setdefault("right_input", None)
    merge_plan.setdefault("join_key", None)
    merge_plan.setdefault("reason", None)
    cleaned["merge_plan"] = merge_plan

    output_schema = cleaned.get("output_schema", [])
    cleaned["output_schema"] = output_schema if isinstance(output_schema, list) else []

    # Backward-compatible hints used by older Validate/Generate code paths.
    cleaned["execution_strategy"] = "operator_first"
    cleaned["measures"] = cleaned.get("measures", [])
    cleaned["group_by"] = cleaned.get("group_by", [])
    cleaned["filters"] = cleaned.get("filters", [])

    if cleanup_notes:
        prior_reason = str(cleaned.get("reason", "")).strip()
        cleaned["cleanup_notes"] = cleanup_notes
        cleaned["reason"] = (prior_reason + " Cleanup: " + "; ".join(cleanup_notes)).strip()

    return cleaned
