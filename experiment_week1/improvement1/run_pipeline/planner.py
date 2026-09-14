"""AOP planner."""

import concurrent.futures

from .common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    nx,
    os,
    re,
)
from .clients import build_llm_messages
from .utils import parse_llm_json


class AdvancedAOPPlanner:

    """
    Acts as the reasoning engine of the Agent-Oriented Pipeline.
    Generates multiple candidate execution paths(set to 3), converts them to Directed Acyclic Graphs (DAGs)
    for parallel execution, and evaluates them using a Reward Model to find the optimal path.
    """

    def __init__(self, llm_client, operator_registry: Dict[str, Any], model: str = LOCAL_MODEL):
        self.client = llm_client
        self.registry = operator_registry
        self.model = model

        #Heuristic Costs for the DAG evaluation
        # Pre-programmed operators (Python/Graph) are cheap and fast.
        # Semantic operators (LLM calls) are expensive and slow.
        #Below numerics based on time-efficiency only
        #This score is used later to prevent lengthy routes
        #Can be further analysed and changed (heavily depends on the model that is being used)
        self.operator_costs = {
            "Retrieve": 2,
            "Query_Spec": 3,
            "Check_Schema": 1,
            "Link": 2,
            "Extract": 2,
            "Generate": 5,
            "Pre_Scan_Validate": 3,
            "Refine": 4,
            "Scan": 1,
            "Validate": 3,
            "Math_Compute": 1,
            "Set_Intersect": 1,
            "Set_Union": 1,
            "Set_Difference": 1,
            "Classify": 2,
            "Filter_Aggregate": 3,
            "Order_By": 2,
            "Integrate": 6,
            "Explain": 8
        }

    def _planner_completion(
        self,
        prompt: str,
        temperature: float | None = None,
        json_output: bool = False,
    ):
        request = {
            "model": self.model,
            "messages": build_llm_messages("planner", prompt),
        }
        if temperature is not None and not self.model.lower().startswith("gpt-5"):
            request["temperature"] = temperature
        return self.client.chat.completions.create(**request)

    #This function generates (using randomness of the LLM), evaluates(above cost heuristics and a separate evaluator
    #where the LLM acts as  judge based on certain laws specified by us (discussed later)), and selects the most
    #efficient one
    def plan_optimal_dag(
        self,
        query: str,
        num_candidates: int = 3,
        planning_round: int = 1,
    ) -> nx.DiGraph:
        """Generates, evaluates, and selects the most efficient execution DAG."""
        if os.getenv("DAG_PLANNER_MODE", "multi_candidate").strip().lower() == "one_shot":
            return self._plan_one_shot_best_dag(query, num_candidates=num_candidates)

        max_planning_rounds = int(os.getenv("DAG_PLANNER_MAX_ROUNDS", "3"))
        print(
            f"--- Planning Round {planning_round}/{max_planning_rounds}: "
            f"Generating {num_candidates} Candidate Paths ---"
        )

        candidate_chains = []

        #Threaded Generation of initial chains
        #temperature is non zero so as to encourage creativity and generation of multiple distinct paths
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_candidates) as chain_runner:
            chains = list(chain_runner.map(lambda _: self._generate_linear_chain(query, temperature=0.3), range(num_candidates)))
            for chain in chains:
                if chain not in candidate_chains:
                    candidate_chains.append(chain)

        print(f"Generated {len(candidate_chains)} unique linear plans.")

        # Thread Worker Function
        #Checks if it is actually a DAG
        def process_candidate(chain_data):
            idx, chain = chain_data
            try:
                dag_data = self._rewrite_to_dag(chain, query, temperature=0.0)
                dag = self._build_networkx_dag(dag_data)

                is_valid, reason = self._validate_planned_dag(dag, query)
                if not is_valid:
                    print(f"\n   -> Evaluating Path {idx + 1}... [REJECTED BY PYTHON: {reason}]")
                    return None

                print(f"\n   -> Evaluating Path {idx + 1}...")
                reward_score = self._evaluate_dag_reward(dag_data, query)  #here we are using the evaluator function defined later where LLM as a judge rates our DAG
                cost = self._calculate_dag_cost(dag)

                print(f"      [System] Path {idx + 1} Final Metrics -> Reward: {reward_score} | Cost: {cost}")
                return (dag, reward_score, cost)
            except Exception as e:
                print(f"   -> Path {idx + 1} failed DAG compilation: {e}")
                return None

        #Threaded Evaluation of DAGs
        evaluated_dags = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_candidates) as executor:
            results = list(executor.map(process_candidate, enumerate(candidate_chains)))
            evaluated_dags = [res for res in results if res is not None]

        if not evaluated_dags:
            if planning_round < max_planning_rounds:
                print("[WARN] No valid dynamic DAGs. Replanning with new candidates.")
                return self.plan_optimal_dag(
                    query,
                    num_candidates=num_candidates,
                    planning_round=planning_round + 1,
                )
            raise RuntimeError("The planner did not produce any valid DAG.")

        highly_rated_dags = [d for d in evaluated_dags if d[1] >= 0.9]

        if highly_rated_dags:
            best_dag_tuple = min(highly_rated_dags, key=lambda x: (x[2], -x[1]))
            print(f"\n--- Selected Optimal DAG (Reward: {best_dag_tuple[1]} | Lowest Cost: {best_dag_tuple[2]}) ---")
            best_dag = best_dag_tuple[0]
        else:
            best_dag_tuple = max(evaluated_dags, key=lambda x: x[1])

            if best_dag_tuple[1] == 0.0:
                if planning_round < max_planning_rounds:
                    print("[WARN] All evaluated DAGs scored 0.0. Replanning with new candidates.")
                    return self.plan_optimal_dag(
                        query,
                        num_candidates=num_candidates,
                        planning_round=planning_round + 1,
                    )
                raise RuntimeError("All dynamically planned DAGs were rejected by the evaluator.")
            else:
                print(f"\n--- Selected Highest Reward Dynamic DAG (Reward: {best_dag_tuple[1]} | Cost: {best_dag_tuple[2]}) ---")
                best_dag = best_dag_tuple[0]

        return best_dag

    def _query_requires_classify(self, query: str) -> bool:
        return bool(re.search(
            r"\b(average|avg|sum|total|min|max|minimum|maximum|count|how many|"
            r"highest|lowest|largest|smallest)\b",
            query,
            flags=re.I,
        ))

    def _operator_position(self, dag: nx.DiGraph, ordered_nodes: list, operator: str) -> int | None:
        for position, node in enumerate(ordered_nodes):
            if dag.nodes[node].get("operator") == operator:
                return position
        return None

    def _validate_planned_dag(self, dag: nx.DiGraph, query: str) -> tuple[bool, str]:
        if not nx.is_directed_acyclic_graph(dag):
            return False, "planned graph contains a cycle"

        ordered_nodes = list(nx.topological_sort(dag))
        operators = [dag.nodes[node].get("operator") for node in ordered_nodes]
        required = ["Retrieve", "Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Validate", "Explain"]
        missing = [operator for operator in required if operator not in operators]
        if missing:
            return False, f"missing required operators: {missing}"

        retrieve_pos = self._operator_position(dag, ordered_nodes, "Retrieve")
        classify_pos = self._operator_position(dag, ordered_nodes, "Classify")
        query_spec_pos = self._operator_position(dag, ordered_nodes, "Query_Spec")
        generate_pos = self._operator_position(dag, ordered_nodes, "Generate")
        pre_scan_validate_pos = self._operator_position(dag, ordered_nodes, "Pre_Scan_Validate")
        scan_pos = self._operator_position(dag, ordered_nodes, "Scan")
        validate_pos = self._operator_position(dag, ordered_nodes, "Validate")
        explain_pos = self._operator_position(dag, ordered_nodes, "Explain")

        if not (retrieve_pos < query_spec_pos < generate_pos < pre_scan_validate_pos < scan_pos < validate_pos < explain_pos):
            return False, "operator order must be Retrieve -> Query_Spec -> Generate -> Pre_Scan_Validate -> Scan -> Validate -> Explain"
        if classify_pos is not None and classify_pos > query_spec_pos:
            return False, "Classify must run before Query_Spec when present"
        if operators[-1] != "Explain":
            return False, "Explain must be the final operator"
        if self._query_requires_classify(query) and classify_pos is None:
            return False, "math/aggregation query should include Classify before Query_Spec"

        required_dependencies = [
            (ordered_nodes[retrieve_pos], ordered_nodes[query_spec_pos], "Retrieve -> Query_Spec"),
            (ordered_nodes[query_spec_pos], ordered_nodes[generate_pos], "Query_Spec -> Generate"),
            (ordered_nodes[generate_pos], ordered_nodes[pre_scan_validate_pos], "Generate -> Pre_Scan_Validate"),
            (ordered_nodes[pre_scan_validate_pos], ordered_nodes[scan_pos], "Pre_Scan_Validate -> Scan"),
            (ordered_nodes[scan_pos], ordered_nodes[validate_pos], "Scan -> Validate"),
            (ordered_nodes[validate_pos], ordered_nodes[explain_pos], "Validate -> Explain"),
        ]
        if classify_pos is not None:
            required_dependencies.append(
                (ordered_nodes[classify_pos], ordered_nodes[query_spec_pos], "Classify -> Query_Spec")
            )
        for source, target, dependency_name in required_dependencies:
            if not nx.has_path(dag, source, target):
                return False, f"missing dependency path: {dependency_name}"

        return True, "valid"

    def _plan_one_shot_best_dag(self, query: str, num_candidates: int = 3) -> nx.DiGraph:
        print(f"--- One-shot DAG planning: internally selecting best of {num_candidates} candidates ---")
        prompt = f"""
You are the one-shot DAG planner for an Agent-Oriented Pipeline.

User Query: "{query}"
Available Operators (use exact names only): {list(self.registry.keys())}

Your internal task:
1. Create {num_candidates} candidate execution chains for the query.
2. Rewrite each candidate chain into a DAG.
3. Evaluate each DAG for correctness and cost.
4. Select the single best DAG.

Planning laws:
- Retrieve must happen before Generate.
- Query_Spec must happen after Retrieve and before Generate.
- If the query asks for math, aggregation, or a numeric superlative using words like average, sum, min, max, count, how many, highest, lowest, largest, or smallest, include Classify before Query_Spec.
- Do not use Classify for simple lookup/listing questions.
- Generate must happen before Pre_Scan_Validate, and Pre_Scan_Validate must happen before Scan.
- Pre_Scan_Validate is an advisory warning pass; Scan may still run after advisory failures unless the SPARQL is not executable.
- Scan must happen before Validate.
- Explain must be the final operator.
- Do not include Refine in the planned DAG; runtime self-healing handles refinement only when Scan fails.
- Avoid unnecessary operators such as Link, Extract, Filter_Aggregate, Order_By, Integrate, and set operators unless they are truly required by the question.
- Prefer the lowest-cost valid DAG.

Return ONLY one JSON object for the selected best DAG using this schema:
{{
  "nodes": [
    {{"id": "unique node id", "operator": "one available operator", "inputs": {{}}}}
  ],
  "edges": [
    {{"source": "upstream node id", "target": "downstream node id"}}
  ],
  "selected_reason": "short reason"
}}
"""
        try:
            api_logger.log_call(query, "Planner_OneShot_Best_DAG")
            response = self._planner_completion(
                prompt,
                temperature=0.2,
                json_output=True,
            )
            result = response.choices[0].message.content
            dag_data = parse_llm_json(result, {}, "Planner_OneShot_Best_DAG")
            if not dag_data.get("nodes"):
                raise ValueError("Planner returned no DAG nodes.")
            dag = self._build_networkx_dag(dag_data)
            is_valid, reason = self._validate_planned_dag(dag, query)
            if not is_valid:
                raise ValueError(f"One-shot DAG rejected by Python validator: {reason}")

            sequence = " -> ".join(dag.nodes[node].get("operator", "") for node in nx.topological_sort(dag))
            cost = self._calculate_dag_cost(dag)
            print(f"--- Selected One-Shot DAG | Cost: {cost} | Sequence: {sequence} ---")
            return dag
        except Exception as e:
            raise RuntimeError(f"One-shot planner failed without using a manual DAG: {e}") from e

    #responsible for first making the linear chains that will later be converted to DAGs based on the ability
    #to make the flow parallel , if feasible
    #this improved efficiency manifolds
    def _generate_linear_chain(self, query: str, temperature: float) -> str:
        prompt = f"""
        Write a step-by-step, linear execution plan to answer this query using ONLY the provided operators.
        Query: "{query}"

        AVAILABLE OPERATORS (EXACT MATCH ONLY): {list(self.registry.keys())}

        CRITICAL LAWS OF EXECUTION (YOU MUST FOLLOW THIS CHRONOLOGY):
        1. You must start by finding the ontology classes. Use 'Retrieve'.
        2. CRITICAL: Use 'Classify' for math, aggregation, or numeric-superlative words such as 'Average', 'Sum', 'Min', 'Max', 'Count', 'Highest', 'Lowest', 'Largest', or 'Smallest'. If the query is only a simple lookup/listing question, skip Classify.
        3. You must build a schema-grounded computation plan with 'Query_Spec' before writing SPARQL.
        4. If querying the knowledge graph, 'Generate' (writing SPARQL) must happen AFTER 'Query_Spec'.
        5. 'Pre_Scan_Validate' must happen immediately AFTER 'Generate' and BEFORE 'Scan'.
        6. 'Scan' must happen AFTER 'Pre_Scan_Validate'. Pre_Scan_Validate is advisory unless SPARQL is not executable.
        7. 'Validate' (checking data) must happen AFTER 'Scan'.
        8. 'Explain' (talking to the user) MUST be the absolute final step.

        CRITICAL RULE: Do NOT invent new operators. You must use the EXACT string names listed above.
        For example, use "Retrieve", do not use "RetrieveDataset" or "Retrieve_Classes".

        Output ONLY the numbered steps.
        """

        api_logger.log_call(query, "Planner_Generate_Chain")
        response = self._planner_completion(prompt, temperature=temperature)
        return response.choices[0].message.content.strip()

    def _rewrite_to_dag(self, linear_chain: str, query: str, temperature: float) -> Dict:
        classify_rule = (
            "Classify is REQUIRED and must have a directed path to Query_Spec."
            if self._query_requires_classify(query)
            else "Classify is optional for this query."
        )
        prompt = f"""
        Rewrite this linear plan into a Directed Acyclic Graph (DAG).
        Preserve all mandatory execution dependencies. Parallelize only genuinely independent optional work.

        User Query: {query}
        Linear Plan: {linear_chain}

        AVAILABLE OPERATORS: {list(self.registry.keys())}
        CRITICAL: Under the 'operator' key in your JSON, you MUST use the exact operator names listed above. Do not invent names.

        MANDATORY DIRECTED DEPENDENCY PATHS:
        - Retrieve -> Query_Spec
        - Query_Spec -> Generate
        - Generate -> Pre_Scan_Validate
        - Pre_Scan_Validate -> Scan
        - Scan -> Validate
        - Validate -> Explain
        - Explain must be the final sink node.
        - {classify_rule}
        - Never place Scan before Pre_Scan_Validate.
        - Pre_Scan_Validate is an advisory warning pass, not a semantic hard gate.
        - Never remove a mandatory dependency merely to create parallelism.

        Output strictly a JSON object with 'nodes' (id, operator, inputs) and 'edges' (source, target).
        """

        api_logger.log_call(query, "Planner_Rewrite_DAG")
        response = self._planner_completion(
            prompt,
            temperature=temperature,
            json_output=True,
        )
        result = response.choices[0].message.content
        dag_data = parse_llm_json(result, {}, "Planner_Rewrite_DAG")
        if not dag_data.get("nodes"):
            raise ValueError("DAG rewrite returned no nodes.")
        return dag_data

    def _build_networkx_dag(self, dag_data: Dict) -> nx.DiGraph:
        dag = nx.DiGraph()
        for node in dag_data.get("nodes", []):
            operator = node.get("operator")
            if operator not in self.registry:
                raise ValueError(f"Unknown operator in planned DAG: {operator}")
            dag.add_node(node["id"], operator=operator, explicit_inputs=node.get("inputs", {}))
        for edge in dag_data.get("edges", []):
            dag.add_edge(edge["source"], edge["target"])
        return dag

    #The main judge function
    #We instruct the LLM to judge our DAGs based on a set of LAWS (can be changed as per our needs) and provide a score
    def _evaluate_dag_reward(self, dag_data: Dict, query: str) -> float:
        """Use Python for structural validity and the LLM only for semantic efficiency."""
        try:
            temp_dag = self._build_networkx_dag(dag_data)
            is_valid, validation_reason = self._validate_planned_dag(temp_dag, query)
            if not is_valid:
                print(f"      [Python Validator] Rejected DAG: {validation_reason}")
                return 0.0
            ordered_nodes = list(nx.topological_sort(temp_dag))
            sequence_str = " -> ".join([temp_dag.nodes[n]["operator"] for n in ordered_nodes])
            optional_operators = [
                temp_dag.nodes[node]["operator"]
                for node in ordered_nodes
                if temp_dag.nodes[node]["operator"]
                not in {"Retrieve", "Classify", "Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Validate", "Explain"}
            ]
        except Exception:
            return 0.0

        prompt = f"""
        You are evaluating the semantic efficiency of a Python-validated AOP DAG.
        Assign a Reward Score between 0.0 and 1.0.

        User Query: "{query}"
        Python-validated Execution Sequence: {sequence_str}
        Optional Operators: {optional_operators}

        Important facts already verified by Python:
        - Retrieve is before Query_Spec.
        - Query_Spec is before Generate.
        - Generate is before Pre_Scan_Validate.
        - Pre_Scan_Validate is before Scan.
        - Scan is before Validate.
        - Validate is before Explain.
        - Explain is final.
        - Classify is before Query_Spec whenever the query requires it.
        - Retrieve, Query_Spec, Generate, Pre_Scan_Validate, Scan, Validate, and Explain are mandatory core operators.
        Do not dispute these facts and do not penalize mandatory core operators.

        Score only whether any optional operators are useful for this specific query:
        - 1.0: efficient and semantically appropriate.
        - 0.5: valid but contains unnecessary optional operators.
        - 0.0: optional operators make the plan semantically unsuitable.

        Output strictly a JSON object: {{"reward_score": 0.0, "reasoning": "Brief explanation"}}
        """
        try:

            api_logger.log_call(query, "Planner_Evaluate_DAG")
            response = self._planner_completion(
                prompt,
                temperature=0.0,
                json_output=True,
            )
            result = response.choices[0].message.content
            evaluation = parse_llm_json(
                result,
                {"reward_score": 0.0, "reasoning": "Evaluator did not return valid JSON."},
                "Planner_Evaluate_DAG",
            )
            if isinstance(evaluation, list):
                evaluation = next((item for item in evaluation if isinstance(item, dict)), {})
            if not isinstance(evaluation, dict):
                evaluation = {
                    "reward_score": 0.0,
                    "reasoning": "Evaluator returned a non-object response.",
                }

            raw_score = max(0.0, min(1.0, float(evaluation.get("reward_score", 0.0))))
            adjusted_score = max(0.5, raw_score)
            print(
                f"      [Evaluator] Semantic Score: {raw_score} | "
                f"Adjusted Valid-DAG Score: {adjusted_score} | "
                f"Reason: {evaluation.get('reasoning')}"
            )
            return adjusted_score
        except Exception as e:
            print(f"      [Evaluator] Semantic scoring failed: {e}. Using valid-DAG score 0.5.")
            return 0.5

    def _calculate_dag_cost(self, dag: nx.DiGraph) -> int:
        """
        Calculates the heuristic cost of the DAG.
        Cost = Sum of all operator base costs + Depth Penalty (latency).
        """
        total_cost = 0

        # Sum base costs
        for node in dag.nodes:
            op_name = dag.nodes[node]["operator"]
            total_cost += self.operator_costs.get(op_name, 5) # Default penalty if unknown

        # Add penalty for critical path length (latency)
        critical_path_length = nx.dag_longest_path_length(dag)
        total_cost += (critical_path_length * 2)

        return total_cost
