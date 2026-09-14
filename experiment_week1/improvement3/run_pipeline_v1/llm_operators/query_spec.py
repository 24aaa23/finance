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
from ..spec_contracts import normalize_spec, validate_query_spec_contract


def semantic_build_query_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Query_Spec
    Convert one decomposition branch into a schema-grounded raw retrieval contract.
    """

    query = inputs.get("query", "")
    original_query = inputs.get("original_query", query)
    subquestion = inputs.get("subquestion", {})
    decomposition = inputs.get("decomposition", {})
    retrieved_tables = inputs.get("retrieved_tables", [])
    spec_feedback = inputs.get("spec_feedback", "")

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

Your task is NOT to write SPARQL or a computation plan.
Create exactly one raw-data retrieval contract for the active decomposition branch.

User Query:
{query}

Original User Query:
{original_query}

Active Subquestion:
{json.dumps(subquestion, indent=2)}

Selected Decomposition:
{json.dumps(decomposition, indent=2)}

Retrieved Classes:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

Repair feedback from a previous invalid contract, if any:
{spec_feedback}

IMPORTANT RULES:
- Use only classes and fields present in Schema Details.
- Do not invent classes.
- Do not invent fields.
- Do not write SPARQL.
- Build Query_Spec for Active Subquestion, not the whole original question.
- Return exactly one retrieval_spec: one main class, raw fields, entity_key, and only source-level filters.
- Include every raw field needed by downstream processing, including stable entity/join keys.
- Do NOT include SUM, AVG, COUNT, MIN, MAX, ranking, formulas, set logic, merges, or operator plans.
- Put nullable grouping fields in optional_fields so Generate can preserve null groups.
- Return only valid JSON.

Output JSON in exactly this structure:

{{
  "id": "branch_retrieval_id",
  "question_type": "lookup|filter",
  "retrieval_specs": [{{
    "id": "branch_retrieval_id",
    "class": "SchemaClassName",
    "entity_key": ["entityId"],
    "fields": ["entityId", "field_name"],
    "optional_fields": ["nullable_grouping_field"],
    "filters": [{{"field": "field_name", "operator": "=|contains|>|<|>=|<=|between|in|not_in", "value": "literal value", "value_type": "string|number|date|list"}}],
    "purpose": "what raw facts this scan retrieves"
  }}],
  "required_classes": ["SchemaClassName"],
  "output_schema": ["entityId", "field_name"],
  "reason": "short explanation"
}}
"""

    default_spec = {
        "id": str(subquestion.get("id") or "main") if isinstance(subquestion, dict) else "main",
        "question_type": "lookup",
        "retrieval_specs": [
            {
                "id": "main",
                "class": retrieved_tables[0] if retrieved_tables else None,
                "entity_key": [],
                "fields": [],
                "optional_fields": [],
                "filters": [],
                "purpose": "Retrieve raw facts for the original question.",
            }
        ],
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
    parsed_spec = normalize_spec(parsed_spec)
    parsed_spec["contract_errors"] = validate_query_spec_contract(parsed_spec, inputs.get("global_schema", schema_details))
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
    # A Query_Spec belongs to one decomposition branch.  Extra scans belong in extra
    # decompositions, not in this retrieval contract.
    if len(retrieval_specs) > 1:
        retrieval_specs = retrieval_specs[:1]
        cleanup_notes.append("retrieval_specs reduced to the single active branch retrieval")
    for index, spec in enumerate(retrieval_specs):
        if not isinstance(spec, dict):
            retrieval_specs[index] = {"id": f"scan_{index + 1}", "class": None, "fields": [], "filters": []}
            continue
        spec.setdefault("id", f"scan_{index + 1}")
        spec.setdefault("entity_key", [])
        spec.setdefault("fields", [])
        spec.setdefault("optional_fields", [])
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

    # Query_Spec is intentionally retrieval-only.  Processing_Spec and Final_Spec own computation.
    cleaned["operator_plan"] = []
    cleaned["merge_plan"] = {"required": False, "operator": None, "join_key": None}

    output_schema = cleaned.get("output_schema", [])
    cleaned["output_schema"] = output_schema if isinstance(output_schema, list) else []

    # Backward-compatible hints used by Generate/Validate code paths.
    cleaned["execution_strategy"] = "raw_retrieval_only"
    cleaned["measures"] = []
    cleaned["group_by"] = []
    cleaned["filters"] = []

    if cleanup_notes:
        prior_reason = str(cleaned.get("reason", "")).strip()
        cleaned["cleanup_notes"] = cleanup_notes
        cleaned["reason"] = (prior_reason + " Cleanup: " + "; ".join(cleanup_notes)).strip()

    return cleaned
