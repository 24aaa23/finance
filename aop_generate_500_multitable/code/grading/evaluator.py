import os
from code.config import LLMClient
from code.grading.deterministic import normalize_for_compare
from code.grading.llm_grader import run_llm_grade

def evaluate_results(query: str, ground_truth: str, pipeline_output: str, client: LLMClient, mode=None) -> tuple[str, str]:
    """Evaluates query results using the chosen grader mode (defaults to config env settings)."""
    if mode is None:
        mode = os.getenv("GRADING_MODE", "llm")
        
    # Optional deterministic exact check before invoking LLM
    if mode in ["deterministic", "hybrid"]:
        norm_gt = normalize_for_compare(ground_truth)
        norm_out = normalize_for_compare(pipeline_output)
        if norm_gt == norm_out and norm_gt != "":
            return "MATCH", "Evaluated via deterministic exact match."
        if mode == "deterministic":
            return "MISMATCH", "Evaluated via deterministic mismatch."
            
    # LLM fallback / primary LLM grader
    return run_llm_grade(query, ground_truth, pipeline_output, client)
