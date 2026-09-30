# Business Rule Pack Integration

## What changed

This pipeline now uses a compact structured business-rule pack for the wealth-management domain rules.

Added:

- `business_rule_pack.json`
  - A structured Plan C rule pack derived from `../business_rules_addendum.md` and `../domain_intro_latest.prompt`.
  - Captures rule precedence, cash-flow signs, withdrawal presentation, ranking tie-breaks, NULL ranking policy, per-investor averaging grain, allocation concentration, composite score formulas, returns weighting, aggregation guardrails, proportion denominators, XIRR handling, and lock-in rules.

- `business_context.py`
  - Loads `business_rule_pack.json`.
  - Provides `business_context_prompt()` so each LLM prompt gets the same deterministic JSON rule context.

Updated prompt stages:

- `llm_operators/decompose.py`
  - Injects the rule pack before source and operand selection.
  - Tells the model to apply the pack before guessing metric definitions, weighting, signs, ranking tie-breaks, null policy, or population grain.

- `llm_operators/query_spec.py`
  - Injects the rule pack while selecting raw fields.
  - Tells the model to retrieve operands required by governed metrics instead of similarly named shortcut fields.

- `llm_operators/final_spec.py`
  - Injects the rule pack while building executable calculation plans.
  - Replaces the older inline cash-flow sign reminder with a rule-pack reference.

- `llm_operators/validate.py`
  - Injects the rule pack into optional semantic review so review can catch formula, sign, weighting, null, or population mistakes.

## Why this was done

Previously, business meaning lived mostly as scattered prompt text. That made the model vulnerable to old or guessed definitions, such as summing allocation concentration or using an obsolete composite score formula.

The new Plan C approach gives the pipeline one compact structured source of truth. The most important planning stages now see the same rule pack:

1. Decompose chooses the right source tables and operands.
2. Query_Spec preserves those raw operands and filters.
3. Final_Spec computes formulas using the ratified rules.
4. Validate can review the result against the same rules.

## Source precedence

The rule pack encodes this order:

1. `business_rules_addendum.md` wins when rules clash.
2. `domain_intro_latest.prompt` is the corrected domain background.
3. Actual database enum values remain authoritative for values used in queries.

## Notes

No old files were deleted. The prior inline business hint in `Final_Spec` was replaced with a pointer to the new rule pack so the prompt does not maintain two competing sources of truth.
