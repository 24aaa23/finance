"""Apply the reviewed prompt-only simplification to V4 (no model calls)."""
import ast
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "run_pipeline_v4"
stats = {}


def replace_prompt(name, prompt):
    path = SOURCE / "llm_operators" / name
    text = path.read_text(encoding="utf-8")
    start = text.index('    prompt = f"""')
    end = text.index('"""', start + len('    prompt = f"""')) + 3
    old = text[start:end]
    replacement = '    prompt = f"""\n' + prompt.strip() + '\n"""'
    updated = text[:start] + replacement + text[end:]
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")
    stats[name] = {"template_words_before": len(old.split()), "template_words_after": len(replacement.split())}


replace_prompt("decompose.py", '''
Split the question into small raw-data retrieval tasks.
A source class is a type of record in the schema. A branch is one task that reads
one source class. Later code retrieves its fields and calculates the final answer.
Your job here is to choose sources, preserve conditions, and describe connections.

Question: {query}
Suggested classes: {retrieved_tables}
Schema: {json.dumps(schema_details)}
Repair feedback: {decomposition_feedback}

Rules:
- Use one branch for a simple lookup. Add branches only for needed sources or
  separate conditions. Each branch reads independently, without waiting for IDs.
- Use exact schema names. Include a connecting source when facts need it; a
  category record is not a person record. Similar labels do not prove a connection.
- Preserve exact values, comparisons, dates, AND/OR, and absence conditions in
  branch questions. Do not add non-null filters just to make calculation easier.
- Retrieve raw records. Leave sums, averages, ranking, formulas, and final output
  names to the later calculation step. Describe those needs in the branch question.
- Include record identity and the fields needed to link the selected sources.
  An IRI is a full resource identifier. Join keys must identify the same kind of
  entity; do not match an IRI to a short literal ID or a display label.
- Do not write SPARQL, execution steps, metric definitions, or alternative plans.

Return one JSON object. These fields mean:
subquestions: the retrieval branches; id: unique branch name; question: its task;
source_class: exact schema class; retrieval_grain: fields identifying one raw record;
requirement_ids: IDs of conditions assigned to this branch.
answer_requirements: shared conditions and connections, not a calculation plan.
predicates: explicit conditions; stage is scan for a raw-field condition or final
for a condition on a calculated value. branch_ids identifies the responsible tasks.
joins: known connections; left_on/right_on are the actual fields on those branches.
Use empty lists when none apply; do not invent missing schema fields.

{{"selected_decomposition": {{
  "subquestions": [{{"id":"q1", "question":"raw records and conditions needed",
    "source_class":"exact schema class", "retrieval_grain":["record key"],
    "requirement_ids":[]}}],
  "answer_requirements": {{
    "predicates": [],
    "joins": []
  }}
}}}}
Condition shape: {{"id":"p1", "source_class":"exact schema class",
 "field":"exact field", "operator":"=", "value":"exact literal",
 "stage":"scan", "branch_ids":["q1"]}}
Connection shape: {{"left_branch":"q1", "right_branch":"q2",
 "left_on":["reference field"], "right_on":["matching identity field"]}}
''')

replace_prompt("query_spec.py", '''
Describe the raw records to retrieve for one branch.
A retrieval specification (called Query_Spec in code) is JSON naming one source
class, selected fields, record identity, optional fields, and raw-field filters.
It does not contain calculations or a database query.

Original question: {original_query}
Active branch: {json.dumps(subquestion)}
Shared conditions and connections: {json.dumps({key: decomposition.get('answer_requirements', {}).get(key, []) for key in ('predicates', 'joins')})}
Schema: {json.dumps(schema_details)}
Repair feedback: {spec_feedback}

Rules:
- Use the branch's assigned source class and exact local field names from schema.
  The original question remains authoritative; preserve its conditions and meaning.
- fields lists every raw value needed for calculation, display, filtering, and
  joining. Include the complete identity and linking keys, even if not displayed.
- entity_key identifies a raw record. Prefer schema subject_field, the RDF subject
  itself. A link to another entity is not the identity of this record.
- optional_fields is the subset of fields that may be missing. Keep measures,
  display values, and grouping values optional unless an explicit condition needs
  them present. Missing one measure must not remove rows needed by another measure.
- filters contains only requested raw-field conditions. Preserve literal values,
  boundaries, AND/OR and negation scope. Use equality for exact categories, contains
  only for requested substrings, and is_null/is_not_null for missing/present values.
  A condition on a sum/average belongs in the final calculation. Absence of related
  records needs a separate exclusion branch, not a raw not-equal filter.
- Use typed values: number, date, string, list, or null. Do not label a date as a
  string merely because its JSON representation is text.
- Match links to the same entity type and key representation. Do not substitute
  a display label or require a field owned by another source on this source.
- Return exactly one retrieval_specs entry; no formulas, totals, sorting or limits.

Return only JSON. id names the retrieval; class names the source; filters use
field/operator/value/value_type; output_schema repeats the selected field names.
{{"id":"branch id", "retrieval_specs":[{{
 "id":"branch id", "class":"exact source class", "entity_key":["record key"],
 "fields":["record key","needed field"], "optional_fields":["needed field"],
 "filters":[], "purpose":"what this source contributes"
}}], "output_schema":["record key","needed field"]}}
Filter example: {{"field":"exact field", "operator":">", "value":10, "value_type":"number"}}
Supported operators: =, !=, >, <, >=, <=, between, in, not_in, contains, is_null, is_not_null.
''')

replace_prompt("generate.py", '''
Write one raw SPARQL SELECT from the retrieval specification below.
The specification defines one source class, selected fields, identity keys,
optional fields (which may be missing), and filters. Implement it without changing
the requested population. Later Python operators calculate the answer.

Original question: {inputs.get('original_query', inputs.get('query'))}
Retrieval specification: {json.dumps(active_retrieval_spec)}
Schema: {json.dumps(pruned_schema)}
Previous query, if repairing: {failed_sparql if logic_feedback else ''}
Repair feedback: {logic_feedback}

Rules:
- Use exact class_iri and predicate_iri values in the schema. Full <IRI> syntax is
  allowed; declare any prefixes you use. An IRI is a full RDF resource identifier.
- Anchor the subject with rdf:type. The schema's subject_field names this subject
  variable, not a predicate. Select every declared field with its exact alias.
- Bind ordinary fields through their listed predicates. A label_field is a display
  value, not an identity key. Do not invent properties or replace fields by labels.
- Wrap each optional_fields binding in OPTIONAL, including the full path if it
  retrieves a label. Do not also require the same binding outside OPTIONAL.
- Apply every declared filter with its exact values and boundaries. Preserve
  AND/OR/NOT scope. Equality is not substring matching. is_null tests an unbound
  value; is_not_null tests a bound value. Other missing values remain unbound.
- Match numeric/date comparison literals to the RDF datatype. Cast in the filter
  only when necessary; preserve raw selected values. Never compare an RDF date
  with an xsd:string boundary. Preserve the requested date interval.
- Return raw records with identity and linking fields. No aggregates, formulas,
  GROUP BY, ORDER BY, LIMIT, DISTINCT, or nested calculation queries. Do not add
  another source, weaken a condition, or omit a field to make execution easier.

Return raw SPARQL only, beginning with PREFIX or SELECT. No prose or code fences.
''')

replace_prompt("refine.py", '''
Repair the failed raw SPARQL SELECT without changing its meaning.
The retrieval specification is JSON defining the source class, selected fields,
record identity, optional fields, and filters. Preserve all of these during repair.

Question: {inputs.get('query')}
Retrieval specification: {json.dumps(inputs.get('query_spec', {}).get('retrieval_specs', []))}
Failed SPARQL: {inputs.get('failed_sparql')}
Database error: {inputs.get('error_message')}
Repair feedback: {inputs.get('logic_feedback', '')}
Schema: {json.dumps(schema_details)}

- Use the exact schema class_iri and predicate_iri values. An IRI is a full RDF
  resource identifier. Declare used prefixes or write full <IRI> values.
- Bind the typed subject itself for subject_field, not a property with that name.
- Select every required field using its declared alias. Keep optional bindings
  OPTIONAL; preserve raw duplicates and missing values.
- Preserve every filter's value, operator, AND/OR/NOT scope, and date boundary.
  Use numeric/date literals compatible with the RDF field datatype. Do not
  compare dates to strings or change equality to substring matching.
- Fix syntax or invalid schema terms using the supplied evidence. A timeout does
  not authorize dropping a source or condition. Do not answer an easier question.
- Retrieve raw records only: no aggregates, formulas, GROUP BY, ORDER BY, LIMIT,
  DISTINCT, or calculation subqueries. This rule applies even with no operator_plan.

Return the corrected SPARQL only, starting with PREFIX or SELECT. No code fences.
''')

replace_prompt("retrieve.py", '''
Select the schema classes needed to answer the question.
A class is a type of record. The index lists each class and its available fields.
Include sources needed for conditions, returned values, and connections between
records. A category/label source does not replace the entity that owns that label.

Question: {inputs.get('query')}
Class index: {json.dumps(table_index)}

Return only a JSON array of exact class names from this index, for example
["exact class name from the index"]. Do not invent names or return an object.
''')

replace_prompt("explain.py", '''
Answer the question using only the supplied result rows.
Question: {query}
Total result rows: {row_count}
Visible rows: {json.dumps(data_sample, ensure_ascii=False)}

Preserve names, IDs, missing values, and numbers exactly. Do not calculate new
values or infer unseen rows. If the visible rows are only a sample, say so.
Return a concise answer with no reasoning tags or code fences.
''')

# Remove redundant schema/spec expansions from Generate; the active retrieval and
# one complete schema slice are already included in its replacement prompt.
path = SOURCE / "llm_operators/generate.py"
text = path.read_text(encoding="utf-8")
text = text.replace("from ..utils import build_schema_generation_rules, repair_sparql_for_query", "from ..utils import repair_sparql_for_query")
text = text.replace("    schema_generation_rules = build_schema_generation_rules(pruned_schema)\n", "")
start = text.index('    query_spec_context = ""')
end = text.index('    prompt = f"""', start)
text = text[:start] + text[end:]
ast.parse(text)
path.write_text(text, encoding="utf-8")

(Path(__file__).resolve().parent / "prompt_simplification.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
