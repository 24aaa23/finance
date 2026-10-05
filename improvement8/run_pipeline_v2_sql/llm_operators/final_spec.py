"""One compact final-plan format, executed by the existing deterministic engine."""
from copy import deepcopy
import re

from ..common import Any, Dict, LOCAL_MODEL, api_logger, json
from ..clients import build_llm_messages
from ..business_context import business_context_prompt
from ..utils import parse_llm_json
from ..spec_contracts import normalize_spec
from ..spec_runtime import compile_spec
from ..query_understanding import final_contract_errors
from ..consultation import consultation_prompt, consultation_request


PLAN_KEYS = {"final_steps", "merge_steps", "pre_steps", "final_measures", "final_group_by",
             "projection", "final_output", "distinct", "distinct_on", "rounding", "missing_requirements", "assumptions"}


def _branch_context(branches, schema):
    profiles, hints = [], []
    owners = {}
    for branch in branches:
        names = {item.get("class") for item in branch.get("retrieval_specs", []) if isinstance(item, dict)}
        source = next(iter(names)) if len(names) == 1 else None
        profile = {key: branch.get(key) for key in ("id", "branch_id", "question", "fields", "row_count", "sample", "column_stats")}
        profile["source_class"] = source
        profile["retrieval_specs"] = branch.get("retrieval_specs", [])
        details = schema.get(source, {})
        profile["source_description"] = details.get("description", "")
        profile["documented_derived_metrics"] = details.get("derived_metrics", [])
        profile["field_metadata"] = [c for c in details.get("columns", [])
                                     if isinstance(c, dict) and c.get("name") in (profile["fields"] or [])]
        profile["available_source_fields"] = [c.get("name") if isinstance(c, dict) else c
                                               for c in details.get("columns", [])]
        profiles.append(profile)
        if source:
            owners.setdefault(source, []).append(profile)
    for profile in profiles:
        details = schema.get(profile["source_class"], {})
        for column in details.get("columns", []):
            if not isinstance(column, dict) or column.get("name") not in profile["fields"]:
                continue
            target = re.search(r"points to:\s*([^)]+)", str(column.get("datatype", "")))
            if not target:
                continue
            for right in owners.get(target.group(1).strip(), []):
                subject = schema.get(right["source_class"], {}).get("subject_field")
                if right["id"] != profile["id"] and subject in right["fields"]:
                    hints.append({"inputs": [profile["id"], right["id"]],
                                  "left_on": [column["name"]], "right_on": [subject]})
    return profiles, hints


def normalize_final_plan(payload, branches):
    """Accept wrappers/step spellings; never invent missing inputs or operations."""
    if isinstance(payload, dict):
        for wrapper in ("final_spec", "plan"):
            if isinstance(payload.get(wrapper), dict) and not PLAN_KEYS.intersection(payload):
                payload = payload[wrapper]
    if isinstance(payload, list):
        payload = {"final_steps": payload}
    if not isinstance(payload, dict):
        return {}
    payload = deepcopy(payload)
    if "steps" in payload and "final_steps" not in payload:
        payload["final_steps"] = payload.pop("steps")
        if "output" in payload:
            payload.setdefault("final_output", payload.pop("output"))
    candidates = {}
    originals = {str(branch["id"]) for branch in branches}
    for branch in branches:
        names = [branch.get("branch_id")]
        names += [item.get("class") for item in branch.get("retrieval_specs", []) if isinstance(item, dict)]
        for name in names:
            if name:
                candidates.setdefault(str(name), set()).add(str(branch["id"]))
    aliases = {name: next(iter(ids)) for name, ids in candidates.items() if len(ids) == 1 and name not in originals}
    normalized = normalize_spec(payload)
    def dataset_id(value):
        if isinstance(value, list):
            return [dataset_id(item) for item in value]
        return aliases.get(value, value) if isinstance(value, str) else value
    for key in ("final_steps", "merge_steps", "pre_steps", "final_measures"):
        for step in normalized.get(key, []) if isinstance(normalized.get(key), list) else []:
            if isinstance(step, dict):
                for field in ("input", "inputs"):
                    if field in step:
                        step[field] = dataset_id(step[field])
    if "final_output" in normalized:
        normalized["final_output"] = dataset_id(normalized["final_output"])
    return normalized


def semantic_build_final_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    query = inputs.get("original_query", inputs.get("query", ""))
    branches = inputs.get("processed_datasets", [])
    profiles, joins = _branch_context(branches, inputs.get("global_schema", {}))
    requirements = inputs.get("answer_requirements") or inputs.get("decomposition", {}).get("answer_requirements", {})
    source_contract = {key: requirements.get(key, []) for key in ("predicates", "joins", "calculation_notes", "metrics", "group_by", "required_projection", "order_by", "query_understanding")}
    previous = {key: value for key, value in inputs.get("previous_final_spec", {}).items() if key in PLAN_KEYS}
    business_context = business_context_prompt()
    prompt = f"""Return one JSON calculation plan answering the question from the available tables.
A table is a list of retrieved records. A step applies one operation and names its
result so later steps can use it. Python executes these steps; do not write SQL.

Choose the calculation grain before joining or aggregating:
- Independent fact sources can contain several rows per entity. Joining their raw
  rows multiplies observations. When comparing per-entity metrics, calculate each
  source's requested metric per entity first, join those summaries through the
  entity's profile, then group by the requested profile attribute.
- Choose each inner calculation from the question and supplied definitions: totals
  use SUM per entity; maxima use MAX; means use AVG of the relevant observations.
  Apply an outer AVG only when an average across entities is requested.
  "Compare" alone does not specify a metric.
- A mean across observations and a mean across entity summaries have different
  weights. For an observation mean, aggregate raw observations at the requested
  group or carry SUM and non-null COUNT through summaries and divide their totals.
  Do not average entity averages unless each entity should have equal weight.
- Many-to-one dimension joins can precede aggregation. Follow the requested
  population and metric grain; there is no blanket requirement to summarize every
  source before every join. Each metric ignores only its own missing inputs.
- Decide inner and outer aggregation separately for EVERY metric, including
  amounts and counts. A mean transaction count is AVG(per-entity COUNT(*)), not
  COUNT(*) for the group. A mean total value is AVG(per-entity SUM(value)), not
  SUM(value) for the group. Keep average amounts distinct from total amounts.
- For joint comparisons, establish the requested common entity population before
  computing group averages. Separately grouping each source then joining labels
  can compare different populations even when all labels match. Required fact
  participation uses inner joins of entity summaries; optional labels use left
  joins. Keeping a null label does not require making every fact join left.
- Prefer a display attribute already on its owning profile over a redundant label
  lookup. If a lookup is needed, attach its nullable label BEFORE the final group:
  different missing/unresolved references must form one null display group.
- Use field_metadata and calculation_notes to choose the exact source operands.
  Never turn a change into an event count or use a scenario gap for an action gap.
  Calculate paired differences before averaging: AVG(after-before) differs from
  AVG(after)-AVG(before) when operands have different nulls. Preserve direction.
  Request missing raw operands instead of substituting an available metric.

Business rule pack, authoritative for metric definitions, formula precedence, signs, weighting, nulls, ranking tie-breaks and populations: {business_context}
Question: {query}
Available tables (actual column names and sample values): {json.dumps(profiles, default=str)}
Schema relationship join options: {json.dumps(joins)}
Declared source conditions and connections (branch_id maps to each table above): {json.dumps(source_contract, default=str)}
Repair errors, if any: {inputs.get('spec_feedback', '')}
Previous plan, if any: {json.dumps(previous, default=str)}

Use this single format: {{"final_steps": [], "projection": ["requested output columns"], "assumptions": []}}
Record underspecified metric, weighting, population or band choices in assumptions.
Do not invent extra outputs to cover guesses. Explicit question definitions win.
final_steps is the ordered list of operations. projection lists columns to return.
Steps run in listed order. Use id for a step result, input for one table, inputs for joins.
Use actual table IDs or earlier step IDs; previous means the preceding result. With one
raw table, omitted input uses it. With multiple raw tables the first input must be explicit.
A lookup needs no steps. Output is the last step, or final_output for a chosen table.

Operators and exact syntax (replace example field/table names with available ones):
- Join: {{"id":"joined","operator":"Integrate","inputs":["left_table","right_table"],
  "left_on":["customer_id"],"right_on":["id"],"join_type":"inner"}}
  join_type is inner|left|right|outer. Use both left_on and right_on for different names.
  Same-name non-key columns from the right get _right, then _right_2 if already occupied.
  Use inner join when both sides must participate (entities with BOTH types of
  required related records). Use left join to preserve a requested base population when related
  facts or labels are optional. A missing related metric remains null unless the
  question defines a default. Do not discard a base entity just because a label is missing.
  Declare cardinality:"many_to_one" for lookup joins, "one_to_one" for entity
  summaries, or "one_to_many"/"many_to_many" when intentional. Actual rows validate
  this declaration. column_stats measures non-null distinct counts and maximum
  multiplicity over the complete scan; three sample rows cannot prove uniqueness.
  Ordinary joins do not match null keys. To merge already aggregated groups from
  the SAME population and grouping, explicitly set nulls_equal:true; otherwise
  an outer join creates two incomplete null groups. Do not enable it on entity IDs.
- Aggregate: {{"id":"totals","operator":"Filter_Aggregate","input":"joined",
  "group_by":["category"],"aggregations":[
  {{"operation":"count_rows","input_column":"*","output_column":"n"}},
  {{"operation":"sum","input_column":"amount","output_column":"total"}}]}}
  Operations: count_rows, count (non-null), count_distinct, sum, avg, min, max.
  All metrics in this list use the same original input. Output contains group keys and metrics.
- Filter: {{"operator":"Filter_Aggregate","operation":"filter",
  "filters":[{{"field":"total","operator":">","value":10}}]}}
- Copy/rename a field: {{"operator":"Math_Compute","expression":"column('category_name')",
  "output_column":"category"}}. Text copies are allowed; do not sum/average text labels.
- Formula: {{"operator":"Math_Compute","expression":"total / nullif(n, 0)","output_column":"average"}}.
  Arithmetic supports + - * /, abs, round, coalesce, nullif, column('exact name').
  column reads a field; coalesce picks the first non-null value; nullif(a,b) returns
  null when a equals b. Do not replace missing values with zero unless intended.
  Conditional values: where(amount > 0, amount, 0), where(kind == 'credit', amount,
  -amount). Supports == != < <= > >=, and/or/not; a null condition selects the else
  value. This is a row formula, not a filter: SUM(where(...)) retains entities with
  no qualifying rows. Follow supplied definitions for signs and units.
  where(..., value, null) excludes only that metric's
  nonqualifying observations from AVG without excluding other metrics' inputs.
  is_null(value) and is_not_null(value) test presence. Never compare == null or
  != null; those are not presence tests. Simple arithmetic already propagates
  nulls, so after-before needs no conditional presence wrapper.
- Sort: {{"operator":"Order_By","order_by":[{{"column":"total","direction":"DESC"}}],"limit":5}}
- Date: {{"operator":"Date_Extract","input_column":"date","part":"month","output_column":"month"}}
  year/month/day are available; month returns YYYY-MM and day YYYY-MM-DD.
- Bucket: {{"operator":"Bucket","input_column":"n","output_column":"band",
  "rules":[{{"label":"low","min":0,"max":10,"max_inclusive":false}}]}}
  Rules apply in order. Optional default supplies the ELSE label, including null
  inputs. Omit default to leave unmatched values null. Use supplied band boundaries;
  if the question gives none, disclose the chosen boundaries in assumptions.
- Set_Intersect keeps left rows with a matching right key; Set_Difference keeps
  left rows with no matching right key. Both use inputs and left_on/right_on like Join.
  For EXISTS/NOT EXISTS row filtering, set distinct:false and nulls_equal:false:
  preserve left duplicates and do not match missing keys. For distinct set results,
  distinct defaults true and nulls_equal defaults true.
- Set_Union combines rows from inputs. distinct_on lists keys for removing duplicate
  final rows; omit it when duplicates should remain.

Worked example (illustrative names; use your actual tables and fields):
"For customers with both payments and reviews, by region show mean total spend per
customer and mean of each customer's average review score."
Payments has customer_ref/amount, Reviews has customer_ref/score, and Customers has
customer_id/region. These are separate sources; region belongs to Customers.
{{"final_steps":[
 {{"id":"spend","operator":"Filter_Aggregate","input":"Payments",
   "group_by":["customer_ref"],"aggregations":[
   {{"operation":"sum","input_column":"amount","output_column":"customer_spend"}}]}},
 {{"id":"scores","operator":"Filter_Aggregate","input":"Reviews",
   "group_by":["customer_ref"],"aggregations":[
   {{"operation":"avg","input_column":"score","output_column":"customer_score"}}]}},
 {{"id":"metrics","operator":"Integrate","inputs":["spend","scores"],
   "left_on":["customer_ref"],"right_on":["customer_ref"],"join_type":"inner"}},
 {{"id":"profiles","operator":"Integrate","inputs":["metrics","Customers"],
   "left_on":["customer_ref"],"right_on":["customer_id"],"join_type":"inner"}},
 {{"operator":"Filter_Aggregate","input":"profiles","group_by":["region"],
   "aggregations":[
   {{"operation":"avg","input_column":"customer_spend","output_column":"mean_spend"}},
   {{"operation":"avg","input_column":"customer_score","output_column":"mean_score"}}]}}
],"projection":["region","mean_spend","mean_score"]}}

Preserve the question's predicates, population, null groups, weighting, and limits.
Preserve resolved query_understanding owners, formulas, output aliases, grouping,
ordering and limit. Do not reinterpret them silently. Use the documented aliases
in projection. Report missing requirements if their raw operands are unavailable.
Keep each branch's responsibility and declared connection meaning; the original
question wins if planning notes contradict it. A group belongs to its owning source,
not any other source with a similarly named label. If a connection needs a missing
source, request it; do not join unrelated identities to obtain an empty answer.
Join real scalar columns identifying the same entity type and using the same
stored representation. Unrelated tables' primary keys need not identify the same
entity. Do not rewrite key values or substitute a display label for an identity key.
Conditions on aggregate values (SQL HAVING) are filter steps after aggregation.
Renaming does not create a new source field. Use real available columns only.
After aggregation only its group keys and output metrics remain. Follow the
actual column names through every step, including right-side join suffixes; copy
or rename display fields before joining when that makes their source unambiguous.
Project requested display fields/metrics; aggregate inputs and filtering-only metrics
need not be displayed. Optional nulls are legitimate unless an explicit filter excludes them.
Only deduplicate or limit if requested. For final distinctness set distinct_on at the top.
Only round when requested. Before requesting retrieval, check every available
table and schema relationship: an attribute may be on an existing profile or
dimension branch, or may need to be carried as a grouping key through a summary.
A missing calculated alias is a plan error, not a field to retrieve.
If required source data or a connector is truly absent, return
{{"missing_requirements":[{{"source_class":"needed source", "field":"needed field"}}]}}.
missing_requirements describes data to retrieve; never invent that data. Return JSON only.
"""
    prompt += consultation_prompt(inputs)
    api_logger.log_call(query, "Final_Spec")
    response = client.chat.completions.create(model=model,
        messages=build_llm_messages("final_spec", prompt),
        **({} if model.lower().startswith("gpt-5") else {"temperature": 0.0}))
    choice = response.choices[0]
    content = choice.message.content or ""
    parsed_response = parse_llm_json(content, None, "Final_Spec")
    if inputs.get("agent_consultation_enabled") and consultation_request(parsed_response):
        return consultation_request(parsed_response)
    parsed = normalize_final_plan(parsed_response, branches)
    diagnostics = {"finish_reason": getattr(choice, "finish_reason", None), "raw_response": content[:16000],
                   "response_chars": len(content), "response_truncated_in_log": len(content) > 16000}
    if not parsed or not PLAN_KEYS.intersection(parsed):
        return {"final_spec": {"contract_errors": ["Final_Spec must return a JSON plan with final_steps or projection."],
                               "response_diagnostics": diagnostics}}
    parsed.setdefault("preserve_null_groups", True)
    parsed.setdefault("rounding", None)
    spec = compile_spec(parsed, {str(branch["id"]): branch.get("fields", []) for branch in branches})
    spec["response_diagnostics"] = diagnostics
    if inputs.get("contract_checks", True):
        spec["contract_errors"].extend(final_contract_errors(spec, requirements.get("query_understanding", {})))
    if parsed.get("missing_requirements"):
        spec["contract_errors"].append("Missing retrieval: " + json.dumps(parsed["missing_requirements"]))
        spec["repair_stage"] = "Query_Spec"
    return {"final_spec": spec}
