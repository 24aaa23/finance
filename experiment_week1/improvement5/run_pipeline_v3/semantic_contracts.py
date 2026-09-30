"""Schema-backed semantic checks; never infer a repair from a question ID."""
import ast

from .connections import _columns, _entity_type
from .relational import join_column_maps
from .spec_contracts import flatten_identifiers


def _aggregate_name(value):
    return {"mean": "avg", "average": "avg", "nunique": "count_distinct"}.get(value, value)


def requirement_shape_errors(requirements):
    """Reject malformed model metadata before it can crash semantic checks."""
    if not isinstance(requirements, dict):
        return ["Answer requirements must be an object."]
    errors = []
    metrics = requirements.get("metrics", [])
    if not isinstance(metrics, list) or any(not isinstance(m, dict) for m in metrics):
        errors.append("Metrics must be a list of objects.")
        metrics = []
    terms = list(metrics)
    for metric in metrics:
        components = metric.get("components", [])
        if not isinstance(components, list) or any(not isinstance(c, dict) for c in components):
            errors.append("Metric components must be a list of source-term contracts.")
        else:
            terms.extend(components)
    for term in terms:
        operands = term.get("operand_fields", [])
        if not isinstance(operands, list) or any(not isinstance(f, str) or not f for f in operands):
            errors.append("Metric operand_fields must be a list of field names, not a string or NULL.")
        for key in ("output_column", "source_class", "entity_key", "group_owner", "inner_aggregation", "outer_aggregation"):
            if term.get(key) is not None and not isinstance(term[key], str):
                errors.append(f"Metric {key} must be a field/class/operation name, not an object or list.")
        for key in ("inner_aggregation", "outer_aggregation"):
            value = term.get(key)
            if isinstance(value, str) and _aggregate_name(value) not in {"", "none", "sum", "avg", "min", "max", "count", "count_rows", "count_distinct"}:
                errors.append(f"Metric {key} must be an operation such as sum or avg; put expressions in formula.")
    policy = requirements.get("null_policy", {})
    if not isinstance(policy, dict):
        errors.append("null_policy must be an object.")
    else:
        labels = policy.get("label_groups", [])
        if not isinstance(labels, list):
            errors.append("null_policy.label_groups must be a list.")
        else:
            for label in labels:
                if (not isinstance(label, dict) or not isinstance(label.get("field"), str)
                        or not label["field"] or not isinstance(label.get("policy"), str)
                        or label["policy"] not in {"keep", "exclude"}):
                    errors.append("Each label_groups entry needs a field name and policy keep or exclude.")
    return list(dict.fromkeys(errors))


def metric_source_errors(requirements, schema, sources):
    """Check declared metric sources before asking a later stage to use them."""
    errors = requirement_shape_errors(requirements)
    if errors:
        return errors
    for metric in requirements.get("metrics", []):
        if not metric.get("output_column"):
            continue
        if not {"source_class", "components", "operand_fields", "entity_key", "inner_aggregation",
                "outer_aggregation", "group_owner"}.intersection(metric):
            continue  # Legacy output-only metadata declares no source contract.
        output = metric["output_column"]
        components = metric.get("components", [])
        source = metric.get("source_class")
        if not source and not components:
            errors.append(f"Metric {output} needs a source_class or explicit source components.")
        if not source and components and metric.get("operand_fields"):
            errors.append(f"Metric {output}: put operands in their source components, not on a source-less formula.")
        terms = ([metric] if source else []) + components
        for term in terms:
            owner = term.get("source_class")
            if not owner or (schema and owner not in schema):
                errors.append(f"Metric {output} has an unknown source_class: {owner!r}.")
                continue
            if owner not in sources:
                errors.append(f"Metric {output} needs a retrieval branch for source {owner}.")
            if schema:
                details = schema[owner]
                fields = set(_columns(details)) | {details.get("subject_field")}
                needed = set(term.get("operand_fields", [])) | ({term["entity_key"]} if term.get("entity_key") else set())
                missing = needed - fields
                if missing:
                    errors.append(f"Metric {output} requests unknown fields on {owner}: {sorted(missing)}.")
        owner = metric.get("group_owner")
        if owner and ((schema and owner not in schema) or owner not in sources):
            errors.append(f"Metric {output} declares group_owner {owner}, but no such group source is retrieved. "
                          "Use the source of the grouping field, including the input of a derived band, "
                          "or retrieve the required group source and connector.")
    return list(dict.fromkeys(errors))


def _required_filters(filters):
    """Only conjunctive presence tests establish a guaranteed non-null value."""
    for condition in filters if isinstance(filters, list) else []:
        if not isinstance(condition, dict):
            continue
        if "all" in condition:
            yield from _required_filters(condition["all"])
        elif not any(key in condition for key in ("any", "not")):
            yield condition


def _nonnull_fields(filters):
    return {c.get("field") or c.get("column") or c.get("target_column")
            for c in _required_filters(filters)
            if str(c.get("operator", "")).strip().lower().replace(" ", "_") == "is_not_null"}


def predicate_errors(predicates, *, check_contradictions=True):
    """Check conjunctive scalar bindings, keeping OR branches independent."""
    errors, equalities, allowed_values = [], {}, {}
    if not isinstance(predicates, list):
        return ["Predicates must be a list."]
    conjunction = []
    for predicate in predicates:
        if not isinstance(predicate, dict):
            continue
        if "all" in predicate:
            conjunction.extend(predicate["all"] if isinstance(predicate["all"], list) else [])
        else:
            conjunction.append(predicate)
    # Flatten nested ANDs before checking their shared binding.
    if any("all" in item for item in conjunction if isinstance(item, dict)):
        return predicate_errors(conjunction, check_contradictions=check_contradictions)
    for predicate in conjunction:
        if not isinstance(predicate, dict):
            continue
        if "any" in predicate:
            for child in predicate["any"] if isinstance(predicate["any"], list) else []:
                errors.extend(predicate_errors([child], check_contradictions=False))
            continue
        if "not" in predicate:
            errors.extend(predicate_errors([predicate["not"]], check_contradictions=False))
            continue
        field = predicate.get("field") or predicate.get("column") or predicate.get("target_column")
        op = str(predicate.get("operator", "=")).lower()
        if predicate.get("value") is None and op in {"=", "==", "eq", "equals", "!=", "<>", "ne", "<", ">", "<=", ">="}:
            errors.append(f"{field}: comparison with NULL is not a presence test; use is_null/is_not_null.")
        if op in {"=", "==", "eq", "equals"} and predicate.get("value") is not None:
            value = predicate["value"]
            if check_contradictions and field in equalities and value != equalities[field]:
                errors.append(f"Contradictory equalities on {field}: {equalities[field]!r} AND {value!r}. "
                              "For comparison alternatives use one IN predicate or separate branches; do not change a genuine AND silently.")
            equalities[field] = value
        if check_contradictions and (op in {"=", "==", "eq", "equals", "in"}):
            values = predicate.get("value")
            values = values if op == "in" and isinstance(values, list) else [values] if op != "in" else None
            if values is not None:
                if field in allowed_values:
                    values = [value for value in values if value in allowed_values[field]]
                    if not values:
                        errors.append(f"Contradictory allowed values on {field}. "
                                      "Metric-specific cases/bands belong in final calculations or separate branches, "
                                      "not conjunctive scan filters.")
                allowed_values[field] = values
    return list(dict.fromkeys(errors))


def decomposition_predicate_errors(requirements, branches):
    errors = []
    for branch in branches:
        predicates = [p for p in requirements.get("predicates", [])
                      if p.get("stage", "scan") == "scan"
                      and p.get("source_class") == branch.get("source_class")
                      and (not p.get("branch_ids") or branch["id"] in flatten_identifiers(p["branch_ids"]))]
        errors.extend(f"Branch {branch['id']}: {error}" for error in predicate_errors(predicates))
    return errors


def final_semantic_errors(spec, profiles, schema, requirements):
    """Follow column origins through compiled operations, including join suffixes.

    Check proven identity mismatches and declared aggregate contracts. Unknown
    metadata is left for semantic review rather than guessed from column names.
    """
    from .non_llm_operators.math_compute import expression_columns
    shape_errors = requirement_shape_errors(requirements)
    if shape_errors:
        return shape_errors
    datasets, errors = {}, []
    for profile in profiles:
        source = profile.get("source_class")
        details = schema.get(source, {})
        columns = _columns(details)
        present = set().union(*(_nonnull_fields(r.get("filters", [])) for r in profile.get("retrieval_specs", [])
                               if isinstance(r, dict)))
        datasets[profile["id"]] = {
            field: {"origins": {(source, field)}, "types": {_entity_type(source, field, details, columns)} - {None}
                    if field in columns else set(), "aggregates": [], "nonnull": field in present}
            for field in profile.get("fields", [])
        }

    def combined(values):
        return {"origins": set().union(*(v["origins"] for v in values)), "types": set(),
                "aggregates": [a for v in values for a in v["aggregates"]], "nonnull": False}

    for step in spec.get("execution_steps", []):
        inputs = [datasets.get(name, {}) for name in step["inputs"]]
        if not inputs:
            continue
        current = {field: dict(meta) for field, meta in inputs[0].items()}
        op = step["operator"]
        if op == "Integrate":
            left = flatten_identifiers(step.get("left_on") or step.get("join_key"))
            right = flatten_identifiers(step.get("right_on") or step.get("join_key"))
            for other in inputs[1:]:
                for lkey, rkey in zip(left, right):
                    ltypes, rtypes = current.get(lkey, {}).get("types", set()), other.get(rkey, {}).get("types", set())
                    if ltypes and rtypes and ltypes.isdisjoint(rtypes):
                        errors.append(f"Join {lkey} -> {rkey} identifies different entity classes: {sorted(ltypes)} vs {sorted(rtypes)}. Retrieve the correct connector.")
                    if step.get("nulls_equal") and (ltypes or rtypes) and not str(step.get("stage", "")).startswith("combine_"):
                        errors.append("nulls_equal must not match missing entity identities; reserve it for aggregated display groups.")
                lm, rm, _ = join_column_maps(list(current), list(other), left, right, step.get("suffixes", ["", "_right"]))
                how = step.get("join_type", "inner")
                left_present = {lm[k] for k, v in current.items() if v["nonnull"]}
                right_present = {rm[k] for k, v in other.items() if v["nonnull"]}
                guaranteed = (left_present if how == "left" else right_present if how == "right"
                              else left_present & right_present if how == "outer" else left_present | right_present)
                merged = {lm[k]: v for k, v in current.items()}
                for key, value in other.items():
                    name = rm[key]
                    if name in merged:
                        prior = merged[name]
                        merged[name] = {**prior, "origins": prior["origins"] | value["origins"],
                                        "types": prior["types"] | value["types"]}
                    else:
                        merged[name] = value
                current = {k: {**v, "nonnull": k in guaranteed} for k, v in merged.items()}
        elif op == "Combine_Scalars":
            current = {k: v for table in inputs for k, v in table.items()}
        elif op == "Copy":
            current = {field: current[field] for field in step.get("output_columns", current) if field in current}
        elif op in {"Set_Union", "Union"}:
            current = {field: combined([table[field] for table in inputs if field in table])
                       for field in set().union(*(set(table) for table in inputs))}
        elif op == "Filter_Aggregate":
            for field in _nonnull_fields(step.get("filters", [])):
                if field in current:
                    current[field] = {**current[field], "nonnull": True}
            if step.get("operation") not in {"filter", "where"}:
                groups = flatten_identifiers(step.get("group_by"))
                target = step.get("target_column")
                value = combined([current[target]]) if target in current else combined([])
                if target == "*":
                    # COUNT(*) measures input rows, so retain their source without
                    # pretending the count consumes every numeric column.
                    value["origins"] = set().union(*(v["origins"] for v in current.values()))
                value["aggregates"].append({"operation": step["operation"],
                    "group_origins": set().union(*(current[g]["origins"] for g in groups if g in current)),
                    "input_origins": value["origins"]})
                current = {**{g: current[g] for g in groups if g in current}, step["output_column"]: value}
        elif op in {"Math_Compute", "Date_Extract", "Bucket"}:
            expression = step.get("expression")
            fields = expression_columns(expression) if expression else flatten_identifiers(
                [step.get("input_column"), step.get("left_column"), step.get("right_column"), step.get("target_column"), step.get("base_col")])
            values = [current[f] for f in fields if f in current]
            value = combined(values)
            # Identity and label-presence metadata survive a plain copy only.
            if expression:
                tree = ast.parse(expression, mode="eval").body
                if len(values) == 1 and (isinstance(tree, ast.Name) or
                    isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name) and tree.func.id == "column"):
                    value = dict(values[0])
            current[step["output_column"]] = value
        elif op == "Order_By" and step.get("limit") is not None:
            for policy in requirements.get("null_policy", {}).get("label_groups", []):
                if isinstance(policy, dict) and policy.get("policy") == "exclude":
                    field = policy.get("field")
                    if field in current and not current[field]["nonnull"]:
                        errors.append(f"Label {field} must be filtered before ranking/limit, not afterwards.")
        datasets[step["output"]] = current

    final = datasets.get(spec.get("compiled_output"), {})

    def matches_inner(aggregate, operation, source, entity, operands):
        raw_identity = schema.get(source, {}).get("subject_field")
        still_raw = raw_identity and raw_identity != entity and (source, raw_identity) in aggregate["group_origins"]
        return (not still_raw and aggregate["operation"] == operation
                and (source, entity) in aggregate["group_origins"] and operands <= aggregate["input_origins"])

    for metric in requirements.get("metrics", []):
        output = metric.get("output_column")
        if not output:  # Legacy metadata is still shown to the reviewer.
            continue
        value = final.get(output)
        if value is None:
            errors.append(f"Required metric {output} is missing from final data. "
                          "If this is only an intermediate calculation, repair Decompose: describe it "
                          "inside the final metric's components/calculation_notes, not as a requested output.")
            continue
        aggregates = value["aggregates"]
        outer = _aggregate_name(metric.get("outer_aggregation"))
        earlier = aggregates[:-1] if outer and outer != "none" else aggregates
        for component in metric.get("components", []):
            source = component.get("source_class")
            operands = {(source, field) for field in component.get("operand_fields", [])}
            if not operands <= value["origins"]:
                errors.append(f"Metric {output} is missing component operands from {source}. "
                              "Components must describe formula values; grouping/filter-only fields "
                              "belong in group_by, predicates, joins and population instead.")
            operation, entity = _aggregate_name(component.get("inner_aggregation")), component.get("entity_key")
            if operation and operation != "none" and entity and not any(
                matches_inner(a, operation, source, entity, operands) for a in earlier
            ):
                errors.append(f"Metric {output} requires component {operation} per {source}.{entity}.")
        source = metric.get("source_class")
        operands = {(source, field) for field in metric.get("operand_fields", [])}
        if (source or operands) and not operands <= value["origins"]:
            errors.append(f"Metric {output} uses the wrong source/operands; required {sorted(operands)}.")
        if outer and outer != "none" and (not aggregates or aggregates[-1]["operation"] != outer):
            errors.append(f"Metric {output} requires outer {outer}, not a pooled total or a different aggregate.")
        owner = metric.get("group_owner")
        if owner in schema and outer and outer != "none" and aggregates:
            group_origins = aggregates[-1]["group_origins"]
            if group_origins and not any(source == owner for source, _ in group_origins):
                errors.append(f"Metric {output} groups by the wrong source; the requested group owner is {owner}.")
        inner, entity = _aggregate_name(metric.get("inner_aggregation")), metric.get("entity_key")
        # A component-based formula has no root source. Its inner aggregates
        # were checked against each real component above, never against None.
        if source and inner and inner != "none" and entity:
            if not any(matches_inner(a, inner, source, entity, operands) for a in earlier):
                errors.append(f"Metric {output} requires {inner} per {source}.{entity} before the cohort aggregate.")
    for policy in requirements.get("null_policy", {}).get("label_groups", []):
        if not isinstance(policy, dict):
            continue
        field, action = policy.get("field"), policy.get("policy")
        if field in final:
            if action == "exclude" and not final[field]["nonnull"]:
                errors.append(f"Label {field} requires an explicit is_not_null filter before ranking/output.")
            if action == "keep" and final[field]["nonnull"]:
                errors.append(f"Label {field} must preserve its NULL group; remove the non-null label filter.")
    return list(dict.fromkeys(errors))
