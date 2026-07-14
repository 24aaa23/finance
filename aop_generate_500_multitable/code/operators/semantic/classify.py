import re
import json
from typing import Dict, Any, List
from code.operators.base import parse_llm_json, repair_sparql_query, build_schema_generation_rules, strip_llm_reasoning_blocks
from code.config import api_logger, LOCAL_MODEL, LLMClient

def semantic_classify_query(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_classify_query ---")

    # We now pull the schema so the LLM can check datatypes
    schema_details = inputs.get('schema_details', {})

    prompt = f"""
    The next operator is Classify.
    Analyze the user query and classify its primary analytical intent.

    User Query: "{inputs.get('query')}"
    Schema & Datatypes: {json.dumps(schema_details, indent=2)}

    CRITICAL RULE (DATATYPE CHECK):
    If the user is asking for a mathematical calculation (Average, Sum, Min, Max) on a specific field, check the Schema to see whether that exact field is numeric.
    If that exact field is explicitly a 'categorical_string', the requested calculation is mathematically unsupported.
    In that case, you MUST classify the intent strictly as "out_of_domain_unanswerable".
    Never infer the target field from an example or another query. If the field cannot be identified in the schema, use "aggregation_numeric" and schema_datatype "unknown" so later operators can validate it.

    WARNING: Do NOT abort simple retrieval or lookup queries. A categorical string can still be retrieved and displayed.
    ONLY return out_of_domain_unanswerable if the user explicitly asks to perform MATHEMATICAL AGGREGATION (Average, Sum, Math) on a field that is listed as a 'categorical_string'.

    Possible Intents:
    - "point_lookup" (Fetching facts for a specific entity)
    - "aggregation_numeric" (Valid math on numeric fields)
    - "out_of_domain_unanswerable" (Attempting math on text fields)
    - "boolean_comparison" (Yes/No questions)
    - "taxonomic_reasoning" (Grouping by categories)

    Output strictly a JSON object:
    {{"intent": "intent_name", "confidence": 0.0_to_1.0, "target_field": "exact field requested by the user", "schema_datatype": "numeric|categorical_string|unknown", "reason": "brief schema-grounded explanation"}}
    """


    api_logger.log_call(inputs.get('query'), "Classify")
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0.0
    )
    result = response.choices[0].message.content

    parsed_classification = parse_llm_json(
        result,
        {"intent": "point_lookup", "confidence": 0.0, "reason": "Classifier did not return valid JSON."},
        "Classify",
    )
    final_result = {"classification": normalize_classification(parsed_classification, inputs.get("query", ""))}
    print(f"[DEBUG] Output Classification: {final_result}")
    return final_result

