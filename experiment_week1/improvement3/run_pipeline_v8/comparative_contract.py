"""Validate declared comparison metrics against the compiled data flow.

No question IDs, reference SQL, answer values, or domain-specific formulas live here.
The contract is a model interpretation; consistency is not proof of that interpretation.
"""
import ast
import re

from .relational import join_column_maps


COMPARATIVE_INSTRUCTIONS = """
This is a grouped multi-source comparison. Include a comparative_contract beside
final_steps and projection, resolving its names against ACTUAL available tables.
It records your interpretation. Do not copy speculative output aliases or a
universal entity-key spelling from decomposition; each source has its own keys.

Exact shape (illustrative, replace every name):
"comparative_contract": {
  "version": 1,
  "dimensions": [{"source":"Customers", "column":"region", "output_column":"region_name"}],
  "required_population": ["Customers", "Payments", "Reviews"],
  "metrics": [
    {"source":"Payments", "source_columns":["amount"], "source_grain":["customer_ref"],
     "inner_aggregate":"sum", "outer_aggregate":"avg", "output_column":"mean_customer_spend"},
    {"source":"Reviews", "source_columns":["score"], "source_grain":["owner"],
     "inner_aggregate":"avg", "outer_aggregate":"avg", "output_column":"mean_customer_score"}
  ],
  "assumptions": []
}
Here the question requests customers WITH BOTH payments and reviews. required_population
names the sources each metric must join before its outer aggregation. If metrics
intentionally use separate populations, name only their shared required base
sources and explain that interpretation in assumptions. Required participation
normally uses inner joins between entity summaries; optional labels use left joins.
Every metric and dimension output_column must appear in projection.

inner_aggregate is sum|avg|min|max|count|count_rows|count_distinct|none.
Use none for a record-weighted comparison or an already one-row-per-entity measure.
For entity-weighted comparisons use the appropriate inner calculation, THEN join
eligible entity summaries, THEN apply the outer calculation by the profile attribute.
Independent group summaries can use different populations and change the answer.
For a formula, source_columns lists its raw operands. Compute it before its inner
aggregate and preserve null propagation: SUM(value-cost) can differ from
SUM(value)-SUM(cost) when missing-value patterns differ. A maximum concentration
uses MAX, not the average/sum of every allocation. Explain unspecified definitions.

Alias display fields by copying their owning column. Profile attributes and fact
attributes can differ; an unrelated label table cannot replace a missing profile.
Preserve null groups. For dimension joins expected to be many-to-one, set
validate:"many_to_one"; for entity-summary joins use validate:"one_to_one" when
appropriate. These checks apply to actual data. Sort/limit after the final metrics.

A metric must descend from its own declared source, inner aggregate/grain and
outer aggregate. A summary on an unused path does not satisfy it. Repair calculated
aliases in the plan rather than requesting them from retrieval. All source IDs
must be actual available table IDs. The original question and schema outrank
comparison_notes. Record ambiguous choices in assumptions. No reference answers
are available to this planner. Do not use none to bypass an entity-level metric.
"""


def needs_comparative_contract(query):
    text = re.sub(r"\s+", " ", str(query).lower())
    return bool(re.search(r"\bacross\b.*\bcompare\b.*\b(?:three|four|five|[3-9]) related tables?\b", text))


def _names(value):
    return [value] if isinstance(value, str) else value if isinstance(value, list) else []


def _operation(value):
    value = str(value or "").lower()
    return {"average": "avg", "mean": "avg", "nunique": "count_distinct"}.get(value, value)


def _refs(node):
    return set(node.get("sources", ()))


def validate_comparative_contract(spec, originals):
    contract = spec.get("comparative_contract")
    if not contract:
        return ["comparative_contract: declare the comparison dimension, population and metric calculations."] if spec.get("comparative_contract_required") else []
    errors = []

    def fail(message):
        errors.append("comparative_contract: " + message)

    if not isinstance(contract, dict) or contract.get("version") != 1:
        return ["comparative_contract: expected an object with version 1."]
    metrics = contract.get("metrics")
    dimensions = contract.get("dimensions", [])
    population = _names(contract.get("required_population"))
    if not isinstance(metrics, list) or not metrics or any(not isinstance(m, dict) for m in metrics):
        return ["comparative_contract: metrics must be a nonempty list of objects."]
    if not isinstance(dimensions, list) or any(not isinstance(d, dict) for d in dimensions):
        return ["comparative_contract: dimensions must be a list of objects."]
    if not dimensions and spec.get("comparative_contract_required"):
        fail("a grouped comparison requires dimensions.")
    if not population:
        fail("declare at least the required base population.")
    if any(not isinstance(p, str) or p not in originals for p in population):
        fail("required_population must name actual source tables.")
        population = [p for p in population if isinstance(p, str) and p in originals]

    # Keep column-specific expression trees. A summary on an unused sibling path
    # cannot certify the raw path used by the answer (a hole in V5's global flag).
    tables = {name: {col: {"kind": "raw", "sources": {(name, col)}} for col in fields}
              for name, fields in originals.items()}
    dependencies = {name: {name} for name in originals}
    participants = {name: {name} for name in originals}
    for step in spec.get("execution_steps", []):
        ids = step["inputs"]
        source = tables.get(ids[0], {}) if ids else {}
        result = dict(source)
        op = step["operator"]
        deps = set().union(*(dependencies.get(i, set()) for i in ids))
        present = set(participants.get(ids[0], set())) if ids else set()
        if op == "Integrate":
            left_keys = _names(step.get("left_on") or step.get("join_key"))
            right_keys = _names(step.get("right_on") or step.get("join_key"))
            for right_id in ids[1:]:
                right = tables[right_id]
                lm, rm, _ = join_column_maps(list(result), list(right), left_keys, right_keys, step.get("suffixes", ["", "_right"]))
                merged = {lm[c]: node for c, node in result.items()}
                for col, node in right.items():
                    target = rm[col]
                    if target in merged:
                        merged[target] = {**merged[target], "sources": _refs(merged[target]) | _refs(node)}
                    else:
                        merged[target] = node
                result = merged
                how = step.get("join_type", "inner")
                right_present = participants.get(right_id, set())
                if how in {"inner", "cross"}:
                    present |= right_present
                elif how == "right":
                    present = set(right_present)
                elif how == "outer":
                    present &= right_present
        elif op == "Combine_Scalars":
            result = {col: node for i in ids for col, node in tables[i].items()}
        elif op == "Filter_Aggregate" and _operation(step.get("operation")) not in {"filter", "where"}:
            groups = _names(step.get("group_by"))
            child = source.get(step.get("target_column"), {})
            if step.get("target_column") == "*":
                child = {"kind": "raw", "sources": {(i, "*") for i in deps}}
            result = {col: source[col] for col in groups}
            result[step["output_column"]] = {
                "kind": "aggregate", "operation": _operation(step.get("operation")),
                "sources": _refs(child), "child": child,
                "groups": [_refs(source[col]) for col in groups],
                "population": present, "dependencies": deps, "step": step["id"],
            }
        elif op == "Math_Compute" and step.get("expression"):
            tree = ast.parse(step["expression"], mode="eval").body
            def column(node):
                if isinstance(node, ast.Name):
                    return node.id if node.id in source else None
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "column" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
                    return node.args[0].value
            copied = column(tree)
            if copied in source:
                result[step["output_column"]] = source[copied]
            else:
                used = {column(n) for n in ast.walk(tree)} - {None}
                result[step["output_column"]] = {"kind": "formula", "sources": set().union(*(_refs(source.get(c, {})) for c in used))}
        elif op in {"Math_Compute", "Bucket", "Date_Extract"}:
            # Derived fields must not inherit an unrelated aggregate's proof.
            columns = [step.get(k) for k in ("input_column", "target_column", "left_column", "right_column", "base_col", "column")]
            result[step["output_column"]] = {"kind": "formula", "sources": set().union(*(_refs(source.get(c, {})) for c in columns))}
        elif op in {"Set_Union", "Union"}:
            result = {col: {"kind": "union", "sources": set().union(*(_refs(tables[i].get(col, {})) for i in ids))}
                      for col in spec["dataset_schemas"][step["output"]]}
        tables[step["output"]] = result
        dependencies[step["output"]] = deps
        participants[step["output"]] = present

    output = tables.get(spec.get("compiled_output"), {})
    projection = spec.get("compiled_output_schema", [])
    dimension_refs = []
    for dimension in dimensions:
        branch, col, alias = (dimension.get(k) for k in ("source", "column", "output_column"))
        if not isinstance(branch, str) or not isinstance(col, str) or col not in originals.get(branch, []):
            fail("dimension must identify an actual source column.")
            continue
        expected = (branch, col)
        dimension_refs.append(expected)
        if not isinstance(alias, str) or alias not in projection or expected not in _refs(output.get(alias, {})):
            fail(f"dimension {alias} must retain provenance from {branch}.{col} and be projected.")

    metric_sources = {m.get("source") for m in metrics if isinstance(m.get("source"), str)}
    for metric in metrics:
        alias, branch = metric.get("output_column"), metric.get("source")
        if not isinstance(alias, str) or not isinstance(branch, str) or branch not in originals:
            fail("each metric needs output_column and an actual source table.")
            continue
        node = output.get(alias, {})
        if alias not in projection:
            fail(f"required metric {alias} is missing from the projection.")
        fields = _names(metric.get("source_columns"))
        if not fields or any(not isinstance(c, str) or (c not in originals[branch] and c != "*") for c in fields):
            fail(f"metric {alias} needs actual source_columns on {branch}.")
            continue
        expected_sources = {(branch, c) for c in fields}
        if _refs(node) != expected_sources:
            fail(f"metric {alias} uses different source columns from its declaration.")
        outer = _operation(metric.get("outer_aggregate"))
        if node.get("kind") != "aggregate" or node.get("operation") != outer:
            fail(f"metric {alias} must end with its declared outer aggregate {outer}.")
            continue
        groups = node.get("groups", [])
        if len(groups) != len(dimension_refs) or any(not any(ref in g for g in groups) for ref in dimension_refs):
            fail(f"metric {alias} must group at the declared comparison dimension.")
        if not set(population).issubset(node.get("population", set())):
            fail(f"metric {alias} aggregates before joining its required population {population}.")
        inner = _operation(metric.get("inner_aggregate"))
        if inner not in {"none", ""}:
            child = node.get("child", {})
            grain = _names(metric.get("source_grain"))
            if not grain or any(not isinstance(c, str) or c not in originals[branch] for c in grain):
                fail(f"metric {alias} needs source_grain using actual fields on {branch}.")
                continue
            if child.get("kind") != "aggregate" or child.get("operation") != inner:
                fail(f"metric {alias} needs {inner} per source entity before {outer}; a sibling summary cannot satisfy this.")
                continue
            inner_groups = child.get("groups", [])
            if len(inner_groups) != len(grain) or any(not any((branch, col) in g for g in inner_groups) for col in grain):
                fail(f"metric {alias} inner grain must be {branch}.{grain}.")
            if (metric_sources - {branch}) & child.get("dependencies", set()):
                fail(f"metric {alias} summarizes after joining an independent metric source; summarize before that join.")
        elif node.get("child", {}).get("kind") == "aggregate":
            fail(f"metric {alias} declares a record-weighted aggregate but averages a summary.")
    return list(dict.fromkeys(errors))
