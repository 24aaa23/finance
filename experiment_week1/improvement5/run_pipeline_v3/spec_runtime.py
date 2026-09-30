"""Compile declarative plans and validate exactly the datasets execution will read.

No domain names, question IDs, sampled values or natural-language guesses are used here.
The compiler does not execute a query or repair its semantics by dropping operations.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from typing import Any

from .spec_contracts import flatten_identifiers, normalize_spec


AGGREGATIONS = {"sum", "avg", "average", "mean", "count", "count_rows", "count_distinct", "nunique", "min", "max"}
MERGES = {"Integrate", "Set_Intersect", "Set_Union", "Set_Difference", "Union", "Difference", "Combine_Scalars"}
OPERATORS = MERGES | {"Filter_Aggregate", "Math_Compute", "Date_Extract", "Bucket", "Order_By", "Distinct", "Copy"}


def _fields(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("fields", value.get("columns", []))
    return list(dict.fromkeys(flatten_identifiers(value)))


def compile_spec(spec: Any, dataset_schemas: dict[str, Any]) -> dict:
    """Return metadata plus execution_steps, compiled_output/schema, and contract_errors.

    Declarations remain unchanged so recompilation against runtime schemas is idempotent.
    Each executable step has one compiler-owned name and explicit predecessor IDs.
    Aggregation outputs contain only grouping keys and their declared metrics.
    """
    result = normalize_spec(spec)
    errors: list[str] = list(result.get("normalization_errors") or [])
    if not isinstance(spec, dict) or not spec:
        errors.append("A specification must be a nonempty object with explicit declarations.")
    schemas = {str(name): _fields(fields) for name, fields in dataset_schemas.items()}
    originals = set(schemas)
    aliases = {name: name for name in schemas}
    steps: list[dict] = []
    grains: dict[str, tuple[str, ...] | None] = {name: None for name in schemas}
    dependencies: dict[str, set[str]] = {name: {name} for name in schemas}
    lineage: dict[str, list[dict]] = {name: [] for name in schemas}
    previous = "raw" if "raw" in schemas else (next(iter(schemas)) if len(schemas) == 1 else "")
    is_processing = "steps" in result
    # Repair responses may reuse compiler-looking IDs. Reserve all declarations,
    # including later steps, before expanding one operation into several steps.
    reserved_names = set(originals)

    def reserve_declarations(declarations):
        for declaration in declarations if isinstance(declarations, list) else []:
            if isinstance(declaration, dict):
                reserved_names.update(value for value in (declaration.get("id"), declaration.get("output"))
                                      if isinstance(value, str) and value)
                reserve_declarations(declaration.get("aggregations"))

    for key in ("steps", "merge_steps", "pre_steps", "final_steps", "final_measures"):
        reserve_declarations(result.get(key))
    name_index = 0

    def new_name() -> str:
        nonlocal name_index
        while True:
            name_index += 1
            name = f"__spec_step_{name_index}"
            if name not in reserved_names and name not in schemas:
                return name

    def fail(message: str) -> None:
        errors.append(message)

    def require(field: Any, available: list[str], context: str, allow_star: bool = False) -> None:
        if not isinstance(field, str) or not field or (field not in available and not (allow_star and field == "*")):
            fail(f"{context}: field does not exist on the selected input: {field}")

    def resolve(raw: Any, default: str) -> list[str]:
        ids = flatten_identifiers(raw)
        if not ids:
            ids = [default] if default else []
        resolved = [default if item == "previous" else aliases.get(item, item) for item in ids]
        if not resolved or any(not item for item in resolved):
            fail("Step requires an explicit input dataset; 'previous' has no predecessor.")
        for item in resolved:
            if item not in schemas:
                fail(f"Step input dataset does not exist: {item}")
        return resolved

    def append(raw: Any, stage: str, default: str | None = None) -> str:
        nonlocal previous
        if not isinstance(raw, dict):
            fail(f"{stage}: every operation must be an object.")
            return previous
        step = deepcopy(raw)
        op = step.get("operator")
        # A list of measures applies to one common input, rather than aggregating
        # each previous aggregate. Reuse the existing same-grain combine path.
        if op == "Filter_Aggregate" and "aggregations" in step:
            metrics = step.get("aggregations")
            if not isinstance(metrics, list) or not metrics:
                fail(f"{stage}: aggregations must be a nonempty list.")
                return previous
            base = previous if default is None else default
            common = {key: value for key, value in step.items() if key not in {"id", "output", "aggregations", "output_schema"}}
            metric_ids = []
            for metric in metrics:
                if not isinstance(metric, dict):
                    fail(f"{stage}: every aggregation must be an object.")
                    continue
                if any(key in metric for key in ("input", "inputs")):
                    fail(f"{stage}: nested aggregations must use their parent input.")
                metric_ids.append(append({**common, **metric, "operator": "Filter_Aggregate"}, stage, default=base))
            combined = combine(metric_ids, "combine_aggregations")
            for declared in (step.get("id"), step.get("output")):
                if declared and (not isinstance(declared, str) or declared in originals or (declared in aliases and aliases[declared] != combined)):
                    fail(f"{stage}: duplicate or invalid dataset name: {declared}")
                elif declared:
                    aliases[declared] = combined
            previous = combined
            return combined
        # Lower an explicit aggregate expression through the same checked formula
        # engine used by Math_Compute. Unknown bare column names remain errors.
        operation = str(step.get("operation") or "").lower()
        if op == "Filter_Aggregate" and operation in AGGREGATIONS:
            selected_input = resolve(step.get("inputs", step.get("input")), previous if default is None else default)
            available = schemas.get(selected_input[0], []) if len(selected_input) == 1 else []
            target = step.get("target_column") or step.get("input_column") or step.get("column")
            if isinstance(target, str) and target not in available and target != "*":
                try:
                    from .non_llm_operators.math_compute import expression_columns
                    referenced = expression_columns(target)
                    tree = ast.parse(target, mode="eval").body
                    if not isinstance(tree, ast.Name) and referenced <= set(available) and len(selected_input) == 1:
                        temporary = "__aggregate_value"
                        while temporary in available:
                            temporary += "_"
                        if step.get("filters"):
                            filtered = append({"operator": "Filter_Aggregate", "inputs": selected_input,
                                               "operation": "filter", "filters": step["filters"]}, stage)
                            selected_input = [filtered]
                            step["filters"] = []
                        computed = append({"operator": "Math_Compute", "inputs": selected_input,
                                           "expression": target, "output_column": temporary}, stage)
                        step.pop("input", None)
                        step["inputs"] = [computed]
                        step["target_column"] = temporary
                except (ValueError, TypeError, SyntaxError):
                    pass  # The original target is reported as invalid below.
        name = new_name()
        for declared in (step.get("id"), step.get("output")):
            if declared and (not isinstance(declared, str) or declared in originals or (declared in aliases and aliases[declared] != name)):
                fail(f"{name}: duplicate or invalid dataset name: {declared}")
        selected = resolve(step.get("inputs", step.get("input")), previous if default is None else default)
        input_schemas = [schemas.get(item, []) for item in selected]
        fields = input_schemas[0] if input_schemas else []
        if op not in OPERATORS:
            fail(f"{name}: unsupported operator: {op}")
        if op not in MERGES and len(selected) != 1:
            fail(f"{name}: {op} requires exactly one input dataset.")
        if op in MERGES and len(selected) < 2:
            fail(f"{name}: {op} requires at least two input datasets.")
        output = list(fields)
        grain = grains.get(selected[0]) if selected else None
        next_lineage = list(lineage.get(selected[0], [])) if selected else []
        operation = str(step.get("operation") or "").lower()
        groups = flatten_identifiers(step.get("group_by"))

        if op in MERGES:
            keys = flatten_identifiers(step.get("join_key"))
            left_keys = flatten_identifiers(step.get("left_on")) or keys
            right_keys = flatten_identifiers(step.get("right_on")) or keys
            if op in {"Integrate", "Set_Intersect", "Set_Difference", "Difference"} and not (op == "Integrate" and step.get("join_type") == "cross"):
                if not left_keys or len(left_keys) != len(right_keys):
                    fail(f"{name}: explicit equal-length join_key or left_on/right_on keys are required.")
                if (step.get("left_on") or step.get("right_on")) and len(selected) != 2:
                    fail(f"{name}: left_on/right_on requires exactly two datasets.")
                for field in left_keys:
                    require(field, fields, name + " left join key")
                for right_schema in input_schemas[1:]:
                    for field in right_keys:
                        require(field, right_schema, name + " right join key")
            if op == "Integrate":
                how = str(step.get("join_type") or step.get("how") or "inner").lower()
                if how not in {"inner", "left", "right", "outer", "cross"}:
                    fail(f"{name}: unsupported join type: {how}")
                step["join_type"] = how
                suffixes = step.get("suffixes", ["", "_right"])
                if not isinstance(suffixes, (list, tuple)) or len(suffixes) != 2 or not all(isinstance(item, str) for item in suffixes):
                    fail(f"{name}: suffixes requires two strings.")
                    suffixes = ["", "_right"]
                from .relational import join_column_maps
                output = list(fields)
                for right_schema in input_schemas[1:]:
                    _, _, output = join_column_maps(output, right_schema, left_keys, right_keys, suffixes)
                grain = tuple(keys) if step.get("validate") == "one_to_one" else None
                next_lineage = [entry for item in selected for entry in lineage.get(item, [])]
            elif op in {"Set_Union", "Union"}:
                output = list(dict.fromkeys(field for values in input_schemas for field in values))
                for field in keys:
                    for source_fields in input_schemas:
                        require(field, source_fields, name + " union key")
                grain = None
            elif op == "Combine_Scalars":
                output = []
                for source_fields in input_schemas:
                    for field in source_fields:
                        if field in output:
                            fail(f"{name}: independent scalar measures have duplicate output: {field}")
                        output.append(field)
                grain = ()
                next_lineage = [entry for item in selected for entry in lineage.get(item, [])]
        elif op == "Filter_Aggregate" or (op == "Math_Compute" and operation in AGGREGATIONS and not step.get("expression")):
            # One aggregate implementation preserves SQL null/count semantics.
            step["operator"] = "Filter_Aggregate"
            step["strict_aggregation"] = True
            operation = {"mean": "avg", "average": "avg", "nunique": "count_distinct"}.get(operation, operation)
            step["operation"] = operation
            if operation not in AGGREGATIONS | {"filter", "where"}:
                fail(f"{name}: unsupported aggregate/filter operation: {operation}")
            for field in groups:
                require(field, fields, name + " group_by")
            filters = step.get("filters") or []
            if not isinstance(filters, list):
                fail(f"{name}: filters must be a list.")
                filters = []
            from .semantic_contracts import predicate_errors
            for error in predicate_errors(filters):
                fail(f"{name}: {error}")
            def check_predicate(condition):
                if not isinstance(condition, dict):
                    fail(f"{name}: every filter must be an object.")
                elif any(key in condition for key in ("any", "all", "not")):
                    for key in ("any", "all", "not"):
                        if key in condition:
                            children = [condition[key]] if key == "not" else condition[key]
                            if not isinstance(children, list) or not children:
                                fail(f"{name}: {key} requires predicates.")
                            else:
                                for child in children:
                                    check_predicate(child)
                else:
                    require(condition.get("field") or condition.get("column") or condition.get("target_column"), fields, name + " filter")
            for condition in filters:
                check_predicate(condition)
            if operation in AGGREGATIONS:
                target = step.get("target_column") or step.get("input_column") or step.get("column")
                if operation in {"count", "count_rows"} and not target:
                    target = "*"
                require(target, fields, name + " aggregate source", allow_star=operation in {"count", "count_rows"})
                step["target_column"] = target
                output_column = step.get("output_column")
                if not isinstance(output_column, str) or not output_column:
                    fail(f"{name}: aggregation requires an explicit output_column.")
                    output_column = "__invalid_metric"
                if output_column in groups:
                    fail(f"{name}: metric output duplicates a grouping key: {output_column}")
                output = list(dict.fromkeys(groups + [output_column]))
                grain = tuple(groups)
                next_lineage = [{"output_column": output_column, "operation": operation,
                                 "input_column": target, "group_by": groups,
                                 "input_aggregations": lineage.get(selected[0], []) if selected else []}]
            elif operation == "distinct":
                for field in flatten_identifiers(step.get("distinct_on")):
                    require(field, fields, name + " distinct_on")
        elif op in {"Math_Compute", "Date_Extract", "Bucket"}:
            output_column = step.get("output_column")
            if not isinstance(output_column, str) or not output_column:
                fail(f"{name}: {op} requires an explicit output_column.")
            elif output_column not in output:
                output.append(output_column)
            if op == "Math_Compute":
                if step.get("expression"):
                    try:
                        from .non_llm_operators.math_compute import expression_columns
                        referenced = expression_columns(step["expression"])
                        for field in referenced:
                            require(field, fields, name + " expression")
                    except (ValueError, TypeError, SyntaxError) as exc:
                        fail(f"{name}: invalid expression: {exc}")
                else:
                    left = step.get("left_column") or step.get("base_col")
                    right = step.get("right_column") or step.get("target_column") or step.get("column")
                    for field in (left, right):
                        require(field, fields, name + " arithmetic source")
            else:
                require(step.get("input_column") or step.get("target_column"), fields, name + " source")
                if op == "Date_Extract" and str(step.get("part") or "").lower() not in {"year", "month", "day"}:
                    fail(f"{name}: unsupported date part: {step.get('part')}")
                if op == "Bucket" and (not isinstance(step.get("rules"), list) or not step.get("rules")):
                    fail(f"{name}: Bucket requires declared rules.")
        elif op == "Copy":
            columns = flatten_identifiers(step.get("output_columns", fields))
            if not columns:
                fail(f"{name}: Copy requires a nonempty column selection.")
            for field in columns:
                require(field, fields, name + " copy source")
            output = columns
            step["output_columns"] = columns
            if grain is not None and not set(grain) <= set(columns):
                grain = None
        elif op == "Distinct":
            for field in flatten_identifiers(step.get("distinct_on")):
                require(field, fields, name + " distinct_on")
        elif op == "Order_By":
            try:
                from .llm_operators.order_by import _sort_terms
                for term in _sort_terms(step):
                    require(term["column"], fields, name + " order_by")
            except (ValueError, TypeError) as exc:
                fail(f"{name}: {exc}")
            limit = step.get("limit")
            if limit is not None and (isinstance(limit, bool) or not str(limit).isdigit()):
                fail(f"{name}: limit must be a nonnegative integer.")

        for declared in (raw.get("id"), raw.get("output")):
            if isinstance(declared, str) and declared and declared not in originals:
                aliases[declared] = name
        aliases[name] = name
        step.pop("input", None)
        step.update({"id": name, "output": name, "inputs": selected, "stage": stage})
        # Keep malformed plans inspectable by callers; their contract error is
        # reported above instead of becoming an unrelated KeyError('operator').
        step.setdefault("operator", op)
        step.setdefault("preserve_null_groups", result.get("preserve_null_groups", True))
        schemas[name] = list(dict.fromkeys(output))
        grains[name] = grain
        dependencies[name] = set().union(*(dependencies.get(item, set()) for item in selected)) if selected else set()
        lineage[name] = next_lineage
        steps.append(step)
        previous = name
        return name

    def declarations(key: str) -> list:
        value = result.get(key) or []
        if not isinstance(value, list):
            fail(f"{key} must be a list.")
            return []
        return value

    def combine(ids: list[str], stage: str) -> str:
        if not ids:
            return previous
        if len(ids) == 1:
            return ids[0]
        groupings = [grains.get(item) for item in ids]
        if any(group is None for group in groupings) or len(set(groupings)) != 1:
            fail("Independent outputs require an explicit merge; only measures at the same grouping grain can be combined automatically.")
            return ids[-1]
        keys = list(groupings[0] or ())
        nonkeys: set[str] = set()
        for item in ids:
            metrics = set(schemas[item]) - set(keys)
            if nonkeys & metrics:
                fail("Independent measures have duplicate output columns: " + ", ".join(sorted(nonkeys & metrics)))
            nonkeys.update(metrics)
        return append({"operator": "Integrate" if keys else "Combine_Scalars", "inputs": ids,
                       "join_key": keys, "join_type": "outer", "validate": "one_to_one",
                       "nulls_equal": True}, stage)

    if is_processing:
        for raw in declarations("steps"):
            append(raw, "processing")
    else:
        pending = [(raw, "merge") for raw in declarations("merge_steps")]
        pending += [(raw, "pre_measure") for raw in declarations("pre_steps")]
        # Generated plans sometimes declare a merge before the named per-branch
        # aggregates it consumes. Follow those explicit dependencies, preserving
        # declaration order whenever its predecessors already exist.
        while pending:
            ready = None
            for index, (raw, _) in enumerate(pending):
                if not isinstance(raw, dict):
                    ready = index
                    break
                identifiers = flatten_identifiers(raw.get("inputs", raw.get("input")))
                if identifiers and all((previous if item == "previous" else aliases.get(item, item)) in schemas for item in identifiers):
                    ready = index
                    break
                if not identifiers and previous:
                    ready = index
                    break
            # An unknown input/cycle remains an explicit error, never a guessed
            # join or a skipped operation.
            raw, stage = pending.pop(ready if ready is not None else 0)
            append(raw, stage)
        final_steps = declarations("final_steps")
        measures = declarations("final_measures")
        # Backward compatibility for only the unambiguous leading date/bucket prefix.
        # A date/bucket step after a formula/filter/order remains in that position.
        if measures and not result.get("pre_steps"):
            while final_steps and isinstance(final_steps[0], dict) and final_steps[0].get("operator") in {"Date_Extract", "Bucket"}:
                append(final_steps[0], "pre_measure")
                final_steps = final_steps[1:]
        measure_base = previous
        measure_ids = []
        for measure in measures:
            if not isinstance(measure, dict):
                fail("Every final measure must be an object.")
                continue
            raw = {**measure, "operator": "Filter_Aggregate",
                   "target_column": measure.get("input_column") or measure.get("target_column"),
                   "group_by": measure.get("group_by", result.get("final_group_by", []))}
            if str(raw.get("operation") or "").lower() not in AGGREGATIONS:
                fail(f"Unsupported final measure operation: {raw.get('operation')}")
            measure_ids.append(append(raw, "measure", default=measure_base))
        if measure_ids:
            named_measure_inputs = {
                aliases.get(item, item)
                for raw in final_steps if isinstance(raw, dict)
                for item in flatten_identifiers(raw.get("inputs", raw.get("input")))
                if item != "previous"
            }
            # Explicit downstream joins already combine these named measures.
            # Adding another automatic join creates an unused terminal and can
            # duplicate metric columns, despite an otherwise executable plan.
            previous = measure_ids[-1] if set(measure_ids) <= named_measure_inputs else combine(measure_ids, "combine_measures")
        distinct_keys = flatten_identifiers(result.get("distinct_on"))
        needs_distinct = bool(distinct_keys) or result.get("distinct") is True
        for raw in final_steps:
            if needs_distinct and isinstance(raw, dict) and raw.get("operator") == "Order_By":
                append({"operator": "Distinct", "distinct_on": distinct_keys or result.get("projection", [])}, "final_distinct")
                needs_distinct = False
                raw = {**raw, "input": "previous"}
                raw.pop("inputs", None)
            append(raw, "final")
        if needs_distinct:
            append({"operator": "Distinct", "distinct_on": distinct_keys or result.get("projection", [])}, "final_distinct")

    produced = [step["output"] for step in steps]
    consumed = {item for step in steps for item in step["inputs"]}
    terminals = [item for item in produced if item not in consumed]
    requested = result.get("output") if is_processing else result.get("final_output")
    requested_ids = flatten_identifiers(requested)
    if len(requested_ids) > 1:
        fail("A spec must select exactly one output dataset.")
    selected_output = aliases.get(requested_ids[0], requested_ids[0]) if requested_ids else ""
    if selected_output == "previous":
        selected_output = previous
    if selected_output and selected_output not in schemas:
        fail(f"Requested output dataset does not exist: {selected_output}")
    if steps:
        # A stale/raw output must not bypass computations. Treat this as a contract
        # error for repair, rather than silently changing which answer is returned.
        if selected_output and selected_output not in terminals:
            fail(f"Requested output {selected_output} bypasses terminal computations: {terminals}")
        if len(terminals) > 1:
            selected_output = combine(terminals, "combine_terminals")
        elif not selected_output and terminals:
            selected_output = terminals[0]
    elif not selected_output:
        selected_output = previous
    output_fields = schemas.get(selected_output, [])
    if not is_processing and len(originals) > 1:
        unused = sorted(originals - dependencies.get(selected_output, set()))
        if unused:
            result.setdefault("plan_warnings", []).append(f"Final output does not use retrieved branches: {unused}")
    for field in flatten_identifiers(result.get("projection")):
        require(field, output_fields, "projection")
    for field in flatten_identifiers(result.get("output_schema")):
        require(field, output_fields, "output_schema")
    for field in flatten_identifiers(result.get("distinct_on")):
        require(field, output_fields, "distinct_on")
    for field in flatten_identifiers(result.get("entity_grain")):
        require(field, output_fields, "entity_grain")
    projection = flatten_identifiers(result.get("projection"))
    result.update({"execution_steps": steps, "compiled_output": selected_output,
                   "compiled_output_schema": projection or output_fields,
                   "dataset_schemas": schemas, "execution_name_map": aliases,
                   "aggregation_lineage": lineage.get(selected_output, []),
                   "contract_errors": list(dict.fromkeys(errors))})
    return result
