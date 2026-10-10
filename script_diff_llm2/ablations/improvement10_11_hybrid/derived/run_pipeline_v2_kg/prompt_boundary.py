"""Allow only declared schema and plan contracts in model-facing context.

Instance rows, populations, distributions and execution-error text stay local.
Question literals and explicitly supplied ontology/domain/rule definitions remain
authorized context; they must never be derived from execution samples.
"""
import json
from .knowledge import planning_schema


def schema_for_prompt(schema):
    normalized = {name: {**details, "columns": [column if isinstance(column, dict) else {"name": column}
                                                for column in details.get("columns", [])]}
                  for name, details in (schema or {}).items()}
    return planning_schema(normalized)


def index_for_prompt(index):
    return {name: schema_for_prompt({name: value})[name] if isinstance(value, dict) else
            [field for field in value if isinstance(field, str)] if isinstance(value, (list, tuple)) else []
            for name, value in (index or {}).items()}


def retrieval_for_prompt(retrieval):
    return {key: value for key, value in retrieval.items()
            if key in {"id", "class", "entity_key", "fields", "optional_fields", "filters", "purpose"}}


def _error_category(error):
    text = str(error).lower()
    if any(word in text for word in ("column", "field", "schema", "projection", "source")):
        return "schema_reference_error"
    if any(word in text for word in ("join", "cardinality", "multiplicity", "key")):
        return "join_contract_error"
    if any(word in text for word in ("numeric", "division", "zero", "finite", "calculation")):
        return "calculation_error"
    if any(word in text for word in ("json", "syntax", "format")):
        return "plan_format_error"
    return "plan_contract_error"


def feedback_for_prompt(value):
    """Forward error categories and declared schemas, never raw runtime messages."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            value = {"errors": [value]}
    if not isinstance(value, dict):
        value = {"errors": [value]}
    safe = {key: value[key] for key in ("stage", "attempt") if key in value}
    safe["errors"] = list(dict.fromkeys(_error_category(error) for error in value.get("errors", [])))
    if any('invalid expression' in str(error).lower() for error in value.get('errors', [])):
        safe['expression_guidance'] = ('Use the documented expression functions and exact input fields. '
            'Use where(condition, true_value, false_value) or Bucket for conditional results; '
            'use separate Math_Compute steps for separate outputs. No SQL statements or attribute access.')
    if any('competing scan equalities' in str(error).lower() for error in value.get('errors', [])):
        safe['predicate_scope_guidance'] = ('Scan conditions on one branch are AND. '
            'Metric-specific category conditions belong in final conditional calculations or separate branches. '
            'Use one IN predicate only when the question requires the union of alternatives. Preserve all literals and population.')
    if any('unique join keys' in str(error).lower() for error in value.get('errors', [])):
        safe['cardinality_guidance'] = ('A reference field does not guarantee source uniqueness. '
            'Declare cardinality/validate only when those exact keys have a declared unique constraint '
            'or an earlier group_by/distinct guarantees uniqueness. Otherwise correct the assertion '
            'or summarize at the question\'s declared metric grain. Preserve multiplicity; never drop arbitrary records.')
    safe["failed_steps"] = [{key: step[key] for key in ("step", "operator", "code", "inputs", "input_schemas") if key in step}
                            for step in value.get("failed_steps", []) if isinstance(step, dict)]
    for key in ("available_schemas", "step_ids"):
        if key in value:
            safe[key] = value[key]
    if isinstance(value.get("source_schema"), dict):
        safe["source_schema"] = schema_for_prompt(value["source_schema"])
    safe["hint"] = "Repair the declared plan using the question, schema and prior plan. Execution values are unavailable."
    return json.dumps(safe, ensure_ascii=True)
