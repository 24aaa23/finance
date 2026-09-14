"""Pre_Scan_Validate operator."""

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json


def semantic_pre_scan_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Pre_Scan_Validate
    Validate generated SPARQL against Query_Spec before executing Scan.
    This catches semantic SPARQL errors before database execution.
    """

    query = inputs.get("query", "")
    sparql = inputs.get("sparql", "")
    query_spec = inputs.get("query_spec", {})

    if not sparql:
        return {
            "pre_scan_validation": {
                "is_valid": False,
                "reason": "No SPARQL was generated.",
                "rewrite_hint": "Generate a complete executable SPARQL query using the Query_Spec."
            }
        }

    prompt = f"""
You are Pre_Scan_Validate.

Your job is to check whether the generated SPARQL satisfies the Query_Spec before execution.
Do not execute the query.
Do not judge returned data.
Only inspect the SPARQL logic.

User Query:
{query}

Query_Spec:
{json.dumps(query_spec, indent=2)}

Generated SPARQL:
{sparql}

Validation rules:
1. Every field in query_spec["output_schema"] should appear in the SELECT output, unless there is a clearly equivalent alias.
2. Every measure in query_spec["measures"] must be implemented.
3. If a measure has formula != null, the SPARQL must implement that formula using formula_fields.
4. Never allow COUNT to replace SUM, AVG, MIN, MAX, or a formula-based measure unless Query_Spec explicitly asks for COUNT.
5. If join_policy is "inner_join", required base/event classes should not be joined using OPTIONAL + COALESCE(0). However, group-by dimension fields may use OPTIONAL + COALESCE("NULL") to preserve missing groups.
6. If grain.pre_aggregate_by is present, SPARQL should pre-aggregate at that grain before final grouping.
7. If ranking.required is true, SPARQL must include the correct ORDER BY direction and LIMIT.
8. If filters are present in Query_Spec, SPARQL must implement them.
9. If the SPARQL changes the meaning of the user query, mark invalid.
10. For entity/list questions, the returned subject must be typed with `rdf:type` for query_spec["base_entity"] or a relevant query_spec["required_classes"] entry. Using only an ID-like literal property is invalid because different classes can share identifier literals.
11. For missing-required-field questions, `FILTER NOT EXISTS` must be scoped to the typed requested entity class. Null/None values in requested display fields indicate the query may have matched the wrong class and should be marked invalid unless those fields are explicitly allowed to be missing.
12. If ORDER BY and LIMIT are used for ranking, missing deterministic tie-breaks are repairable_warning, not hard_error.
13. For missing-field queries over related records, SPARQL must show a direct object relationship or shared key between the base entity and related record before counting base entities. Independent typed class patterns with no join are invalid because they create a Cartesian product and can time out.

Return ONLY valid JSON:
{{
  "is_valid": true/false,
  "severity": "valid|acceptable_warning|repairable_warning|hard_error",
  "reason": "specific reason",
  "rewrite_hint": "specific instruction to fix the SPARQL"
}}

Severity rules:
- valid: SPARQL satisfies the spec.
- acceptable_warning: Minor issue that should not block Scan, such as harmless alias differences or OPTIONAL + COALESCE for group-by dimensions.
- repairable_warning: Query is executable but likely semantically degraded; regenerate if retries remain, otherwise Scan with warning.
- hard_error: SPARQL is empty, not executable, uses unknown classes/predicates, omits a required measure/filter, changes the entity class, or cannot answer the query.
"""

    api_logger.log_call(query, "Pre_Scan_Validate")
    request = {
        "model": model,
        "messages": build_llm_messages("validate", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    parsed = parse_llm_json(
        response.choices[0].message.content,
        {
            "is_valid": False,
            "severity": "hard_error",
            "reason": "Pre_Scan_Validate failed to parse model output.",
            "rewrite_hint": "Regenerate SPARQL using Query_Spec exactly."
        },
        "Pre_Scan_Validate",
    )
    if not isinstance(parsed, dict):
        parsed = {
            "is_valid": False,
            "severity": "hard_error",
            "reason": "Pre_Scan_Validate returned non-dict output.",
            "rewrite_hint": "Regenerate SPARQL using Query_Spec exactly."
        }
    if parsed.get("is_valid"):
        parsed["severity"] = "valid"
    elif parsed.get("severity") not in {"acceptable_warning", "repairable_warning", "hard_error"}:
        parsed["severity"] = "repairable_warning"

    return {"pre_scan_validation": parsed}
