"""Three upfront DAG candidates, with improvement3 reward/cost selection."""
from copy import deepcopy
import json
import math
import os

import networkx as nx

from .common import LOCAL_MODEL, api_logger
from .clients import build_llm_messages
from .utils import parse_llm_json
from .dynamic_dag import CALCULATIONS, graph_fingerprint, graph_payload, validate_candidate


OPERATOR_GUIDE = """
Use exact schema columns and explicit ordered dataset inputs. Each calculation
node inputs object contains input (one node ID) or inputs (ordered node IDs).
- Integrate: inputs:[left,right], left_on:[...], right_on:[...],
  join_type:inner|left|right|outer|cross. Cardinality may be declared only when
  schema uniqueness or prior grouping establishes it. Ordinary null keys do not
  match. Same-name non-key columns from the right acquire _right, then _right_2.
- Filter_Aggregate: operation:sum|avg|min|max|count|count_rows|count_distinct,
  target_column, output_column, group_by:[...]. After aggregation only grouping
  keys and the output metric remain. Several measures can use aggregations:
  [{operation,input_column,output_column}], with a shared input and group_by.
  For predicates use operation:filter, filters:[{field,operator,value,value_type}].
  Nested all/any/not preserve AND/OR/NOT. HAVING predicates follow aggregation.
- Math_Compute: expression such as column('total') / column('count'), output_column.
  Expressions use existing fields, arithmetic and supported safe functions;
  no Python statements, arbitrary code or invented domain constants.
- Order_By: order_by:[{column,direction:ASC|DESC,nulls:first|last}], optional limit.
- Date_Extract: input_column, part:year|month|day, output_column.
- Bucket: input_column, output_column,
  rules:[{min,max,min_inclusive,max_inclusive,label}], optional default.
- Set_Intersect / Set_Difference / Difference: inputs:[left,right], left_on, right_on,
  distinct:false preserves left multiplicity; nulls_equal:false follows SQL EXISTS.
- Set_Union / Union: inputs:[...], optional join_key and distinct policy.
- Distinct: input, distinct_on:[...]. Only deduplicate when requested.
- Combine_Scalars: inputs:[...]; each input must produce one row, with distinct
  output metric names. Do not use it to combine arbitrary multirow relations.

Choose grain and population from the question and supplied definitions, not from
operator names. Independent multirow fact sources can multiply observations when
joined raw. Summarize per entity first only when the requested metric calls for
entity summaries. An observation average differs from an average of entity
averages; carry sums and non-null counts when required. Lookup dimension joins
may precede aggregation. Preserve duplicates, NULLs, absent-related-record logic,
exact literals, signs, grouping ownership and required participation. Never fix
multiplicity by dropping arbitrary records. Do not invent metrics or definitions.
Use outer joins when the requested base population must survive missing facts.
Sorting and limit must apply to the requested final metric, with requested ties.
Aliases are calculation outputs, not physical fields to retrieve.
"""


class AdvancedAOPPlanner:
    """Reuse the legacy candidate mechanism with current SQL/spec contracts."""
    def __init__(self, llm_client, operator_registry, model=None, global_schema=None, contract_checks=True):
        self.client = llm_client
        self.registry = operator_registry
        self.model = model or LOCAL_MODEL
        self.global_schema = global_schema or {}
        self.contract_checks = contract_checks
        self.last_planning = {}
        # Improvement3's heuristic: operator weights plus twice graph depth.
        # These are ranking weights, not measured dollars or concurrent latency.
        self.operator_costs = {"Query_Spec": 3, "Generate": 5, "Pre_Scan_Validate": 3,
            "Scan": 1, "Processing_Spec": 3, "Final_Spec": 3, "Validate": 3,
            "Explain": 8, "Math_Compute": 1, "Filter_Aggregate": 3, "Order_By": 2,
            "Integrate": 6, "Date_Extract": 1, "Bucket": 1,
            **{name: 1 for name in CALCULATIONS if name not in {"Math_Compute", "Filter_Aggregate", "Order_By", "Integrate"}}}

    def plan_optimal_dag_from_decomposition(self, query, decomposition, num_candidates=3,
                                            consultation_session=None, **kwargs):
        diagnostics = {"mode": "dynamic", "candidates": [], "fallback": False}
        self.last_planning = diagnostics
        if self.client is None:
            return self._fallback(query, decomposition, diagnostics, "No planner client supplied.")
        rounds = int(os.getenv("DAG_PLANNER_MAX_ROUNDS", "3"))
        if rounds < 1 or rounds > 3 or num_candidates != 3:
            raise ValueError("Use three candidates and DAG_PLANNER_MAX_ROUNDS between 1 and 3.")
        seen, feedback = set(), []
        for planning_round in range(1, rounds + 1):
            evaluated = []
            print(f"[PLANNER] Round {planning_round}/{rounds}: generating 3 upfront DAG candidates")
            # Sequential calls keep the existing mutable consultation session safe.
            for index in range(1, 4):
                entry = {"round": planning_round, "candidate": index}
                diagnostics["candidates"].append(entry)
                try:
                    generate = lambda inputs: self._generate_dag_from_decomposition(
                        query, decomposition, index, feedback[-6:], inputs)
                    payload = (consultation_session.run("Planner", generate, {})
                               if consultation_session else generate({}))
                    entry["dag"] = deepcopy(payload)
                    dag = validate_candidate(payload, decomposition, self.global_schema, self.registry, self.contract_checks)
                    fingerprint = graph_fingerprint(dag)
                    if fingerprint in seen:
                        entry["status"] = "duplicate"
                        continue
                    seen.add(fingerprint)
                    entry.update(status="valid", cost=self._calculate_dag_cost(dag))
                    score, reason = self._evaluate_decomposition_dag_reward(
                        payload, query, decomposition, consultation_session=consultation_session)
                    entry.update(reward_score=score, evaluation_reason=reason)
                    evaluated.append((dag, score, entry["cost"], entry))
                except Exception as exc:
                    from .consultation import InterpretationRevised
                    if isinstance(exc, InterpretationRevised) or self._service_error(exc):
                        entry.update(status="interrupted", errors=[str(exc)])
                        raise
                    entry.update(status="rejected", errors=[str(exc)])
                    feedback.append(str(exc))
                    print(f"[PLANNER] Candidate {index} rejected: {exc}")
            if evaluated:
                rated = [item for item in evaluated if item[1] is not None and item[1] >= 0.9]
                scored = [item for item in evaluated if item[1] is not None]
                if rated:
                    best = min(rated, key=lambda item: (item[2], -item[1]))
                    rule = "lowest_cost_with_reward_at_least_0.9"
                elif scored:
                    best = max(scored, key=lambda item: (item[1], -item[2]))
                    rule = "highest_reward"
                else:
                    best = min(evaluated, key=lambda item: item[2])
                    rule = "lowest_cost_valid_evaluation_unavailable"
                dag, score, cost, entry = best
                entry["status"] = "selected"
                diagnostics.update(selection_rule=rule, selected_round=planning_round,
                    selected_candidate=entry["candidate"], reward_score=score, cost=cost,
                    selected_dag=graph_payload(dag))
                dag.graph["planning"] = deepcopy(diagnostics)
                print(f"[PLANNER] Selected candidate {entry['candidate']}: reward={score}, cost={cost}")
                return dag
        return self._fallback(query, decomposition, diagnostics, "No valid candidate after bounded planning rounds.")

    def _fallback(self, query, decomposition, diagnostics, reason):
        diagnostics.update(fallback=True, fallback_reason=reason, selection_rule="original_fixed_pipeline")
        dag = self._build_three_spec_dag(query, decomposition)
        diagnostics["selected_dag"] = graph_payload(dag)
        dag.graph["planning"] = deepcopy(diagnostics)
        print("[PLANNER] Explicit fallback to fixed retrieval-and-calculation pipeline: " + reason)
        return dag

    @staticmethod
    def _service_error(exc):
        from . import utils
        return any(getattr(utils, name, lambda value: False)(exc)
                   for name in ("is_quota_exhaustion_error", "is_transient_connection_error"))

    def _generate_dag_from_decomposition(self, query, decomposition, index, feedback, consultation_inputs):
        from .business_context import business_context_prompt
        from .knowledge import planning_schema
        from .consultation import consultation_prompt
        sources = {b.get("source_class") for b in decomposition.get("subquestions", [])}
        schema = planning_schema({name: details for name, details in self.global_schema.items() if name in sources})
        strategies = ["Prefer the simplest equivalent graph.",
                      "Consider valid per-source summaries when the requested grain allows them.",
                      "Consider a different valid join or operation order; preserve exact semantics."]
        prompt = f"""Plan one complete execution DAG BEFORE any retrieval SQL or Scan is run.
Question: {query}
Selected decomposition (preserve every branch and requirement): {json.dumps(decomposition)}
Declared schema and supplied YAML metadata: {json.dumps(schema)}
Authoritative business context: {business_context_prompt()}
Candidate strategy {index}: {strategies[index - 1]}
Prior candidate errors to repair: {json.dumps(feedback)}
Supported calculation operators: {sorted(CALCULATIONS)}
{OPERATOR_GUIDE}

Return nodes:[{{id,operator,inputs}}], edges:[{{source,target}}],
final_output:"node_id", projection:["requested_field",...], selected_reason:"brief reason".
Optional top-level distinct, distinct_on, rounding, assumptions use the existing
calculation contract. Do not include database rows, guessed results or SQL.

For EACH selected subquestion create exactly one own-source retrieval branch:
Query_Spec -> Generate -> Pre_Scan_Validate -> Scan -> Processing_Spec.
Every retrieval node inputs has subquestion_id. Query_Spec inputs also has
required_fields:[exact raw columns needed for calculations, output, keys and
the decomposition requirements]. It remains a RAW RETRIEVAL contract, not math.
Choose branch columns upfront; include every later operand and connection key.
Do not cross-wire retrieval branches. Other retrieval-stage inputs are empty
apart from subquestion_id. Calculations consume Processing_Spec node IDs or
earlier calculation node IDs. All dataset input IDs MUST match incoming edges;
inputs:[left,right] specifies join/set operand order. No implicit previous input.
Create only calculations required by the question, in a valid dependency order.
Put EVERY calculation parameter inside that node's inputs OBJECT, including
operation, group_by, rules, join keys and order_by. The node itself has only
id, operator, inputs. For example:
{{"id":"counts","operator":"Filter_Aggregate","inputs":{{"input":"q1_rows",
"operation":"count","target_column":"id","output_column":"record_count",
"group_by":["category"]}}}}
A join node's inputs object must contain inputs:["left_node","right_node"]
and left_on/right_on. Do not substitute left/right properties for that ordered
list. Return the complete outer object with nodes, edges, final_output and
projection; never return a standalone node or a list of nodes.
Use exactly one Validate fed by final_output, and one Explain fed by Validate.
Every node contributes to that output; no disconnected or unused operations.
Do not include Retrieve, Decompose, Refine or Final_Spec: preparation already
ran, repair is local, and the compiler attaches final output handling itself.
No second DAG is generated after Scan. No made-up columns or operators.

Example simple lookup (replace branch, source columns and node IDs):
{{"nodes":[
 {{"id":"q1_spec","operator":"Query_Spec","inputs":{{"subquestion_id":"q1","required_fields":["id","name"]}}}},
 {{"id":"q1_gen","operator":"Generate","inputs":{{"subquestion_id":"q1"}}}},
 {{"id":"q1_check","operator":"Pre_Scan_Validate","inputs":{{"subquestion_id":"q1"}}}},
 {{"id":"q1_scan","operator":"Scan","inputs":{{"subquestion_id":"q1"}}}},
 {{"id":"q1_rows","operator":"Processing_Spec","inputs":{{"subquestion_id":"q1"}}}},
 {{"id":"validate","operator":"Validate","inputs":{{}}}},
 {{"id":"explain","operator":"Explain","inputs":{{}}}}],
 "edges":[{{"source":"q1_spec","target":"q1_gen"}},{{"source":"q1_gen","target":"q1_check"}},
 {{"source":"q1_check","target":"q1_scan"}},{{"source":"q1_scan","target":"q1_rows"}},
 {{"source":"q1_rows","target":"validate"}},{{"source":"validate","target":"explain"}}],
 "final_output":"q1_rows","projection":["name"],"selected_reason":"lookup"}}
""" + consultation_prompt(consultation_inputs)
        api_logger.log_call(query, "Planner_Decomposition_DAG")
        return self._completion(prompt, 0.25, "Planner_Decomposition_DAG")

    def _completion(self, prompt, temperature, stage):
        response = self.client.chat.completions.create(model=self.model,
            messages=build_llm_messages("planner", prompt),
            **({} if self.model.lower().startswith("gpt-5") else {"temperature": temperature}))
        if not response.choices or getattr(response.choices[0], "finish_reason", None) == "length":
            raise ValueError(stage + ": missing or truncated model output.")
        payload = parse_llm_json(response.choices[0].message.content, None, stage)
        if not isinstance(payload, dict):
            raise ValueError(stage + ": return one JSON object.")
        if stage == "Planner_Decomposition_DAG" and not payload.get("nodes"):
            for key in ("dag", "graph", "pipeline", "execution_graph"):
                nested = payload.get(key)
                if isinstance(nested, dict) and nested.get("nodes"):
                    payload = {**{k: v for k, v in payload.items() if k != key}, **nested}
                    break
        return payload

    def _evaluate_decomposition_dag_reward(self, payload, query, decomposition, consultation_session=None):
        from .business_context import business_context_prompt
        from .knowledge import planning_schema
        sources = {b.get("source_class") for b in decomposition.get("subquestions", [])}
        prompt = f"""Evaluate this locally validated upfront DAG for the original question.
Question: {query}
Decomposition and resolved requirements: {json.dumps(decomposition)}
Schema: {json.dumps(planning_schema({k:v for k,v in self.global_schema.items() if k in sources}))}
Business context: {business_context_prompt()}
Specialist advice used during planning: {json.dumps(getattr(consultation_session, 'advice', []))}
COMPLETE DAG (check parameters and ordered inputs, not only operator sequence): {json.dumps(payload)}
{OPERATOR_GUIDE}
Reward 0..1: 1 implements the exact population, metrics, weighting, grouping,
joins, filters and ranking without unnecessary work; 0 is semantically unsuitable.
Structural validity alone is not semantic correctness. Return only
{{"reward_score":0.0,"reasoning":"brief explanation"}}.
"""
        try:
            api_logger.log_call(query, "Planner_Evaluate_Decomposition_DAG")
            value = self._completion(prompt, 0.0, "Planner_Evaluate_Decomposition_DAG")
            raw = value.get("reward_score")
            if isinstance(raw, bool) or not isinstance(raw, (float, int)) or not math.isfinite(raw) or not 0 <= raw <= 1:
                raise ValueError("Evaluator must return a finite reward_score between 0 and 1.")
            return float(raw), str(value.get("reasoning", ""))
        except Exception as exc:
            if self._service_error(exc):
                raise
            # Keep structurally valid candidates usable, but never fabricate a reward.
            return None, "Evaluation unavailable: " + str(exc)

    def _calculate_dag_cost(self, dag):
        return sum(self.operator_costs.get(data["operator"], 5) for _, data in dag.nodes(data=True)) + 2 * nx.dag_longest_path_length(dag)

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
