"""Run the complete AOP pipeline locally with Gemma 4 26B."""

import os
import runpy


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11440/v1")
GEMMA_MODEL = "gemma4:26b"

# Every LLM role uses the local Gemma 4 26B model.
os.environ["LLM_MODEL"] = GEMMA_MODEL
os.environ["PLANNER_MODEL"] = GEMMA_MODEL
os.environ["REFINE_MODEL"] = GEMMA_MODEL
os.environ["VALIDATE_MODEL"] = GEMMA_MODEL
os.environ["EXPLAIN_MODEL"] = GEMMA_MODEL
os.environ["OPENAI_SPARQL_MODEL"] = GEMMA_MODEL

# Reuse Ollama's OpenAI-compatible endpoint for planner and SPARQL clients.
os.environ["LLM_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_BASE_URL"] = OLLAMA_BASE_URL
os.environ["OPENAI_API_KEY"] = "local-model"

# Keep this experiment independent from the GPT-assisted Gemma report.
os.environ["PIPELINE_VERSION"] = "gemma4-26b-all-local-path-validation-v5"
os.environ["REPORT_FILE"] = os.path.join(
    SCRIPT_DIR,
    "Pipeline_Outputs",
    "Pipeline_Retest_Report_gemma4_26b_all_local.csv",
)

base_globals = runpy.run_path(
    os.path.join(SCRIPT_DIR, "firstcheck_gemma4_26b.py"),
    run_name="gemma4_26b_base",
)
BasePlanner = base_globals["AdvancedAOPPlanner"]
parse_llm_json = base_globals["parse_llm_json"]
api_logger = base_globals["api_logger"]
nx = base_globals["nx"]


class GemmaAllLocalPlanner(BasePlanner):
    """Base AOP planner with schema-constrained Gemma DAG output."""

    def _validate_planned_dag(self, dag, query: str):
        """Validate graph dependencies without relying on one topological order."""
        if not nx.is_directed_acyclic_graph(dag):
            return False, "planned graph contains a cycle"

        operator_nodes = {}
        for node in dag.nodes:
            operator = dag.nodes[node].get("operator")
            operator_nodes.setdefault(operator, []).append(node)

        required = ["Retrieve", "Generate", "Scan", "Validate", "Explain"]
        missing = [operator for operator in required if not operator_nodes.get(operator)]
        if missing:
            return False, f"missing required operators: {missing}"

        def has_operator_path(source_operator: str, target_operator: str) -> bool:
            return any(
                nx.has_path(dag, source, target)
                for source in operator_nodes.get(source_operator, [])
                for target in operator_nodes.get(target_operator, [])
            )

        for source_operator, target_operator in [
            ("Retrieve", "Generate"),
            ("Generate", "Scan"),
            ("Scan", "Validate"),
            ("Validate", "Explain"),
        ]:
            if not has_operator_path(source_operator, target_operator):
                return False, f"missing dependency path: {source_operator} -> {target_operator}"

        classify_nodes = operator_nodes.get("Classify", [])
        if self._query_requires_classify(query) and not classify_nodes:
            return False, "math/aggregation query should include Classify before Generate"
        if classify_nodes and not has_operator_path("Classify", "Generate"):
            return False, "missing dependency path: Classify -> Generate"

        sink_nodes = [node for node in dag.nodes if dag.out_degree(node) == 0]
        if not sink_nodes or any(dag.nodes[node].get("operator") != "Explain" for node in sink_nodes):
            return False, "Explain must be the only final sink operator"

        explain_nodes = operator_nodes["Explain"]
        for node in dag.nodes:
            if dag.nodes[node].get("operator") == "Explain":
                continue
            if not any(nx.has_path(dag, node, explain_node) for explain_node in explain_nodes):
                return False, f"node {node} has no directed path to Explain"

        return True, "valid"

    def _rewrite_to_dag(self, linear_chain: str, query: str, temperature: float):
        classify_rule = (
            "Classify is REQUIRED and must have a directed path to Generate."
            if self._query_requires_classify(query)
            else "Classify is optional for this query."
        )
        operator_names = list(self.registry.keys())
        dag_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["nodes", "edges"],
            "properties": {
                "nodes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "operator", "inputs"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "operator": {"type": "string", "enum": operator_names},
                            "inputs": {"type": "object"},
                        },
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["source", "target"],
                        "properties": {
                            "source": {"type": "string", "minLength": 1},
                            "target": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        }
        prompt = f"""
Rewrite this linear plan into a Directed Acyclic Graph (DAG).
Preserve mandatory dependencies and parallelize only independent optional work.

User Query: {query}
Linear Plan: {linear_chain}
Available Operators: {operator_names}

Required directed paths:
- Retrieve -> Generate
- Generate -> Scan
- Scan -> Validate
- Validate -> Explain
- {classify_rule}

Explain must be the final sink. Return only the schema-constrained DAG JSON.
"""
        api_logger.log_call(query, "Planner_Rewrite_DAG_Structured")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "aop_dag",
                    "strict": True,
                    "schema": dag_schema,
                },
            },
        )
        dag_data = parse_llm_json(
            response.choices[0].message.content,
            {},
            "Planner_Rewrite_DAG_Structured",
        )
        if not dag_data.get("nodes"):
            raise ValueError("DAG rewrite returned no nodes.")
        return dag_data


# main() resolves this class from the base script's live global namespace.
base_globals["main"].__globals__["AdvancedAOPPlanner"] = GemmaAllLocalPlanner
base_globals["main"]()
