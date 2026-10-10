from typing import Any, Callable
import copy
import os

import networkx as nx


def fallback_backend_for_query(query: str) -> str:
    if os.getenv("PIPELINE_BACKEND_MODE", "hybrid") == "sql_only":
        return "SQL"
    q = f" {str(query or '').lower()} "
    sql_markers = [
        " count ", " how many ", " average ", " avg ", " sum ", " total ",
        " highest ", " lowest ", " top ", " bottom ", " rank ", " ranking ",
        " compare ", " across ", " per ", " grouped by ", " by ",
        " maximum ", " minimum ", " largest ", " smallest ",
    ]
    return "SQL" if any(marker in q for marker in sql_markers) else "KG"


SET_OPERATOR_CANONICAL_NAMES = {
    "set_intersect": "Set_Intersect",
    "set_intersection": "Set_Intersect",
    "intersect": "Set_Intersect",
    "set_union": "Set_Union",
    "union": "Set_Union",
    "set_merge": "Set_Union",
    "set_combine": "Set_Union",
    "set_difference": "Set_Difference",
    "set_diff": "Set_Difference",
    "set_except": "Set_Difference",
    "set_minus": "Set_Difference",
    "except": "Set_Difference",
    "difference": "Set_Difference",
    "minus": "Set_Difference",
}


def canonicalize_set_operator(operator_name: str) -> str:
    """Map a decomposition-emitted set-operator spelling to its registry name.

    The decomposition prompt names Set_Intersect/Set_Union but the LLM
    occasionally emits a plausible synonym (Set_Diff, Set_Except, Intersection)
    instead. The registry only recognizes the exact canonical names, and an
    unrecognized operator previously crashed the executor outright. This
    normalization is a fixed lookup table, not an LLM call, so the set
    operators themselves remain fully deterministic.
    """
    key = str(operator_name or "").strip().lower()
    return SET_OPERATOR_CANONICAL_NAMES.get(key, operator_name)


def build_subquery_dag(query: str, nodes: list[dict[str, Any]], *, strict: bool = False) -> nx.DiGraph:
    nodes = copy.deepcopy(nodes)
    fallback_backend = fallback_backend_for_query(query)
    if not isinstance(nodes, list) or any(
        not isinstance(node, dict) or not isinstance(node.get("id"), str)
        or not isinstance(node.get("inputs", []), list)
        or not isinstance(node.get("outputs", []), list)
        or any(not isinstance(item, dict) for item in node.get("inputs", []) + node.get("outputs", []))
        for node in nodes
    ):
        if strict:
            raise ValueError('Malformed node IDs, inputs or outputs')
        nodes = []
    # Validate executable operators and complete field bindings before any
    # model/scan work. A SQL verb is not an executor operator. Reject the plan
    # as a whole rather than silently skipping one of the user's conditions.
    if nodes:
        if os.getenv('PIPELINE_BACKEND_MODE', 'hybrid') == 'sql_only' and any(
                node.get('backend') not in (None, 'SQL') or (
                    node.get('operator', 'Subquery') == 'Subquery' and node.get('backend') != 'SQL')
                for node in nodes):
            if strict:
                raise ValueError('SQL-only mode requires SQL subqueries')
            print('[WARN] Non-SQL plan rejected for SQL-only ablation.')
            nodes = []
        backends = {node.get('backend') for node in nodes if node.get('backend') in ('SQL', 'KG')}
        if len(backends) == 1:
            fallback_backend = next(iter(backends))
        by_id = {node['id']: node for node in nodes}
        supported = {'Subquery', 'Set_Intersect', 'Set_Union', 'Set_Difference'}
        valid = len(by_id) == len(nodes) and all(by_id)
        for node in nodes:
            operator = node.get('operator') or ('Subquery' if node.get('backend') else 'Set_Intersect')
            operator = 'Subquery' if str(operator).casefold() == 'subquery' else canonicalize_set_operator(operator)
            # A single database node with a SQL verb still denotes one complete
            # backend query. Its description is restored verbatim below.
            if len(nodes) == 1 and node.get('backend') in ('SQL', 'KG') and operator not in supported:
                operator = 'Subquery'
            node['operator'] = operator
            valid &= operator in supported
            if operator == 'Subquery':
                valid &= node.get('backend', 'KG') in ('SQL', 'KG')
            for inp in node.get('inputs', []):
                source = inp.get('source')
                if not isinstance(source, str) or source.count('.') != 1:
                    valid = False
                    continue
                predecessor, field = source.split('.')
                outputs = by_id.get(predecessor, {}).get('outputs', [])
                valid &= bool(inp.get('name')) and predecessor != node['id'] and any(
                    output.get('name') == field for output in outputs)
        if not valid:
            if strict:
                raise ValueError('Duplicate/empty node IDs, unsupported operators or invalid output bindings')
            print('[WARN] Decomposition has unsupported operators or invalid bindings; preserving the full question in one backend node.')
            nodes = []
    if not nodes:
        if strict:
            raise ValueError('Empty or rejected decomposition')
        print(f"[WARN] Decomposition returned empty. Falling back to single {fallback_backend} node.")
        nodes = [{
            "id": "Q1",
            "description": query,
            "operator": "Subquery",
            "backend": fallback_backend,
            "inputs": [],
            "outputs": [],
        }]

    # A single backend node is the entire question, so a model paraphrase
    # must not replace the user's predicates or invent a metric definition.
    if len(nodes) == 1 and nodes[0].get("operator", "Subquery") == "Subquery":
        # These are inter-node bindings, not a final-answer schema. No consumer
        # exists in a one-node DAG; speculative aliases/types must not constrain
        # the actual QuerySpec output.
        nodes = [{**nodes[0], "description": query, "inputs": [], "outputs": []}]

    dag = nx.DiGraph()
    for node in nodes:
        node_id = node.get("id")
        if "operator" not in node or not node["operator"]:
            node["operator"] = "Subquery" if node.get("backend") else "Set_Intersect"
        elif node["operator"] != "Subquery":
            node["operator"] = canonicalize_set_operator(node["operator"])
        dag.add_node(node_id, **node)

    for node in nodes:
        node_id = node.get("id")
        for inp in node.get("inputs", []):
            source = inp.get("source", "")
            if "." not in source:
                continue
            source_node, source_field = source.split(".", 1)
            if source_node in dag.nodes:
                dag.add_edge(
                    source_node,
                    node_id,
                    field=inp.get("name"),
                    source_field=source_field,
                    type=inp.get("type"),
                )

    if not nx.is_directed_acyclic_graph(dag) or (len(dag) > 1 and sum(dag.out_degree(n) == 0 for n in dag) != 1):
        if strict:
            raise ValueError('DAG has cycles or does not have exactly one final result')
        print("[WARN] Generated DAG has cycles or no single final result. Falling back to simple DAG.")
        dag = nx.DiGraph()
        dag.add_node("Q1", id="Q1", description=query, operator="Subquery", backend=fallback_backend, inputs=[], outputs=[])
    for node in dag:
        if dag.out_degree(node) == 0 and dag.nodes[node].get('operator') == 'Subquery':
            dag.nodes[node]['outputs'] = []
    return dag


class AdvancedAOPPlanner:
    def __init__(
        self,
        llm_client: Any,
        operator_registry: dict[str, Any],
        decompose_fn: Callable[[dict[str, Any], Any, str], dict[str, Any]],
        model: str,
    ):
        self.client = llm_client
        self.registry = operator_registry
        self.decompose_fn = decompose_fn
        self.model = model

    def plan_optimal_dag(
        self,
        query: str,
        num_candidates: int = 3,
        planning_round: int = 1,
    ) -> nx.DiGraph:
        del num_candidates, planning_round
        print("--- Planning DAG using semantic_decompose ---")
        inputs = {"query": query}
        nodes = []
        failures = []
        for attempt in range(4):  # Initial proposal plus three repair attempts.
            decompose_result = self.decompose_fn(inputs, self.client, self.model)
            nodes = decompose_result.get("nodes", []) if isinstance(decompose_result, dict) else []
            try:
                dag = build_subquery_dag(query, nodes, strict=True)
            except ValueError as error:
                reason = (decompose_result.get('decomposition_error')
                          if isinstance(decompose_result, dict) else None) or str(error)
                failures.append(str(reason))
                print(f'[DAG RETRY] Proposal {attempt + 1}/4 rejected: {reason}', flush=True)
                inputs = {"query": query, "decomposition_feedback": str(reason),
                          "previous_decomposition": decompose_result}
            else:
                dag.graph.update(decomposition_attempts=attempt + 1,
                                 decomposition_failures=failures, decomposition_fallback=False)
                return dag
        print('[DAG RETRY] Three retries exhausted; using single-query fallback.', flush=True)
        dag = build_subquery_dag(query, nodes)
        dag.graph.update(decomposition_attempts=4, decomposition_failures=failures,
                         decomposition_fallback=True)
        return dag
