"""Decompose operator for the improvement3 decompose-first pipeline."""

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..business_context import business_context_prompt
from ..utils import parse_llm_json
from ..sql_conditions import normalize_condition, raw_condition_errors


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()))


def _boolean(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _cleanup_decomposition(raw_decomposition: Any, query: str, retrieved_tables: list) -> Dict[str, Any]:
    errors = []
    if isinstance(raw_decomposition, list):
        raw_decomposition = {
            "decomposition_candidates": raw_decomposition,
            "selected_decomposition": raw_decomposition[0] if raw_decomposition else {},
        }
    if not isinstance(raw_decomposition, dict):
        raw_decomposition = {}

    candidates = raw_decomposition.get("decomposition_candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    selected = raw_decomposition.get("selected_decomposition", {})
    if not selected and isinstance(raw_decomposition.get("subquestions"), list):
        selected = raw_decomposition
    if not isinstance(selected, dict) or not selected:
        selected_id = raw_decomposition.get("selected_decomposition_id")
        selected = next((item for item in candidates if isinstance(item, dict) and item.get("id") == selected_id), None)
        if selected is None:
            selected = next((item for item in candidates if isinstance(item, dict)), {})

    subquestions = selected.get("subquestions", [])
    if not isinstance(subquestions, list):
        errors.append("Decompose subquestions must be a list of source branches.")
        subquestions = []
    if not subquestions:
        errors.append("Decompose did not produce any source branches; return the documented JSON plan.")
        subquestions = [
            {
                "id": "q1",
                "question": query,
                "purpose": "Answer the original question as one KG retrieval branch.",
                "depends_on": [],
            }
        ]

    cleaned_subquestions = []
    for index, subquestion in enumerate(subquestions, 1):
        if not isinstance(subquestion, dict):
            subquestion = {"question": str(subquestion)}
        cleaned_subquestions.append({**subquestion,
            "id": str(subquestion.get("id") or f"q{index}"),
            "question": str(subquestion.get("question") or query),
            "purpose": str(subquestion.get("purpose") or ""),
            "depends_on": subquestion.get("depends_on", []) if isinstance(subquestion.get("depends_on", []), list) else [],
            "source_class": subquestion.get("source_class"),
            "requirement_ids": _string_list(subquestion.get("requirement_ids", [])),
            "retrieval_grain": _string_list(subquestion.get("retrieval_grain", [])),
            "required_fields": _string_list(subquestion.get("required_fields", [])),
        })

    merge_strategy = selected.get("merge_strategy") or selected.get("merge_plan") or {}
    if not isinstance(merge_strategy, dict):
        merge_strategy = {}
    merge_strategy.setdefault("required", len(cleaned_subquestions) > 1)
    merge_strategy.setdefault("operator", "Integrate" if len(cleaned_subquestions) > 1 else None)
    merge_strategy.setdefault("join_key", None)
    merge_strategy.setdefault("reason", None)

    selected["subquestions"] = cleaned_subquestions
    selected["merge_strategy"] = merge_strategy
    requirements = selected.get("answer_requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    # One semantic contract travels through every execution partition. Never
    # rewrite literal values or discard metric population/weighting metadata here.
    requirements["original_query"] = query
    for key in ("required_projection", "group_by", "output_grain", "distinct_on", "source_classes"):
        requirements[key] = _string_list(requirements.get(key, []))
    for key in ("metrics", "predicates", "joins", "order_by"):
        value = requirements.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            errors.append(f"Decompose {key} must be a list of objects; requirements cannot be discarded.")
        requirements[key] = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    requirements["predicates"] = [normalize_condition(item) for item in requirements["predicates"]]
    requirements["preserve_null_groups"] = _boolean(requirements.get("preserve_null_groups", False))
    requirements["requires_distinct_entities"] = _boolean(requirements.get("requires_distinct_entities", False))
    if not isinstance(requirements.get("null_policy"), dict):
        requirements["null_policy"] = {}
    if not requirements["source_classes"]:
        requirements["source_classes"] = list(dict.fromkeys(item["source_class"] for item in cleaned_subquestions if item.get("source_class")))
    requirements["required_branch_ids"] = [item["id"] for item in cleaned_subquestions]
    selected["answer_requirements"] = requirements
    branch_ids = [item["id"] for item in cleaned_subquestions]
    if len(branch_ids) != len(set(branch_ids)):
        errors.append("Decomposition has duplicate branch IDs; each source retrieval needs a unique ID.")
    for predicate in requirements["predicates"]:
        if predicate.get("stage", "scan") == "scan":
            errors.extend(f"Decompose predicate {predicate.get('id', '?')}: {error}"
                          for error in raw_condition_errors(predicate))
        missing = set(_string_list(predicate.get("branch_ids"))) - set(branch_ids)
        if missing:
            errors.append("Predicate references nonexistent branches: " + ", ".join(sorted(missing)))
    # These are logical relationships, not executable scan parameters. All raw
    # branches are retrieved independently; the final relational plan applies
    # their joins/existence/aggregate dependencies. Do not reject this annotation.
    for branch in cleaned_subquestions:
        if branch.get("depends_on"):
            branch["logical_dependencies"] = branch["depends_on"]
            branch["depends_on"] = []
    selected["contract_errors"] = errors
    selected.setdefault("required_classes", retrieved_tables)
    selected.setdefault("reason", "Selected decomposition normalized by Decompose cleanup.")

    return {
        "decomposition_candidates": candidates,
        "selected_decomposition": selected,
    }


def semantic_decompose_question(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Decompose
    Creates one retrieval decomposition before DAG planning.
    """

    query = inputs.get("query", "")
    retrieved_tables = inputs.get("retrieved_tables", [])
    global_schema = inputs.get("global_schema", {})
    decomposition_feedback = inputs.get("decomposition_feedback", "")
    schema_details = {
        cls: global_schema[cls]
        for cls in retrieved_tables
        if cls in global_schema
    } or global_schema
    connector_sources = {
        name: {"subject_field": details.get("subject_field"),
               "columns": [{key: column[key] for key in ("name", "datatype") if key in column}
                           if isinstance(column, dict) else column
                           for column in details.get("columns", [])]}
        for name, details in global_schema.items() if name not in schema_details
    }
    business_context = business_context_prompt()

    prompt = f"""
Split the question into small raw-data retrieval tasks.
A source is a physical SQLite table in the schema. A branch is one task that reads
one table. The compatibility field source_class contains that exact table name.
Later code retrieves its columns and calculates the final answer.
Your job here is to choose sources, preserve conditions, and describe connections.

Question: {query}
Suggested tables: {retrieved_tables}
Schema: {json.dumps(schema_details)}
Other available sources (fields and relationships for needed connectors): {json.dumps(connector_sources)}
Business rule pack, authoritative for metric definitions and rule clashes: {business_context}
Repair feedback: {decomposition_feedback}

Rules:
- Use one branch for a simple lookup. Add branches only for needed sources or
  separate conditions. Each branch reads independently, without waiting for IDs.
- Use exact schema names. Include a connecting source when facts need it; a
  category record is not a person record. Similar labels do not prove a connection.
  Suggested classes are a starting point: add a source from the catalogue when a
  requested attribute or connection requires it. Follow schema reference targets.
  For example, if Sale points to Customer and Customer points to Region, grouping
  sales by region requires the Customer connector, even if no customer field is
  displayed. Retrieve its identity and region reference in a separate branch.
  If the fact already points directly to the requested dimension, use that path.
- Read source descriptions, field descriptions/allowed_values, and derived_metrics
  before choosing fields. derived_metrics are documented calculations, not stored
  fields: retrieve their operands. A categorical event/scenario label describes
  what occurred; a numeric before/after change describes its effect. Choose the
  documented meaning appropriate to the requested metric, not a name-only match.
  Apply the business rule pack before guessing metric definitions, weighting,
  signs, ranking tie-breaks, null policy, or population grain.
- Preserve exact values, comparisons, dates, AND/OR, and absence conditions in
  branch questions. Do not add non-null filters just to make calculation easier.
- Retrieve raw records. Leave sums, averages, ranking, formulas, and final output
  names to the later calculation step. Preserve each metric's meaning in
  calculation_notes and list its raw operands in required_fields on its branch.
  A change/gap needs both operands from the correct source, not a name or count
  of events. A signed difference is not an absolute or percentage difference.
  Do not substitute another source's similarly named metric when data is missing.
- For each comparison, identify whose attribute defines the group and whose
  observations are being compared. A person's category differs from their
  holdings' categories. State the owner in calculation_notes; use the schema.
  Include a connector table only when the physical schema and requested relation need it.
- Include record identity and the fields needed to link the selected sources.
  For comparisons by an entity's attributes, include the source that connects
  that entity to those attributes, not only a separate list of attribute labels.
  Use actual scalar key columns and their stored values. Join keys must identify
  the same kind of entity; a display label is not an identity key. Prefer declared
  primary/foreign keys when available. Missing constraint metadata does not prove
  uniqueness, and sample rows do not establish a key. Do not invent subject_iri.
- Do not write SQL, execution steps, or alternative plans. Keep calculation_notes
  short: metric source and meaning, observation/entity weighting, group owner,
  required participation, and aggregate-filter scope. Preserve explicit definitions.
  If wording leaves a definition ambiguous, record the assumption rather than
  presenting a guessed definition as a requirement. Do not add unrequested metrics.

Return one JSON object. These fields mean:
subquestions: the retrieval branches; id: unique branch name; question: its task;
source_class: exact physical table name; retrieval_grain: real columns identifying one raw record;
required_fields: raw operands, display attributes and keys needed from this source
(separate from retrieval_grain; an amount or label is not a record identity);
requirement_ids: IDs of conditions assigned to this branch.
answer_requirements: shared conditions, connections and concise calculation_notes.
predicates: explicit conditions; stage is scan for a raw-field condition or final
for a condition on a calculated value. branch_ids identifies the responsible tasks.
joins: known connections; left_on/right_on are the actual fields on those branches.
Use empty lists when none apply; do not invent missing schema fields.

{{"selected_decomposition": {{
  "subquestions": [{{"id":"q1", "question":"raw records and conditions needed",
    "source_class":"exact table name", "retrieval_grain":["record key"],
    "required_fields":[], "requirement_ids":[]}}],
  "answer_requirements": {{
    "predicates": [],
    "joins": [], "calculation_notes": "metric meanings, grain, group owner and population; assumptions if needed"
  }}
}}}}
Condition shape: {{"id":"p1", "source_class":"exact table name",
 "field":"exact field", "operator":"=", "value":"exact literal",
 "stage":"scan", "branch_ids":["q1"]}}
Connection shape: {{"left_branch":"q1", "right_branch":"q2",
 "left_on":["reference field"], "right_on":["matching identity field"]}}
For missing/present values use operator is_null/is_not_null and JSON value null.
For between use a two-element value array [lower, upper], never one SQL expression string.
Supported raw operators: =, !=, >, <, >=, <=, between, in, not_in, contains,
is_null, is_not_null. Do not use SQL-only LIKE expressions. For calendar periods,
express the exact requested date boundaries with these supported operators.
"""

    api_logger.log_call(query, "Decompose")
    request = {
        "model": model,
        "messages": build_llm_messages("decompose", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.2
    response = client.chat.completions.create(**request)

    parsed = parse_llm_json(
        response.choices[0].message.content,
        {},
        "Decompose",
    )
    cleaned = _cleanup_decomposition(parsed, query, retrieved_tables)
    if global_schema:
        for branch in cleaned["selected_decomposition"]["subquestions"]:
            if branch.get("source_class") not in global_schema:
                cleaned["selected_decomposition"]["contract_errors"].append(
                    f"Branch {branch['id']} needs an existing source_class, got {branch.get('source_class')!r}.")
            details = global_schema.get(branch.get("source_class"), {})
            fields = {c.get("name") if isinstance(c, dict) else c for c in details.get("columns", [])}
            fields.add(details.get("subject_field"))
            missing = set(branch["required_fields"]) - fields
            if missing:
                cleaned["selected_decomposition"]["contract_errors"].append(
                    f"Branch {branch['id']} requests unknown raw fields: {sorted(missing)}. Use the owning source's schema.")
    return cleaned
