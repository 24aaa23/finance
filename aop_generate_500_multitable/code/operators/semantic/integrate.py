import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_integrate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Integrate
    Purpose: Merges the results of parallel DAG branches into a single, cohesive final output.
    """
    prompt = f"""
    The next operator is Integrate.
    You are receiving data from multiple parallel execution branches. Your task is to synthesize
    this information to answer the original user query.

    User Query: "{inputs.get('query')}"

    Branch 1 Data: {json.dumps(inputs.get('branch_1_output', {}))}
    Branch 2 Data: {json.dumps(inputs.get('branch_2_output', {}))}

    Cross-reference the data from both branches and output the final, integrated answer.
    """

    api_logger.log_call(inputs.get('query'), "Integrate")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.2
    )
    return {"integrated_result": response.choices[0].message.content.strip()}

