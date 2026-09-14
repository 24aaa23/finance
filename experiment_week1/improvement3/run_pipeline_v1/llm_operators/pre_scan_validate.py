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
                "rewrite_hint": "Generate a complete executable raw-retrieval SPARQL query using retrieval_specs."
            }
        }

    prompt = f"""
You are Pre_Scan_Validate.

Your job is to check whether the generated SPARQL satisfies the operator-first Query_Spec before execution.
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
1. SPARQL should satisfy one retrieval_spec by selecting the raw fields needed downstream.
2. SPARQL should anchor the selected subject with rdf:type for the retrieval_spec class or a relevant required_classes entry.
3. Simple entity/text/date/number filters from retrieval_specs may be implemented in SPARQL.
4. If query_spec has operator_plan, do NOT require SPARQL to implement SUM, AVG, COUNT, MIN, MAX, formulas, ranking, GROUP BY, ORDER BY, or LIMIT.
5. If query_spec has operator_plan, raw unaggregated rows are valid because post-scan operators compute the final answer.
6. Mark hard_error only if the query is empty/not executable, uses unknown terms, selects none of the required raw fields, changes the entity class, or has an unsafe unjoined graph pattern.
7. For entity/list questions, the returned subject must be typed with rdf:type for the retrieval class or a relevant required class. Using only an ID-like literal property is invalid because different classes can share identifier literals.
8. For missing-required-field questions, FILTER NOT EXISTS must be scoped to the typed requested entity class.
9. Independent typed class patterns with no direct relationship or shared key are invalid because they create a Cartesian product and can time out.

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
- hard_error: SPARQL is empty, not executable, uses unknown classes/predicates, omits required raw retrieval fields, changes the entity class, or cannot support downstream operators.
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
            "rewrite_hint": "Regenerate simple raw-retrieval SPARQL using retrieval_specs."
        },
        "Pre_Scan_Validate",
    )
    if not isinstance(parsed, dict):
        parsed = {
            "is_valid": False,
            "severity": "hard_error",
            "reason": "Pre_Scan_Validate returned non-dict output.",
            "rewrite_hint": "Regenerate simple raw-retrieval SPARQL using retrieval_specs."
        }
    if parsed.get("is_valid"):
        parsed["severity"] = "valid"
    elif parsed.get("severity") not in {"acceptable_warning", "repairable_warning", "hard_error"}:
        parsed["severity"] = "repairable_warning"

    return {"pre_scan_validation": parsed}
