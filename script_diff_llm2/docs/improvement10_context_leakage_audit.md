# Improvement 10: context specificity and leakage audit

Scope: unchanged snapshot commit `9ce5a6d99c96f3c17dda0b98ec8edc0c11bd2380`, using the original `simple` knowledge compiler and agent consultation. This is a static inference-boundary review plus inspection of actual model caches, not a proof that all prompts from historical requests were clean.

## Findings

1. **Direct reference-answer leakage was not found in the inspected inference path.** `main.py` reads Ground Truth into a separate variable for reports. Query understanding receives the sanitized question, schema and compiled business pack; consultation receives question/schema/documents; retrieval, decomposition and execution receive question and generated context. The 216 answer overrides populate reference columns before execution, not planner arguments. Four original offline flow tests passed, including reference-answer marker isolation. Loading reference answers in the same process is a weaker architectural separation than separate inference/evaluation processes, but does not itself establish leakage.

2. **The operator code appears predominantly generic; the supplied context is intentionally database-specific.** Searches of production Python found no embedded ATOM table identifiers, investor-profile/portfolio-health table names, risk-pressure formulas or Deposit/Withdrawal rules. Default asset paths are dataset-specific. The domain file and addendum contain concrete tables, units, financial thresholds, sign conventions and composite formulas. These are injected via an agent-built pack and are not inferred solely from the physical SQL schema. SQL→KG portability of the hybrid project must not be conflated with this original SQL baseline.

3. **Evaluation-derived content is present in inference documents.** The addendum names benchmark questions, identifies review concerns, refers to corrected ground-truth workbooks, and changes the SQA-5T-006 threshold to an index >65 with an approximate cohort of 36 investors. R3/R4 cite empirical values such as 50 tied returns rows and 77 of 1550 investors with missing health scores. This is not a dumped per-question reference-result table, but creates a benchmark-contamination risk. Expert approval alone does not establish independence from evaluation. Document provenance and timing are needed to decide whether these are prior business policies or corrections derived from held-out evaluation.

4. **No active quarantine blocks those documents in simple mode.** `load_documents` reads domain, rules and all YAML verbatim. `validate_documents` only checks nonempty content. `compile_single` supplies all documents to drafting and review. `consult_domain` can resend all original documents during a question. BENCHMARK_ID exists, but masking in knowledge_units is not the active simple compiler. Compiler instructions explicitly permit examples/source notes. Moving such material into an external file does not prevent it from influencing inference.

5. **Actual propagation is confirmed.** GPT-OSS's cache retains both the 77-of-1550 observation and the >65 threshold. DeepSeek retains the >65 threshold in three rule texts. Literal benchmark IDs were not found in the inspected GPT-OSS, DeepSeek, Gemma or Qwen compiled rules/citations. Nevertheless, compilation saw those IDs and consultation retains access to the full source. No exact overlap was found between the addendum's 13 unique question IDs and the selected workbook's Source Question ID values; this does not prove semantic independence because similar/rephrased questions or shared rules may overlap.

6. **YAML context may include example data.** `planning_schema` allows column sample_values and full yaml_metadata; documentation is loaded verbatim. Original prompt-boundary tests deliberately permit documented examples while excluding live database samples/row counts. This is schema grounding, not a row-free prompt guarantee. Private enterprise documentation can be transmitted to the configured provider. Open-weight model usage does not itself imply local/private processing.

## Implication for the paper

Describe Improvement 10 as a domain-conditioned SQL baseline using the supplied reviewed business-rule documents. Do not describe its results as evidence of a fully generic, benchmark-independent inference system. Direct answer-key leakage was not identified; contextual benchmark contamination cannot be ruled out and concrete evaluation-related source material was found.

Keep the existing baseline artifacts unchanged. For a separate clean experiment, use independently authored deployment documentation: retain legitimate definitions, units, signs, ownership, aggregation grain and approved financial formulas; remove question IDs, evaluation corrections, GT-workbook references and observed expected cohort sizes. Do not merely strip IDs while retaining question-derived decisions. Confirm the provenance of threshold/formula choices. Version the cleaned documents, create fresh caches/output folders, and compare to the unchanged baseline. No accuracy impact can be predicted without running that experiment.

## Source locations

- `source/improvement10/business_rules_addendum.md`: R3/R4 empirical statistics; R8 benchmark-indexed metric inventory, GT-workbook references and threshold correction.
- `source/improvement10/domain_intro_latest.prompt`: finance-specific domain definitions.
- `run_pipeline_v3_sql _/knowledge.py`: load_documents, validate_documents, planning_schema and prompt_pack.
- `run_pipeline_v3_sql _/knowledge_single.py`: complete-document simple draft and review.
- `run_pipeline_v3_sql _/consultation.py`: original documents resent to domain specialist.
- `run_pipeline_v3_sql _/main.py`: separate inference arguments and report-only ground_truth variable.

No original source, prompts, data, caches, graders or saved output files were changed during this audit.
