from typing import Any, Callable

import networkx as nx


def fallback_backend_for_query(query: str) -> str:
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


def build_subquery_dag(query: str, nodes: list[dict[str, Any]]) -> nx.DiGraph:
    if not nodes:
        fallback_backend = fallback_backend_for_query(query)
        print(f"[WARN] Decomposition returned empty. Falling back to single {fallback_backend} node.")
        nodes = [{
            "id": "Q1",
            "description": query,
            "operator": "Subquery",
            "backend": fallback_backend,
            "inputs": [],
            "outputs": [],
        }]

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

    if not nx.is_directed_acyclic_graph(dag):
        print("[WARN] Generated DAG has cycles. Falling back to simple DAG.")
        dag = nx.DiGraph()
        dag.add_node("Q1", id="Q1", description=query, operator="Subquery", backend=fallback_backend_for_query(query), inputs=[], outputs=[])
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
        decompose_result = self.decompose_fn({"query": query}, self.client, self.model)
        return build_subquery_dag(query, decompose_result.get("nodes", []))
