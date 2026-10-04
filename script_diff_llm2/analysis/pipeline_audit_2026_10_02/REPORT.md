# Pipeline audit — 2 October 2026

## Findings in brief

The rerun is **637/1,000 MATCH (63.7%)**, 137 PARTIAL, 202 MISMATCH, 18 PRE_SCAN_ERROR, 3 SCAN_ERROR, 2 GRADER_API_ERROR and 1 OTHER. The previous 1,000-question run had **698 MATCH (69.8%)**. The strongest observed defects are incorrect RDF namespaces, question meaning changed during decomposition, and correct SQL results damaged by normalization. These are not primarily model-size or grader problems.

The main-branch baseline is materially stronger than a simple predecessor without decomposition: it already decomposes, preserves predicate/connection contracts, and separates raw retrieval from processing and final composition. The architecture difference is much larger than adding decomposition. It also supplies substantial dataset-specific business rules, so its result cannot isolate an architectural effect.

**The 3 October continuation removed the remaining active wealth-specific planning/normalization helpers and added a schema-grounded requirement contract.** It is still not a universal financial-data system: ambiguous named metrics require an independently authored source catalog, and the current mixed SQL/KG identity mapping is not yet namespace-safe. No new whole-benchmark accuracy is claimed. The historical findings below describe the pre-repair rerun; the implementation update at the end records the current code state.

## Scope and provenance

- Working branch: `kritik`, initial commit `ef7feb1`; six files already had local edits. Those edits were preserved.
- Fetched origin and fast-forwarded the local `main` reference to `97f3d84`. The working checkout stayed on `kritik`.
- Baseline examined: `main:experiment_week1/improvement6`, including both `run_pipeline_v2` and `run_pipeline_v2_sql`; detailed architectural comparison below uses the SQL package.
- Active IDE file `grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py` is the grader. Runtime source is `src/script_diff_llm/`; experiment runners select configuration.
- Joined all 1,000 rerun raw and graded rows by Sample Row ID. Question, Ground Truth, New Pipeline Result and Generated SPARQL agree on all rows. This rules out pairing the wrong raw run as an explanation here.
- Inventoried 182 status-bearing CSVs across current outputs and historical directories, with 116 distinct file contents. Duplicated archives are explicitly identified in `run_inventory.csv`; they are not independent replications.
- Baseline grade files are inventoried separately in `baseline_run_inventory.json`. Files called `graded_pipeline_v9_final_answers.csv` retain execution status in `New Status`; the actual grade is in **Grade Status**. Confusing those columns produces incorrect comparisons.
- All 1,000 questions and parsed reference answers agree between current rerun and each original-question main baseline. The baseline SQLite database and configured current SQLite database have identical Git blob hashes (`d135e0277a2030afa3c3108534f18912f2b54ecd`).
- Runtime paths, prompts, cleanup, schema loaders, executor, deterministic operators, reporting and grader inputs were reviewed. Historical outputs were inventoried and compared statistically; this is not a claim that every archived query or vendored dependency was manually reviewed.
- `manifest.json` fingerprints the principal inputs. There is no trustworthy per-run source hash in the old reports: their repeated Pipeline Version string does not establish which working-tree changes produced each run.

## Results and regressions

| Run | Rows | MATCH | PARTIAL | MISMATCH | Other/failure |
|---|---:|---:|---:|---:|---:|
| Current rerun, grader2 | 1,000 | 637 | 137 | 202 | 24 |
| Previous test1000 | 1,000 | 698 | 165 | 104 | 33 |
| Main improvement6 SQL | 1,000 | 834 | 97 | 40 | 29 |
| Main SQL fixed_v1 | 1,000 | 761 | 96 | 119 | 24 |
| Main paraphrased questions | 1,000 | 677 | 135 | 160 | 28 |

The main figures above use the recorded TERA grades. Paraphrased questions are a different input condition, not a direct replication. The original SQL and fixed_v1 baseline names do not establish that one code change caused their 7.3-point difference. Business rules, generated plans and run identities need to be controlled.

Of the previous 698 matches, **157 stopped being MATCH**, including **126 becoming MISMATCH**. There were 96 newly gained matches, leaving a net loss of 61. **96 of the 126 MATCH→MISMATCH regressions use KG** in the rerun. Execution failure counts decreased, so execution reliability did not translate to semantic accuracy.

| Rerun plan | Questions | MATCH | Match rate |
|---|---:|---:|---:|
| One SQL node | 854 | 624 | 73.1% |
| One KG node | 108 | 6 | 5.6% |
| More than one node | 38 | 7 | 18.4% |

All 15 plans containing Set_Intersect are MISMATCH. This does not prove the intersection operator caused the errors: upstream KG results frequently are already empty. Do not repair set logic by relaxing the intersection to a union or dropping failed conditions.

The previous run's KG-only group had 84 matches out of 114; it is a different routed subset, so this is descriptive rather than a paired causal estimate. Mean per-question reported elapsed time fell from 38.41 to 34.28 seconds (median 22.89 to 20.51). These are per-question times, not total wall time under concurrency.

| Source family, 125 questions each | MATCH | PARTIAL | MISMATCH |
|---|---:|---:|---:|
| Basic benchmark | 69 | 7 | 49 |
| At-risk critical | 75 | 13 | 37 |
| Batch status | 97 | 1 | 26 |
| Enrichment context | 50 | 51 | 20 |
| Multi-step comparative | 68 | 38 | 9 |
| Reference compliance | 94 | 7 | 18 |
| Scoring quantitative | 94 | 20 | 9 |
| Temporal transaction | 90 | 0 | 34 |

Difficulty alone is misleading: Easy is 60/82 (73.2%), Medium 293/361 (81.2%), Hard 163/306 (53.3%), Advanced 54/124 (43.5%), Expert 67/127 (52.8%). Routing and semantic operation families explain more than these labels alone.

## Root causes, evidence and repairs

### 1. RDF namespace information is discarded

`backends/kg.py` previously reduced graph terms to local names. `load_rdf_knowledge_graph` exposed names such as Investor and investorId without their full URIs. Generation was instructed to use actual namespaces without being given reliable URI bindings. Term validation accepted a familiar local name even in an unrelated namespace.

**Observed:** 135 question traces contain generated SPARQL with `http://example.org/`. For WM125-1T-002, the recorded query returns zero rows on the live Fuseki endpoint. Changing only its namespace to the graph's observed ontology namespace returns INV-082, Amit Chauhan, Aggressive, Long-term. This is a read-only diagnostic, not a dataset-specific production rewrite.

**Implemented:** retain observed class/property URIs in metadata; supply configured prefix maps to Generate and Refine; keep full URIs in the vocabulary cache and compare parsed SPARQL predicate/class URIs. Unknown namespace terms enter existing repair/error handling. Synthetic tests use a device ontology. Legacy local-name caches remain supported, though only full-URI caches permit strict namespace checking.

**Still needed:** handle ontology local-name collisions explicitly; validate object-reference versus literal field usage; preserve native RDF datatypes/unbound values; test property paths and backend data equivalence. An empty result must remain a legitimate possibility; never turn every empty result into an automatic SQL fallback.

### 2. Decomposition changes the user's meaning before grounding

WM125-2T-004 asks how many Conservative investors have risk_score >75. Its decomposition says **political affiliation is Conservative**. Query_Spec then says that column does not exist, drops the condition, and returns 372 rather than 133. WM125-3T-012 has the same reinterpretation. WM125-1T-018 invents a ratio of matched goals instead of retrieving the stored goal-match metric, returning 0 instead of 29.801246.

The word `political` appears in 21 traces: 12 PARTIAL, 6 MISMATCH and 3 MATCH. These are a reproducible diagnostic signature, not a complete count of lost predicates.

**Implemented:** single-node DAGs execute the original question verbatim. Decomposition receives dynamically loaded SQL columns and KG index and generic instructions to preserve literals and domain terminology. This does not hard-code that Conservative maps to a particular financial field.

**Implementation update:** Query_Spec now requires quoted requirement entries pointing to actual plan items; unresolved requirements stop execution. Multi-node decomposition requires verbatim `scope_clauses` and falls back to the original question when these are missing or invented. The old keyword map and year propagation were removed. Full machine-checked Boolean/predicate equivalence across decomposition is still needed.

### 3. Normalization deletes correct NULL groups

`cleanup_query_spec` first enables preserve_null_groups, then disables it whenever a grouped question has filters or ranking. `_drop_null_group_rows` subsequently removes rows. A predicate on a fact table does not imply a non-null predicate on a grouping dimension.

EC125-3T-002's SQL correctly groups investors with Equity holdings and SIP events by risk tolerance, including the NULL group. The saved answer loses that group. The grader correctly marks the missing group PARTIAL.

**Read-only replay:** 71 single-SQL PARTIAL rows have grader reasons mentioning NULL. Re-executing their saved SQL against the configured identical database shows 67 have more rows than the saved answer. For **41**, projecting the raw SQL result onto reference column names gives exact row-multiset equality, without numeric tolerance or fuzzy aliases. See `sql_null_replay.json`. These 41 are credible recovery candidates, not 41 newly graded matches; regeneration can change SQL.

**Implemented:** remove the filtered/ranked override; unspecified null-group policy now preserves rows. Explicit exclusions remain supported. Updated the unit test that encoded the incorrect old behavior.

**Implementation update:** the automatic null-month deletion and answer alias/rounding/reshaping helpers were removed from the active result path. Null groups are retained by default. An absent event count contributes zero only when the plan explicitly sets `missing_entity_value: 0`; other missing measures remain NULL. A typed missing-value IR is still needed for complex plans.

### 4. Metric grain, population, units and formulas are conflated

Examples in the row audit:

- EC125-4T-011 and MC125-044: entities with no related actions/scenarios should contribute zero to a requested count average, but are excluded or represented as NULL.
- MC125-097: average transaction amount repeats average net cash flow. AVG(event amount) and AVG(entity SUM(amount)) are different measures.
- MC125-035 and EC125-4T-023: returns appear as fractions rather than percentage-scale values.
- MC125-091 and MC125-111: composite normalization is incorrect; scores exceed the specified scale or become zero.
- TT125-061/065/067/092: sign reversals despite signed-sum wording.
- SQA125-1T-030: ranks sector aggregates instead of individual allocation records.
- RC125-011/017/032/035: counts turn into 1.0 metrics, illustrating that preserving a column name is not preserving the computation.

**Implemented:** preserve `requires_distinct` rather than clearing it merely because the question lacks the word “distinct”; preserve SQL execution-strategy labels instead of converting them to SPARQL labels.

**Implementation update:** Query_Spec now preserves explicit operation, formula, grain and missing-value fields; a generic SQL compiler covers a narrow entity-first grouped-aggregation pattern on arbitrary table names. It does not yet compile all filters, joins, normalization formulas or eligibility populations. Unsupported patterns still rely on model SQL generation and validation.

Do not infer that every comparative query requires AVG, that every amount is signed, or that an unspecified bucket means a familiar threshold. Those are semantic definitions, not generic SQL laws.

### 5. Validation mostly checks shape, not answer fidelity

Of rows reporting Validation Is Valid=True, **80 are MISMATCH and 134 PARTIAL**. A table with the expected column names can implement the wrong filters or grain. Some invalid semantic results still retain success after retries; SQL and KG execution success is reported independently of answer correctness. The grouped-single-row heuristic is also unsound: a valid filtered grouped query may contain exactly one group.

**Implementation update:** Query_Spec contract errors are traced as `Query_Spec_Contract` and stop generation. The single-group-is-an-error heuristic was removed. Raw SQL rows remain in the trace before conservative normalization. Complete semantic equivalence and transformation-level provenance are still open.

### 6. Identity and result enrichment can distort meaning

WM125-3T-009 loses investor IDs and collapses distinct people sharing a name. ARC125-1T-010/011 return internal UUIDs with no useful identity or requested scores. ARC125-1T-017 copies IDs into metric/group_avg aliases.

`enrich_sql_result_rows` has hard-coded investor-profile and health lookups. Normalization invents convenience aliases and can copy nonnumeric measures into numeric-looking aliases. DAG key selection includes domain-specific preferred keys, and IRI local-name normalization can collapse different namespaces.

**Implementation update:** active SQL enrichment and answer-alias synthesis were removed; set operators no longer default to `investor_id`. Explicit identity/display bindings and namespace-safe cross-backend mappings remain open.

## Historical runs: what is and is not comparable

The current-output training series includes the following recorded MATCH counts. Full status distributions and duplicate detection are in `run_inventory.csv`.

| File shorthand | Rows | MATCH | PARTIAL | MISMATCH |
|---|---:|---:|---:|---:|
| train_442_terra | 442 | 105 | 70 | 181 |
| train_442_terra_ab14 | 442 | 108 | 76 | 172 |
| train_442_ab2_terra | 442 | 126 | 94 | 195 |
| train_442_ab2_regraded | 442 | 188 | 167 | 60 |
| train_442_semanticfix_terra | 442 | 240 | 132 | 41 |
| train_442_semanticfix_v2_terra | 442 | 215 | 131 | 65 |
| all_final605_terra | 605 | 269 | 211 | 57 |
| 605_final_terra | 605 | 339 | 135 | 40 |
| 605_final_direct_llm_terra | 605 | 374 | 113 | 80 |
| 605_final_semantic_terra | 605 | 308 | 171 | 56 |
| 605_fast_terra | 605 | 312 | 166 | 56 |

There are also 30-row and 78-row partial runs: 12 and 19 MATCH respectively. They cannot be compared as full-benchmark improvements. Regrading the same output is not a pipeline improvement; nor does a different denominator demonstrate generalization. Prior prompt rules are part of each historical treatment and must be documented as such.

The main baseline's grader directories record MATCH totals from 624 to 834 across different graders/files. Directory naming is unreliable: `pipelien_output_sql_gpt_oss_grader` records TERA as the actual grader. Use the recorded grader model and payload hashes, not the folder label. Some regrader files also treat execution failures differently. These numbers quantify evaluation variability, not multiple new pipeline performances.

The unchanged current grader allows harmless extra columns, semantic column aliases, numeric strings and numeric tolerance. Most investigated failures are therefore not cosmetic formatting disputes. It also truncates large prompt inputs at 60,000 characters: 13 rerun references and 42 saved answers exceed that length. This warrants an evaluation limitation in the paper, not rewriting this grader. No grader code or saved grades were changed.

## Baseline architecture versus current architecture

| Aspect | improvement6 SQL package | Current script_diff_llm2 |
|---|---|---|
| Retrieval/planning | Retrieve then schema-grounded decomposition with answer requirements | Semantic decomposition first; per-node retrieval |
| DAG | Fixed operator chain per source branch | Model-selected backend nodes and set operators |
| Query_Spec | Raw records from one source, identity/link keys, optional fields, filters | Analytical plan including joins, measures, aggregation and ranking |
| Generation | Deterministic raw SQL renderer where supported | Several special compilers, otherwise full SQL/SPARQL generated by LLM |
| Calculation | Processing_Spec and Final_Spec executed by relational/spec runtime | Mostly delegated to generated backend query |
| Contracts | Predicate, connection-key, retrieval, processing and final-spec contracts | Output-shape and selected aggregation/join checks |
| Repair | Can regenerate Query_Spec and return repair requirements upstream | Mostly refine generated query with limited semantic-stage recovery |
| Domain grounding | Explicit business-rule pack injected into planning prompts | Schema plus prompt rules and hard-coded cleanup/enrichment |

The README's “3 decompositions × 3 DAGs” description is not authoritative for the current SQL planner: `planner.py` builds the fixed chain. It is not valid to describe this synced baseline as having no decomposition. Establish an immutable original baseline commit before making a paper claim about what your modification introduced.

The main baseline business pack includes sign conventions, concentration=MAX(allocation_pct), investor-first averaging, metric formulas, named score definitions, tie keys, lock-in periods, and even a reference to “MC-104.” `schema_annotations.py` also hard-codes an ontology namespace. Removing that knowledge without supplying authoritative runtime metadata makes some questions under-specified.

## Generic rules and leakage boundary

**Allowed generic instructions:** preserve Boolean scope and literals, use observed schema/URIs, respect declared keys and multiplicities, preserve NULL semantics, prevent unsafe fanout, obey explicit units/grain/ranking, and fail visibly on unresolved requirements.

**Dataset-specific knowledge that must not live in generic prompt templates or cleanup code:** which financial field defines a named metric; whether stored values are already signed; bucket thresholds; allowed categories; ontology namespaces; synonyms linking business terms to source fields; investor-specific ID/display rules.

Provide that knowledge as a versioned, independently authored semantic catalog supplied with the data source. Generic prompts may consume retrieved catalog facts as runtime context. That is schema/business grounding, not label leakage, provided those facts originate independently of evaluation answers. If the requirement literally prohibits all dataset-specific information even in runtime context, reliable answering of ambiguous enterprise questions is impossible: column names alone do not determine business meaning.

The current execution entrypoint passes only the preprocessed question into planner/executor; Ground Truth is used by benchmark reporting and grading. **No direct reference-answer injection was found along this path.** This is narrower than a proof of zero leakage across all historical experiments.

Exact question overlap checks (case and whitespace normalized) found zero overlap between test1000 and the 300-question training workbook, 142-question test workbook, final605 questions, or the current-output training CSVs. See `question_overlap.json`. This does not rule out shared templates, entities, business definitions or benchmark-informed development; these runs use the same wealth database. The inspected comparisons do not themselves establish the abstract's claim of transfer to a second non-overlapping enterprise knowledge base.

Remaining contamination risks are real:

- The pre-repair `specification.py`, SQL enrichment, bucket compiler and answer-alias code contained benchmark and wealth-specific behavior. These active and dormant helpers were removed in the 3 October continuation.
- Main business-rule pack mentions a benchmark-specific metric identifier.
- This audit uses the test1000 errors to guide development. After these repairs, test1000 is a development/regression set; reserve a fresh, untouched domain/entity/template-separated final evaluation.

No reference answers were added to runtime prompts, new rules or regression tests. New tests use an unrelated device schema. The audit artifacts contain reference answers for offline analysis and are not imported by runtime code.

For privacy, open-weight does not mean on-premises: the configured pipeline calls an AWS Bedrock-compatible endpoint, and TERA grading sends reference and predicted answers to its configured service. A privacy claim must describe actual deployment and data flow, not only weight availability.

## Recommended order of work

1. Validate these namespace, fidelity and null-preservation fixes with the unchanged grader on a fresh output path. Preserve source/config/model/database hashes and all operator inputs.
2. Replace silent condition dropping with a requirement ledger and contract checks. Add schemas/enums/business definitions as independently sourced metadata.
3. Separate generic planning from the remaining wealth-specific cleanup and enrichment. Delete benchmark-expectation overrides; move legitimate domain definitions into the catalog with provenance.
4. Introduce a typed relational IR and deterministic compilation for supported operations, borrowing the baseline's raw/processing/final separation and predicate coverage. Keep complex joins and eligibility populations explicit. Avoid forcing every operation into a single generated query.
5. Test operator invariants on synthetic schemas: renamed columns, one-to-many duplication, same-name entities, null groups, zero-event entities, date-scope differences, percentages and mixed URI namespaces.
6. Run controlled ablations: no decomposition vs decomposition; SQL-only vs KG-only vs hybrid on equivalent data; generic metadata vs governed catalog; learned generation vs deterministic compilation. Keep model, grader, questions, source snapshot, retries and temperature fixed. Report per-family accuracy, latency, tokens, errors and paired transitions.
7. Evaluate on a truly unseen domain using only its catalog/schema adapter. Verify transfer rather than claiming “any financial data” from success on one wealth dataset.

Do not add the 41 null-replay opportunities and 135 namespace traces as a projected accuracy gain: the latter includes matches, overlaps other defects, and regeneration may change outcomes.

## MCP recommendation

**Do not make MCP the next accuracy intervention.** MCP standardizes access to resources and callable tools; it does not define correct decomposition, aggregation grain, financial metric meaning or evaluation. Wrapping the current backends would preserve their semantic bugs.

After stabilizing a semantic catalog and execution interface, MCP can be useful for enterprise integration: expose schema discovery, catalog lookup, approved value lookup, query validation and read-only execution behind consistent typed tool interfaces. Keep the orchestrator and deterministic execution contracts in the application. Enforce tenant scope and authorization in the data service, and use local/private deployment where required. Avoid giving every agent an unconstrained database surface merely to call the architecture “multi-agent.”

This recommendation is an engineering inference from the observed failures and MCP's documented server primitives: [official MCP server overview](https://modelcontextprotocol.io/specification/draft/server/index) and [official MCP architecture](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/architecture/index.mdx).

## Changes and verification

Changed production surfaces: `backends/kg.py`, `pipeline/kg_pipeline.py`, `pipeline/core_pipeline.py`, `pipeline/decomposition.py`, `pipeline/dag/planner.py`, `pipeline/specification.py`, and `pipeline/semantic_contract.py`. The pre-existing SQL backend edits were not changed by this audit. The grader, experiment data and saved outputs were not changed.

- Seven new generic regression tests pass.
- Eleven existing SQLite integration/DAG regression tests pass.
- Live metadata extraction returns full class/property URIs; live wrong-namespace validation rejects the incorrect Investor URI.
- Read-only SQL and Fuseki replays support the root-cause findings above.

### 3 October continuation

All edits remain inside `script_diff_llm2`; the grader and saved grades were not changed. The continuation adds `pipeline/contracts.py`, requires source-field/output/requirement coverage, retries one malformed contract, and rejects unresolved plans before generation. Single-node decomposition executes the original wording; multi-node plans need quoted source clauses. Query_Spec cleanup no longer injects benchmark metric formulas, thresholds, ranking limits or default averages. SQL scanning opens SQLite read-only, the generic entity-first compiler handles a bounded aggregation pattern, and the grouped-count compiler accepts only explicit distinct entity counts. The active result path preserves backend values and NULL groups. Dead wealth-specific enrichment, fixed-threshold bucket and alias-synthesis helpers were deleted.

Validation: 117 unit tests pass with 37 skips, 10 DAG regression tests pass, 1 SQLite integration test passes, source compilation passes and `git diff --check` passes. The 37 skips are legacy tests that asserted the retired wealth-specific inference or output rewriting; they are retained as historical examples and are **not** evidence that the new generic behavior passes those scenarios. New portable tests use synthetic customer/charge tables and fake model responses. No live 1,000-question rerun or unchanged-grader rescore has been performed after these edits, so the effect on MATCH percentage is unknown.

Open engineering limits: source-specific named financial metrics still need independently authored definitions in the new catalog hook; mixed-backend entity matching needs source-declared identity bindings; the SQL compiler covers only a subset of the Query_Spec language; and the runtime still assumes the configured dual SQL/Fuseki infrastructure. These are necessary qualifications to the claim that the pipeline works on arbitrary financial data. Use a fresh held-out dataset to evaluate transfer and avoid treating the analyzed test1000 answers as a clean final test set.

### Subsequent portability and live-smoke continuation

An optional, versioned source catalog can now be loaded with `SEMANTIC_CATALOG_FILE`; its metric entries must name real live-schema fields and include provenance. Only entries matching the current subquery and retrieved source enter Query_Spec context. No wealth-specific metric definition was added. See `docs/semantic_catalog.md`. The catalog can also declare an exact KG URI-namespace-to-SQL-ID binding. With no binding, full IRIs remain distinct, and set operators use exact keys. The executor no longer guesses an overlapping column or silently substitutes a category for an upstream identifier; missing declared bindings fail visibly, while a genuinely empty upstream list produces an empty dependent result. This improves portability and prevents false joins, but an unconfigured mixed KG/SQL source may now yield empty intersections until its owner supplies the identity mapping.

A bounded live run used the configured Fuseki, SQLite and GPT-OSS model with `TEST_QUERY_LIMIT=1`, fresh output paths, and the grader disabled. It exposed two real issues during the continuation: the requirement ledger rejected a faithful paraphrase, and malformed model DAG nodes could crash planning. Both were repaired generically with regression tests. The repeated point-lookup smoke then returned one requested name row with `PIPELINE_SUCCESS`. A separate grouped smoke for EC125-3T-002 returned `PIPELINE_SUCCESS` with four rows, including the `risk_tolerance = NULL` group; the raw SQL rows and final rows agree. These are execution and normalization checks, **not an unchanged-grader rescore or a new benchmark MATCH percentage**. The smoke CSVs and logs are ignored by Git because they contain benchmark material.

The requirement contract now accepts a nonverbatim projection only for a point lookup when its physical field tokens are present in the question; computed measures still require explicit requirement coverage. It rejects unsupported added concepts and filter literals. The catalog and binding hooks are source adapters, not evidence that every financial ontology or multi-source computation is supported. The original 1,000-question audit remains development evidence; reserve a fresh held-out set for any paper claim about generalization.

Final local verification after this continuation: 122 unit tests pass (37 historical skips), 10 DAG regression tests pass, 1 SQLite integration test passes, Python source compilation passes, and `git diff --check` passes. The grader and existing saved grades remain unchanged.

### 3 October full rerun and in-progress grader audit

The completed raw rerun at `outputs/openai_gpt_oss_120b/all/test1000/rerun_20261003_023143/raw_pipeline.csv` has 1,000 rows: 411 `PIPELINE_SUCCESS`, 583 `DAG_NODE_ERROR`, 5 `PRE_SCAN_ERROR`, and 1 `SCAN_ERROR`. Thus the maximum possible MATCH count for this saved run is 411, even before judging answer correctness. Its 579 `Q1:Query_Spec_Contract` failures dominate the regression. The preceding rerun had 979 successful executions and its unchanged grader produced 637 MATCH, 137 PARTIAL, and 202 MISMATCH, with 24 other statuses. These runs cannot be compared as controlled ablations because the intervening pipeline code changed; they do demonstrate that the current score is primarily an execution regression.

Failure traces show three recurring mechanisms. Missing requirement ledgers or per-item quotation links alone blocked at least 217 questions despite schema-grounded plans; those annotations are useful diagnostics but do not determine whether a field exists. About 146 failed specs had an empty top-level `output_schema` and keys shaped like inner grain, requirement, filter or measure objects. The generic JSON parser can extract a valid inner object from a truncated outer response; Query_Spec had accepted that fragment as the whole plan. Another 96 failures included invalid source names, commonly a logical `base_entity` such as `investor` even though the plan's actual source fields pointed to a physical schema table. These categories are diagnostic, not additive: a row can have multiple errors, and raw model responses were not retained for every case.

At an audit snapshot of 584 graded rows, the grader file had 176 MATCH, 28 PARTIAL, 374 MISMATCH, 5 PRE_SCAN_ERROR and 1 GRADER_API_ERROR. This is an ordered prefix of a still-running grader, **not** the final 1,000-row rate. Of the 374 mismatches, 354 were Query_Spec contract failures and 3 were downstream binding failures; 17 had successful execution but wrong answers. The grader labels most `DAG_NODE_ERROR` outputs MISMATCH because that status is not preserved by its grading policy. The grader was not edited or stopped.

The 17 answer mismatches in this prefix include wrong source-field choices (`Gold` filtered as `investment_name` where the intended category appears to be `investment_type`), distinct-investor counts that disagree with the reference despite executing `COUNT(DISTINCT investor_id)`, and multi-measure averages with different aggregation/population semantics. These are separate from the execution regression and need source-grounded metric/value metadata, query-spec coverage, and controlled database checks. A benchmark-specific Gold mapping or answer rule was deliberately not added. A successful SQL execution is not evidence of a correct financial answer.

Only future pipeline runs use the subsequent generic repairs: Query_Spec retries a fragment that lacks an outer plan envelope; a logical base entity binds to a physical source only when the source and entity key uniquely identify it; missing ledger quotations remain visible as `contract_warnings` while unknown sources, fields, unresolved meanings, and invalid implementations still block. No saved raw row, grade, grader code, or external database was changed. Validation after these repairs: 125 unit tests pass with 37 historical skips, 10 regression tests and 1 integration test pass, and `git diff --check` passes. Use `/usr/bin/python3` for the test suite in this environment; the default Python lacks `rdflib`. These checks establish local behavior, **not** a new MATCH rate. Run a fresh raw pipeline and unchanged grader to measure the result; reserve another held-out set for final paper claims.

For the earlier paired audit and bounded read-only SQL diagnostics, run `/usr/bin/python3 script_diff_llm2/analysis/pipeline_audit_2026_10_02/reproduce.py --replay-sql` from the repository root. The saved `audit_only_changes.patch` is an earlier audit snapshot and does not include this continuation.
