"""Build the fixed retrieval-and-calculation flow; no model-generated DAGs."""
import networkx as nx


class AdvancedAOPPlanner:
    """Compatibility entrypoint for the fixed V4 pipeline."""
    def __init__(self, llm_client, operator_registry, model=None):
        self.registry = operator_registry

    def plan_optimal_dag_from_decomposition(self, query, decomposition, **kwargs):
        return self._build_three_spec_dag(query, decomposition)

    def _build_three_spec_dag(self, query, decomposition):
        dag = nx.DiGraph()
        branches = decomposition.get("subquestions", []) or [{"id": "q1", "question": query}]
        processed = []
        for index, branch in enumerate(branches, 1):
            branch_id = str(branch.get("id") or f"q{index}")
            previous = None
            for operator in ["Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Processing_Spec"]:
                node = branch_id + "_" + operator.lower()
                if node in dag:
                    raise ValueError("Duplicate retrieval branch ID: " + branch_id)
                dag.add_node(node, operator=operator, explicit_inputs={"subquestion_id": branch_id})
                if previous:
                    dag.add_edge(previous, node)
                previous = node
            processed.append(previous)
        dag.add_node("final_spec", operator="Final_Spec", explicit_inputs={})
        for node in processed:
            dag.add_edge(node, "final_spec")
        dag.add_node("validate", operator="Validate", explicit_inputs={})
        dag.add_node("explain", operator="Explain", explicit_inputs={})
        dag.add_edge("final_spec", "validate")
        dag.add_edge("validate", "explain")
        return dag
