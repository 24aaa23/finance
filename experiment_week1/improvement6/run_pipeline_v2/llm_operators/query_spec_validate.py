"""Semantic validation of a raw retrieval contract before SPARQL generation."""

from ..common import Any, Dict, LOCAL_MODEL, api_logger, json
from ..clients import build_llm_messages
from ..utils import parse_llm_json


def semantic_query_spec_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    query = inputs.get("query", "")
    original_query = inputs.get("original_query", query)
    spec = inputs.get("query_spec", {})
    decomposition = inputs.get("decomposition", {})
    retrieved = inputs.get("retrieved_tables", [])
    global_schema = inputs.get("global_schema", {})
    schema = {name: global_schema[name] for name in retrieved if name in global_schema} or global_schema
    if isinstance(spec, dict) and spec.get("contract_errors"):
        return {"query_spec_validation": {"is_valid": False,
                "reason": "; ".join(str(error) for error in spec["contract_errors"]),
                "repair_hint": "Repair the reported retrieval contract errors without removing original requirements.",
                "repair_stage": "Query_Spec"}}
    prompt = f"""
You are Query_Spec_Validate. Check a raw retrieval contract before SPARQL is generated.

Question: {query}
Original question (the final answer must satisfy this, not only the branch wording): {original_query}
Query_Spec: {json.dumps(spec, indent=2)}
Active branch: {json.dumps(inputs.get("subquestion", {}), indent=2)}
Complete decomposition: {json.dumps(decomposition, indent=2)}
Answer requirements: {json.dumps(decomposition.get("answer_requirements", {}) if isinstance(decomposition, dict) else {}, indent=2)}
Relevant schema: {json.dumps(schema, indent=2)}

The contract may fetch only raw fields. It must include the identity/key, requested filters,
requested display or grouping dimensions, and raw measure input fields needed by downstream
operators. It must not request computed totals, counts, rankings, formulas, merges, or a final
answer. Do not require a derived output column such as a total or month to be fetched.
When its source class owns a required final entity/display field, it must retrieve that field.
If a declared final grouping field can be absent, require it in optional_fields so NULL groups
survive the raw scan. Reject a branch that would make a required original-question condition,
display field, or grouping dimension impossible downstream.

Audit the original question against the complete answer_requirements and branches.
Do not accept a self-consistent plan that has lost a source, predicate, group, or
requested comparison. If decomposition lost meaning, set repair_stage Decompose.
For the active branch, verify exact categorical/identifier literals, equality versus
contains, numeric/date boundaries, conjunction/disjunction and negation scope, source
class and every assigned requirement_id. Preserve raw row identity and all composite
join keys. Do not permit an early average to change fact weighting, a schema dimension
to become a calendar bucket, or a requested grouped comparison to become detail rows.
Preserve nullable display and metric inputs unless required filters exclude nulls.
Do not require another branch's fields on this source; instead check their coverage
in that other branch. Distinguish a missing source (Decompose) from a missing raw field
or incorrect filter on the correct source (Query_Spec).

Return JSON only:
{{"is_valid": true|false, "reason": "specific coverage issue", "repair_hint": "specific raw field/key/filter to add or remove", "repair_stage": "Query_Spec|Decompose"}}
"""
    api_logger.log_call(query, "Query_Spec_Validate")
    response = client.chat.completions.create(
        model=model,
        messages=build_llm_messages("validate", prompt),
        **({} if model.lower().startswith("gpt-5") else {"temperature": 0.0}),
    )
    check = parse_llm_json(
        response.choices[0].message.content,
        {"is_valid": False, "reason": "Query_Spec_Validate returned invalid JSON.", "repair_hint": "Regenerate the raw retrieval contract."},
        "Query_Spec_Validate",
    )
    if not isinstance(check, dict):
        check = {"is_valid": False, "reason": "Query_Spec_Validate returned non-object.", "repair_hint": "Regenerate the raw retrieval contract."}
    check["is_valid"] = check.get("is_valid") is True
    return {"query_spec_validation": check}
