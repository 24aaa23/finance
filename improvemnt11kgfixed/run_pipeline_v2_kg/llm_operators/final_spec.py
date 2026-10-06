"""One compact final-plan format, executed by the existing deterministic engine."""
from copy import deepcopy
import re

from ..common import Any, Dict, LOCAL_MODEL, api_logger, json
from ..clients import build_llm_messages
from ..prompt_boundary import schema_for_prompt, feedback_for_prompt, retrieval_for_prompt
from ..business_context import business_context_prompt
from ..utils import parse_llm_json
from ..spec_contracts import normalize_spec
from ..spec_runtime import compile_spec
from ..query_understanding import final_contract_errors
from ..consultation import consultation_prompt, consultation_request
from ..rdf_contracts import class_key
from ..plan_lineage import field_origins, shared_join_keys, normalize_coalesced_key_expression


PLAN_KEYS = {"final_steps", "merge_steps", "pre_steps", "final_measures", "final_group_by",
             "projection", "final_output", "distinct", "distinct_on", "rounding", "missing_requirements", "assumptions"}


def _branch_context(branches, schema):
    schema = schema_for_prompt(schema)
    profiles, hints = [], []
    owners = {}
    for branch in branches:
        names = {item.get("class") for item in branch.get("retrieval_specs", []) if isinstance(item, dict)}
        source = next(iter(names)) if len(names) == 1 else None
        profile = {key: branch.get(key) for key in ("id", "branch_id", "question", "fields")}
        profile["source_class"] = source
        profile["retrieval_specs"] = [retrieval_for_prompt(item) for item in branch.get("retrieval_specs", []) if isinstance(item, dict)]
        details = schema.get(source, {})
        profile["source_description"] = details.get("description", "")
        profile["documented_derived_metrics"] = details.get("derived_metrics", [])
        if "ontology_metadata" in details:
            profile["ontology_metadata"] = details["ontology_metadata"]
        profile["subject_field"] = details.get("subject_field", "subject_iri")
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
    # SQL-style projection aliases are syntax only; implement an exact field
    # copy so the normal compiler still checks the source and selected dataset.
    projection = normalized.get('projection', [])
    copies = []
    for index, field in enumerate(projection if isinstance(projection, list) else []):
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)', field, re.I) if isinstance(field, str) else None
        if match:
            copies.append((index, *match.groups()))
    if copies and (normalized.get('final_steps') or normalized.get('final_output') or len(branches) == 1):
        used = {step.get('id') for key in ('final_steps', 'merge_steps', 'pre_steps', 'final_measures')
                for step in normalized.get(key, []) if isinstance(step, dict)} | originals
        source = normalized.get('final_output') or 'previous'
        for index, field, alias in copies:
            name = f'projection_alias_{index + 1}'
            while name in used:
                name += '_copy'
            used.add(name)
            normalized.setdefault('final_steps', []).append({'id': name, 'operator': 'Math_Compute',
                'input': source, 'expression': f'column({field!r})', 'output_column': alias})
            projection[index] = alias
            source = name
        normalized['final_output'] = source
    return normalized


def retain_documented_output_aliases(parsed, spec, requirements, branches, schema):
    """Copy a uniquely documented raw field under an interpreted output alias.

    This preserves requested names without treating them as new RDF properties,
    inventing metric aliases, or consulting rows to guess their meaning.
    """
    if spec.get('contract_errors') or any(step.get('stage') == 'combine_terminals'
                                        for step in spec.get('execution_steps', [])):
        return parsed
    projection = list(parsed.get('projection', []))
    available = set(spec.get('dataset_schemas', {}).get(spec.get('compiled_output'), spec.get('compiled_output_schema', [])))
    contract = requirements.get('query_understanding', {})
    metrics = {metric.get('output'): metric for metric in contract.get('metrics', []) if isinstance(metric, dict)}
    output_origins = field_origins(spec, branches).get(spec.get('compiled_output'), {})
    expected = contract.get('required_projection', requirements.get('required_projection', []))
    sources = {class_key(item.get('class'), schema) for branch in branches
               for item in branch.get('retrieval_specs', []) if isinstance(item, dict)}
    aliases = []
    def raw_metric_matches(metric, source, column):
        if not metric:
            return True
        ref = metric['operands'][0]
        if ref == {'table': source, 'column': column['name']}:
            return True
        declared = next((c for c in schema.get(ref['table'], {}).get('columns', [])
                         if isinstance(c, dict) and c.get('name') == ref['column']), {})
        return (column.get('predicate_iri') and column.get('predicate_iri') == declared.get('predicate_iri')
                and column.get('ontology_attribute') == declared.get('ontology_attribute') == metric['output'])
    for alias in expected:
        if alias in available:
            continue
        metric = metrics.get(alias)
        if metric and (metric.get('inner_aggregation') != 'none'
                       or metric.get('outer_aggregation') not in {'none', 'distinct'}
                       or len(metric.get('operands', [])) != 1):
            continue
        matches = {field for source in sources
                   for column in schema.get(source, {}).get('columns', [])
                   if isinstance(column, dict) and column.get('ontology_attribute') == alias
                   for field, origins in output_origins.items()
                   if (source, column.get('name')) in origins and field in available and field != alias
                   and raw_metric_matches(metric, source, column)}
        if len(matches) == 1:
            aliases.append((alias, next(iter(matches))))
    retained = [field for field in expected if contract and field in available and field not in projection]
    if not aliases and not retained:
        return parsed
    result = deepcopy(parsed)
    result['projection'] = list(dict.fromkeys(projection + retained))
    if not aliases:
        return result
    steps = result.setdefault('final_steps', [])
    used = {step.get('id') for key in ('pre_steps', 'merge_steps', 'final_measures', 'final_steps')
            for step in result.get(key, []) if isinstance(step, dict)}
    source = result.get('final_output') or 'previous'
    replacements = {}
    for alias, field in aliases:
        index = 1
        while f'rdf_output_alias_{index}' in used:
            index += 1
        name = f'rdf_output_alias_{index}'
        used.add(name)
        steps.append({'id': name, 'operator': 'Math_Compute', 'input': source,
                      'expression': f'column({field!r})', 'output_column': alias})
        source = name
        replacements[field] = alias
    result['final_output'] = source
    result['projection'] = list(dict.fromkeys([replacements.get(field, field) for field in result['projection']] +
                                              [alias for alias, field in aliases]))
    return result


def align_count_operations(parsed, spec, contract, branches):
    """Implement the contract's precise count kind and raw operand, not a guess.

    A count family spelling is repairable only when its output is an explicitly
    declared count and the requested raw operand survives on that exact input.
    Conditional expressions, sums and unrelated metrics are left to the planner.
    """
    if spec.get('contract_errors'):
        return parsed
    counts = {'count', 'count_rows', 'count_distinct'}
    origins = field_origins(spec, branches)
    result = deepcopy(parsed)
    changed = False
    for key in ('final_steps', 'merge_steps', 'pre_steps', 'final_measures'):
        for parent in result.get(key, []):
            if not isinstance(parent, dict):
                continue
            for measure in parent.get('aggregations', [parent]):
                if measure.get('operation') not in counts:
                    continue
                metric = next((m for m in contract.get('metrics', []) if m.get('output') == measure.get('output_column')), {})
                operation = metric.get('outer_aggregation')
                if operation == 'none':
                    operation = metric.get('inner_aggregation')
                if operation not in counts or operation == measure.get('operation'):
                    continue
                compiled = [s for s in spec.get('execution_steps', []) if s.get('operator') == 'Filter_Aggregate'
                            and s.get('output_column') == measure.get('output_column')]
                if len(compiled) != 1:
                    continue
                source = (compiled[0].get('inputs') or [None])[0]
                refs = metric.get('operands', [])
                if operation == 'count_rows':
                    target = '*'
                elif len(refs) == 1:
                    ref = refs[0]
                    candidates = [field for field, values in origins.get(source, {}).items()
                                  if (ref.get('table'), ref.get('column')) in values]
                    if len(candidates) != 1:
                        continue
                    target = candidates[0]
                else:
                    continue
                measure['operation'] = operation
                for target_key in ('column', 'target_column'):
                    measure.pop(target_key, None)
                measure['input_column'] = target
                changed = True
    return result if changed else parsed


def repair_shared_key_expressions(parsed, spec):
    merged = shared_join_keys(spec)
    result = deepcopy(parsed)
    changed = False
    for key in ('final_steps', 'pre_steps', 'merge_steps', 'final_measures'):
        for step in result.get(key, []):
            if not isinstance(step, dict) or step.get('operator') != 'Math_Compute' or not step.get('expression'):
                continue
            candidates = [s for s in spec.get('execution_steps', [])
                          if s.get('operator') == 'Math_Compute' and s.get('output_column') == step.get('output_column')
                          and s.get('expression') == step['expression']]
            if len(candidates) != 1:
                continue
            source = (candidates[0].get('inputs') or [None])[0]
            expression = normalize_coalesced_key_expression(step['expression'],
                spec.get('dataset_schemas', {}).get(source, []), merged.get(source, {}))
            if expression != step['expression']:
                step['expression'] = expression
                changed = True
    return result if changed else parsed


def retain_required_ordering(parsed, spec, contract):
    """Add an omitted declared sort; never sort after an earlier truncation."""
    terms = contract.get('order_by', [])
    if (not terms or spec.get('contract_errors') or any(s.get('operator') == 'Order_By'
            or s.get('stage') == 'combine_terminals' for s in spec.get('execution_steps', []))):
        return parsed
    fields = spec.get('dataset_schemas', {}).get(spec.get('compiled_output'), [])
    if any(term.get('column') not in fields for term in terms):
        return parsed
    result = deepcopy(parsed)
    used = {step.get('id') for key in ('final_steps', 'merge_steps', 'pre_steps', 'final_measures')
            for step in result.get(key, []) if isinstance(step, dict)} | set(spec.get('dataset_schemas', {}))
    name = 'required_order'
    while name in used:
        name += '_last'
    step = {'id': name, 'operator': 'Order_By', 'input': result.get('final_output') or 'previous',
            'order_by': deepcopy(terms)}
    if contract.get('limit') is not None:
        step['limit'] = contract['limit']
    result.setdefault('final_steps', []).append(step)
    result['final_output'] = name
    return result


def semantic_build_final_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    query = inputs.get("original_query", inputs.get("query", ""))
    branches = inputs.get("processed_datasets", [])
    profiles, joins = _branch_context(branches, inputs.get("global_schema", {}))
    requirements = inputs.get("answer_requirements") or inputs.get("decomposition", {}).get("answer_requirements", {})
    source_contract = {key: requirements.get(key, []) for key in ("predicates", "joins", "calculation_notes", "metrics", "group_by", "required_projection", "order_by", "query_understanding")}
    previous = {key: value for key, value in inputs.get("previous_final_spec", {}).items() if key in PLAN_KEYS}
    declared_errors = []
    if previous:
        checked = compile_spec(previous, {str(branch['id']): branch.get('fields', []) for branch in branches})
        declared_errors = checked['contract_errors'] + final_contract_errors(checked, requirements.get('query_understanding', {}), branches, inputs.get('global_schema', {}))
    business_context = business_context_prompt()
    prompt = f"""Return one JSON calculation plan answering the question from the available tables.
A table is a list of retrieved records. A step applies one operation and names its
result so later steps can use it. Python executes these steps; do not write SPARQL.
Retrieval and Scan are ALREADY complete. Use existing branch IDs as step inputs.
Do not emit Scan, Retrieve, Copy, SPARQL, or source_class steps. Do not recreate tables.
Supported calculation operators are Integrate, Filter_Aggregate, Math_Compute,
Order_By, Date_Extract, Bucket, Set_Intersect, Set_Difference, Set_Union, Distinct.

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
  Calculate paired differences before averaging: AVG(after-before) differs from
  AVG(after)-AVG(before) when operands have different nulls. Preserve direction.
  Request missing raw operands instead of substituting an available metric.

Business rule pack, authoritative for metric definitions, formula precedence, signs, weighting, nulls, ranking tie-breaks and populations: {business_context}
Question: {query}
Available branch definitions, relevant supplied ontology metadata and retrieval contracts (no live Scan samples or statistics): {json.dumps(profiles, default=str)}
Schema relationship join options: {json.dumps(joins)}
Declared source conditions and connections (branch_id maps to each table above): {json.dumps(source_contract, default=str)}
Repair errors, if any: {feedback_for_prompt(inputs.get('spec_feedback', ''))}
Previous plan, if any: {json.dumps(previous, default=str)}
Local checks of the previous DECLARATIONS against the declared schemas and question contract
(these checks never execute the plan or read rows): {json.dumps(declared_errors)}

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
  Equal-name join keys have ONE coalesced output column, including outer joins.
  They do not get a second _right column. Use that key directly for unmatched
  records from either side; do not reference a nonexistent key_right.
  Use inner join when both sides must participate (entities with BOTH types of
  required related records). Use left join to preserve a requested base population when related
  facts or labels are optional. A missing related metric remains null unless the
  question defines a default. Do not discard a base entity just because a label is missing.
  Declare cardinality:"many_to_one" for lookup joins, "one_to_one" for entity
  summaries, or "one_to_many"/"many_to_many" when intentional. Local execution
  validates this declaration. Infer no cardinality or uniqueness from instance
  counts or values; only declared schema constraints and requested grain apply.
  A reference does not make its source field unique. A raw fact class can have
  many records for one entity. Declare a unique side only when a declared unique
  constraint, the RDF subject identity, or a prior group_by/distinct step guarantees
  those exact join keys. Multi-valued RDF properties can expand one subject into
  several rows; subject identity alone does not guarantee a unique retrieved side.
  Otherwise omit cardinality; preserve multiplicity and the requested metric grain.
  Never fix multiplicity by dropping arbitrary records or changing the question.
  Ordinary joins do not match null keys. To merge already aggregated groups from
  the SAME population and grouping, explicitly set nulls_equal:true; otherwise
  an outer join creates two incomplete null groups. Do not enable it on entity IDs.
- Aggregate: {{"id":"totals","operator":"Filter_Aggregate","input":"joined",
  "group_by":["category"],"aggregations":[
  {{"operation":"count_rows","input_column":"*","output_column":"n"}},
  {{"operation":"sum","input_column":"amount","output_column":"total"}}]}}
  Operations: count_rows, count (non-null), count_distinct, sum, avg, min, max.
  The interpreted operation is exact: count(column) excludes nulls; count_rows
  counts all input rows; count_distinct also removes duplicates. Do not substitute
  one for another. Conditional count: calculate where(condition, 1, null), then
  count that column. Its group count is zero when no input row meets the condition.
  Preserve the resolved metric's outer operation and final grouping, including
  calculated grouping aliases. Do not replace count_distinct with SUM of counts
  unless disjoint populations and an equivalent calculation are explicitly defined.
  All metrics in this list use the same original input. Output contains group keys and metrics.
  input_column must be an existing column, not an expression. Calculate conditional
  values with separate Math_Compute steps first, then aggregate their output columns.
- Filter: {{"operator":"Filter_Aggregate","operation":"filter",
  "filters":[{{"field":"total","operator":">","value":10}}]}}
- Copy/rename a field: {{"operator":"Math_Compute","expression":"column('category_name')",
  "output_column":"category"}}. Text copies are allowed; do not sum/average text labels.
- Formula: {{"operator":"Math_Compute","expression":"total / nullif(n, 0)","output_column":"average"}}.
  Each Math_Compute step has ONE expression and ONE output_column. For several
  formulas use separate steps, each consuming the preceding result; no expressions list.
  Use where(condition, true_value, false_value) for conditional formulas. For
  several conditions nest where() calls, or use Bucket with explicit boundaries.
  Do not emit SQL CASE WHEN syntax in the calculation plan.
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
- Distinct: {{"operator":"Distinct","input":"existing dataset","distinct_on":["label"]}}.
  For a list of distinct labels, use Distinct and projection, without an unrequested
  count aggregate. Distinctness and count_distinct are different output operations.

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
Keep the interpreted grouping dimensions exact. Do not add a lookup label as an
extra group merely to project it. Aggregate facts at the requested identity grain
before attaching optional display labels, and preserve the required population.
If the question's required calculated band/count dimension is missing from its
interpretation, request query_understanding advice on aggregation_grain instead
of repeatedly emitting a plan that contradicts that interpretation.
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
    repaired = repair_shared_key_expressions(parsed, spec)
    if repaired is not parsed:
        parsed = repaired
        spec = compile_spec(parsed, {str(branch['id']): branch.get('fields', []) for branch in branches})
    counted = align_count_operations(parsed, spec, requirements.get('query_understanding', {}), branches)
    if counted is not parsed:
        parsed = counted
        spec = compile_spec(parsed, {str(branch['id']): branch.get('fields', []) for branch in branches})
    aliased = retain_documented_output_aliases(parsed, spec, requirements, branches, inputs.get('global_schema', {}))
    if aliased is not parsed:
        parsed = aliased
        spec = compile_spec(parsed, {str(branch["id"]): branch.get("fields", []) for branch in branches})
    ordered = retain_required_ordering(parsed, spec, requirements.get('query_understanding', {}))
    if ordered is not parsed:
        parsed = ordered
        spec = compile_spec(parsed, {str(branch['id']): branch.get('fields', []) for branch in branches})
    spec["response_diagnostics"] = diagnostics
    if inputs.get("contract_checks", True):
        spec["contract_errors"].extend(final_contract_errors(spec, requirements.get("query_understanding", {}), branches, inputs.get('global_schema', {})))
    if parsed.get("missing_requirements"):
        spec["contract_errors"].append("Missing retrieval: " + json.dumps(parsed["missing_requirements"]))
        spec["repair_stage"] = "Query_Spec"
    return {"final_spec": spec}
