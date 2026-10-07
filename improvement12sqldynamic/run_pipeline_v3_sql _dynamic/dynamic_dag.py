"""Validate upfront graphs with the existing calculation compiler.

Graph edges are data dependencies. Ordered input IDs, rather than NetworkX edge
insertion order, determine the left and right sides of joins and set operations.
"""
from copy import deepcopy
import hashlib
import json

import networkx as nx

from .spec_runtime import OPERATORS, compile_spec
from .spec_contracts import flatten_identifiers, normalize_spec
from .query_understanding import final_contract_errors

RETRIEVAL = ("Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Processing_Spec")
CALCULATIONS = frozenset(OPERATORS)
OUTPUT_NODE = "__dynamic_output"


def graph_payload(dag):
    return {
        "nodes": [{"id": node, "operator": data["operator"],
                   "inputs": deepcopy(data.get("explicit_inputs", {}))}
                  for node, data in dag.nodes(data=True)],
        "edges": [{"source": a, "target": b} for a, b in dag.edges],
    }


def graph_fingerprint(dag):
    """Ignore cosmetic node names while retaining ordered data dependencies."""
    signatures = {}
    for name in nx.topological_sort(dag):
        node = dag.nodes[name]
        params = deepcopy(node.get("explicit_inputs", {}))
        parents = node.get("dynamic_step", {}).get("inputs", list(dag.predecessors(name)))
        params.pop("input", None)
        params.pop("inputs", None)
        content = {"operator": node["operator"], "params": params,
                   "parents": [signatures[parent] for parent in parents]}
        signatures[name] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    content = {"sink": signatures[next(n for n in dag if dag.out_degree(n) == 0)],
               "projection": dag.graph["dynamic_plan"]["spec"]["projection"],
               "rounding": dag.graph["dynamic_plan"]["spec"].get("rounding")}
    return json.dumps(content, sort_keys=True)


def _strings(value, label, allow_empty=False):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(label + " must be a list of nonempty strings.")
    if len(value) != len(set(value)) or (not value and not allow_empty):
        raise ValueError(label + " must contain unique names.")
    return value


def validate_candidate(payload, decomposition, schema, registry, contract_checks=True):
    """Return an executable graph; never invent missing model nodes or edges."""
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list) or not payload["nodes"]:
        raise ValueError("Candidate must contain a nonempty nodes list.")
    if not isinstance(payload.get("edges"), list):
        raise ValueError("Candidate must contain an edges list.")
    graph = nx.DiGraph()
    allowed = set(RETRIEVAL) | CALCULATIONS | {"Validate", "Explain"}
    for node in payload["nodes"]:
        if not isinstance(node, dict):
            raise ValueError("Every node must be an object.")
        name, operator, inputs = node.get("id"), node.get("operator"), node.get("inputs", {})
        if not isinstance(name, str) or not name or name in graph or name.startswith("__dynamic_"):
            raise ValueError("Duplicate, invalid, or reserved node ID: " + str(name))
        if not isinstance(operator, str) or operator not in allowed:
            raise ValueError("Unsupported DAG operator: " + str(operator))
        if operator not in registry and operator not in {"Distinct", "Combine_Scalars"}:
            raise ValueError("Operator absent from registry: " + operator)
        if not isinstance(inputs, dict):
            raise ValueError(name + ": inputs must be an object.")
        if operator in RETRIEVAL:
            permitted = {"subquestion_id", "required_fields"} if operator == "Query_Spec" else {"subquestion_id"}
            if set(inputs) - permitted:
                raise ValueError(name + ": retrieval inputs only declare branch identity and required raw fields.")
        if operator in {"Validate", "Explain"} and inputs:
            raise ValueError(name + ": completion inputs come from the selected result, not model overrides.")
        if set(inputs) & {"data", "sparql", "query_spec", "global_schema", "final_spec", "decomposition"}:
            raise ValueError(name + ": inputs may not override runtime data or contracts.")
        graph.add_node(name, operator=operator, explicit_inputs=deepcopy(inputs))
    for edge in payload["edges"]:
        if not isinstance(edge, dict) or not all(isinstance(edge.get(key), str) for key in ("source", "target")):
            raise ValueError("Every edge requires source and target IDs.")
        pair = edge["source"], edge["target"]
        if any(name not in graph for name in pair):
            raise ValueError("Edge references an undeclared node: " + str(pair))
        if graph.has_edge(*pair):
            raise ValueError("Duplicate edge: " + str(pair))
        graph.add_edge(*pair)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Candidate contains a cycle.")
    branches = decomposition.get("subquestions", [])
    ids = [branch.get("id") for branch in branches if isinstance(branch, dict)]
    if not branches or len(ids) != len(branches) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Decomposition requires unique nonempty branch IDs.")
    branch_fields, branch_processing = {}, {}
    for branch in branches:
        branch_id, source = branch["id"], branch.get("source_class")
        if source not in schema:
            raise ValueError("Unknown branch source: " + str(source))
        columns = {c.get("name") if isinstance(c, dict) else c for c in schema[source].get("columns", [])}
        nodes = {}
        for operator in RETRIEVAL:
            matches = [name for name, data in graph.nodes(data=True)
                       if data["operator"] == operator and data["explicit_inputs"].get("subquestion_id") == branch_id]
            if len(matches) != 1:
                raise ValueError(branch_id + ": requires exactly one " + operator)
            nodes[operator] = matches[0]
        query_inputs = graph.nodes[nodes["Query_Spec"]]["explicit_inputs"]
        fields = _strings(query_inputs.get("required_fields"), branch_id + " required_fields")
        fields = list(dict.fromkeys(fields + flatten_identifiers(branch.get("required_fields"))
                                    + [name for name in flatten_identifiers(branch.get("retrieval_grain")) if name in columns]))
        if set(fields) - columns:
            raise ValueError(branch_id + ": unknown source fields: " + str(sorted(set(fields) - columns)))
        query_inputs["required_fields"] = fields
        if graph.in_degree(nodes["Query_Spec"]):
            raise ValueError("Query_Spec must start its own retrieval branch.")
        for previous, operator in zip(RETRIEVAL, RETRIEVAL[1:]):
            if list(graph.predecessors(nodes[operator])) != [nodes[previous]]:
                raise ValueError(branch_id + ": preserve own-branch " + previous + " -> " + operator)
        # Context-bearing retrieval nodes cannot feed unrelated branches or calculations.
        for previous, following in zip(RETRIEVAL, RETRIEVAL[1:]):
            if list(graph.successors(nodes[previous])) != [nodes[following]]:
                raise ValueError(branch_id + ": branch context may only feed its next retrieval stage.")
        branch_processing[branch_id] = nodes["Processing_Spec"]
        branch_fields[nodes["Processing_Spec"]] = fields
    for name, data in graph.nodes(data=True):
        if data["operator"] in RETRIEVAL and data["explicit_inputs"].get("subquestion_id") not in ids:
            raise ValueError(name + ": unknown subquestion_id.")
    validators = [n for n in graph if graph.nodes[n]["operator"] == "Validate"]
    explainers = [n for n in graph if graph.nodes[n]["operator"] == "Explain"]
    if len(validators) != 1 or len(explainers) != 1:
        raise ValueError("Exactly one Validate and one Explain are required.")
    validate, explain = validators[0], explainers[0]
    output = payload.get("final_output")
    if not isinstance(output, str) or output not in graph or graph.nodes[output]["operator"] not in CALCULATIONS | {"Processing_Spec"}:
        raise ValueError("final_output must name a calculation or processed dataset node.")
    if list(graph.predecessors(validate)) != [output] or list(graph.successors(validate)) != [explain]:
        raise ValueError("Final dataset must feed Validate -> Explain.")
    if list(graph.predecessors(explain)) != [validate] or graph.out_degree(explain):
        raise ValueError("Explain must be the only final sink after Validate.")
    if any(not nx.has_path(graph, name, explain) for name in graph):
        raise ValueError("Every node must contribute to the final output.")
    projection = _strings(payload.get("projection"), "projection", allow_empty=True)
    steps = []
    for name in nx.topological_sort(graph):
        data = graph.nodes[name]
        if data["operator"] not in CALCULATIONS:
            continue
        inputs = deepcopy(data["explicit_inputs"])
        if "input" in inputs and "inputs" in inputs:
            raise ValueError(name + ": declare either input or inputs, not both.")
        selected = inputs.get("inputs", inputs.get("input"))
        selected = [selected] if isinstance(selected, str) else selected
        selected = _strings(selected, name + " input datasets")
        if set(selected) != set(graph.predecessors(name)):
            raise ValueError(name + ": ordered input datasets must match its incoming edges.")
        if any(graph.nodes[parent]["operator"] not in CALCULATIONS | {"Processing_Spec"} for parent in selected):
            raise ValueError(name + ": calculations require processed datasets or earlier calculation outputs.")
        if set(inputs) & {"id", "output", "operator"}:
            raise ValueError(name + ": node identity and operator must not be overridden in inputs.")
        inputs.pop("input", None)
        steps.append({**inputs, "id": name, "operator": data["operator"], "inputs": selected})
    raw_spec = {"final_steps": steps, "final_output": output, "projection": projection,
                "preserve_null_groups": True, "rounding": payload.get("rounding")}
    for key in ("distinct", "distinct_on", "assumptions"):
        if key in payload:
            raw_spec[key] = deepcopy(payload[key])
    raw_spec = normalize_spec(raw_spec)
    if raw_spec.get("normalization_errors"):
        raise ValueError("; ".join(raw_spec["normalization_errors"]))
    distinct_keys = flatten_identifiers(raw_spec.get("distinct_on"))
    if distinct_keys or raw_spec.get("distinct") is True:
        # A global output policy must not change an earlier branch's ranking.
        # The legacy compiler inserts global DISTINCT before the first sort in
        # a flat steps list; an upfront DAG may have independent branch sorts.
        # Bind the operation to the selected final dataset explicitly instead.
        distinct_id = "__dynamic_distinct"
        final_step = next((step for step in raw_spec["final_steps"] if step["id"] == output), None)
        distinct_step = {"id": distinct_id, "operator": "Distinct",
                         "distinct_on": distinct_keys or projection}
        if final_step and final_step["operator"] == "Order_By":
            if len(final_step["inputs"]) != 1:
                raise ValueError("Final Order_By requires exactly one input dataset.")
            distinct_step["inputs"] = list(final_step["inputs"])
            position = raw_spec["final_steps"].index(final_step)
            raw_spec["final_steps"].insert(position, distinct_step)
            final_step["inputs"] = [distinct_id]
        else:
            distinct_step["inputs"] = [output]
            raw_spec["final_steps"].append(distinct_step)
            raw_spec["final_output"] = distinct_id
        raw_spec.pop("distinct", None)
        raw_spec.pop("distinct_on", None)
    rounding = raw_spec["rounding"]
    if rounding is not None and (isinstance(rounding, bool) or not isinstance(rounding, (int, dict))
            or (isinstance(rounding, dict) and any(key not in projection or isinstance(value, bool)
                or not isinstance(value, int) for key, value in rounding.items()))):
        raise ValueError("rounding must be an integer, projection-column integer map, or null.")
    compiled = compile_spec(raw_spec, branch_fields)
    errors = list(compiled["contract_errors"])
    contract = decomposition.get("answer_requirements", {}).get("query_understanding", {})
    if contract_checks:
        errors.extend(final_contract_errors(compiled, contract))
    if errors:
        raise ValueError("; ".join(errors))
    # Materialize compiler-expanded operations (multiple measures, distinctness) as
    # actual upfront DAG nodes. The executor will use these same operations once.
    executable = nx.DiGraph()
    for name, data in graph.nodes(data=True):
        if data["operator"] in RETRIEVAL:
            executable.add_node(name, **deepcopy(data))
    for left, right in graph.edges:
        if left in executable and right in executable:
            executable.add_edge(left, right)
    mapping = {step["output"]: "__dynamic_calc_" + str(index)
               for index, step in enumerate(compiled["execution_steps"], 1)}
    for step in compiled["execution_steps"]:
        name = mapping[step["output"]]
        selected = [mapping.get(parent, parent) for parent in step["inputs"]]
        params = {key: deepcopy(value) for key, value in step.items()
                  if key not in {"id", "output", "inputs", "operator", "stage"}}
        runtime_step = {**params, "id": name, "operator": step["operator"], "inputs": selected}
        executable.add_node(name, operator=step["operator"], explicit_inputs={**params, "inputs": selected},
                            dynamic_step=runtime_step)
        executable.add_edges_from((parent, name) for parent in selected)
    final_input = mapping.get(compiled["compiled_output"], compiled["compiled_output"])
    executable.add_node(OUTPUT_NODE, operator="Final_Spec", explicit_inputs={}, dynamic_output=True)
    executable.add_node(validate, operator="Validate", explicit_inputs={})
    executable.add_node(explain, operator="Explain", explicit_inputs={})
    executable.add_edges_from([(final_input, OUTPUT_NODE), (OUTPUT_NODE, validate), (validate, explain)])
    if (not nx.is_directed_acyclic_graph(executable)
            or any(not data.get("operator") for _, data in executable.nodes(data=True))
            or any(not nx.has_path(executable, name, explain) for name in executable)):
        raise ValueError("Compiled candidate must preserve a complete acyclic graph with no unused nodes.")
    executable.graph["dynamic_plan"] = {"spec": raw_spec, "compiled_spec": compiled,
        "branch_fields": branch_fields, "branch_processing": branch_processing, "final_input": final_input,
        "selected_reason": str(payload.get("selected_reason", "")), "contract_checks": contract_checks}
    return executable
