import re
from code.config import LOCAL_MODEL, api_logger, LLMClient

def run_llm_grade(query: str, ground_truth: str, pipeline_output: str, client: LLMClient) -> tuple[str, str]:
    eval_prompt = f"""
    You are a strict grading assistant.
    Did the Pipeline output successfully answer the user's question based on the Ground Truth?

    Question: {query}
    Ground Truth: {ground_truth}
    Pipeline Output: {pipeline_output}

    Rules:
    1. Treat the Ground Truth as the authoritative answer.
    2. If Ground Truth contains a concrete number, JSON value, category, investor ID, or name, the Pipeline Output must contain the same facts. If it says "No data found", "database error", or gives a different number such as 0, mark MISMATCH.
    3. Only mark "No data found" as MATCH when Ground Truth explicitly says no rows/no data/no business rule.
    4. If Ground Truth is JSON, all important values in the JSON must appear in the Pipeline Output. Missing values are PARTIAL or MISMATCH, not MATCH.
    5. If the Pipeline Output gives 0 but Ground Truth is a nonzero number, mark MISMATCH.
    6. For yes/no or comparison questions, the Pipeline Output must explicitly answer yes/no or include all compared facts needed to prove the answer. If it only returns an intermediate row or one side of the comparison, mark MISMATCH.
    7. If the Pipeline Output is just "Result from retrieved rows" and does not directly answer the user's question, mark MISMATCH unless those rows alone fully contain the requested final answer.
    8. Ignore superficial formatting. Check the facts, not presentation.
    9. Treat IDs with punctuation differences as equivalent when the letters and digits match. Examples: INV-001 = INV001, INV_001 = INV001, inv 001 = INV001.
    10. Treat comma-formatted and unformatted numbers as equivalent. Examples: 601,230 = 601230 and 9,192 = 9192.
    11. Ignore markdown, bold text, bullets, extra whitespace, and reasoning/thinking tags such as <reasoning>...</reasoning> or <think>...</think>.
    12. Treat minor spelling variations or obvious database label typos as equivalent when they clearly refer to the same value. Example: Coporate Bond = Corporate Bond. Do not use this rule for genuinely different categories or names.
    13. If the Ground Truth lists multiple tied correct answers and the Pipeline Output returns only one of them, mark PARTIAL, not MATCH.

    Examples:
    - Ground Truth: 1; Pipeline Output: 0 => MISMATCH.
    - Ground Truth: {{"sector": "Private Equity", "allocation_pct": 42}}; Pipeline Output: No data found => MISMATCH.
    - Ground Truth: No; Pipeline Output only shows {{"sectorName": "Private Equity"}} without the stated sector focus => MISMATCH.
    - Ground Truth: {{"investor_id": "INV-001"}}; Pipeline Output: "INV001" => MATCH.
    - Ground Truth: {{"investment_type": "Corporate Bond"}}; Pipeline Output: "Coporate Bond" => MATCH.
    - Ground Truth: {{"amount": 601230}}; Pipeline Output: "601,230" => MATCH.

    Output ONLY the word MATCH, PARTIAL, or MISMATCH.
    """
    
    api_logger.log_call(query, "Final_Result_Grader")
    eval_response = client.chat.completions.create(
        model=LOCAL_MODEL, messages=[{"role": "user", "content": eval_prompt}], temperature=0.0
    )
    raw_status = eval_response.choices[0].message.content.strip()
    status_match = re.search(r"\b(MATCH|PARTIAL|MISMATCH)\b", raw_status, flags=re.I)
    new_status = status_match.group(1).upper() if status_match else raw_status
    comments = "Evaluated via LLM-only final grader."
    return new_status, comments
