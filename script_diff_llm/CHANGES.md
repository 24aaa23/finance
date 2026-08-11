# AOP Pipeline — Change Report

Baseline: `run_pipeline_deepseek_v3_2_all_test.py` (3,713 lines)
Result: `run_pipeline_deepseek_v3_2_all_test.py` (4,463 lines) + `aop_ext.py` (1,423 lines)
Diff against baseline: **933 changed lines** in the runner.

**Verification status.** Both files compile. 86 tests pass: 67 unit tests over the new
logic (`test_aop_ext.py`) and 19 integration smoke tests over the wiring
(`smoke_test_wiring.py`, using stubbed LLM and Fuseki calls). The pipeline has **not**
been run end to end — no endpoint, no triplestore, no KG files were available. Budget a
short debugging pass on a 5-query window before the full 300.

**rdflib.** Not used for parsing, validation, or execution anywhere in the new code. All
structural analysis is done directly on the query text; everything that touches the graph
goes through Fuseki over SPARQL/HTTP. An rdflib syntax check exists behind
`AOP_USE_RDFLIB_SYNTAX_CHECK`, **off by default**, for debugging only.

---

## 1. Files

| File | Purpose |
|---|---|
| `run_pipeline_deepseek_v3_2_all_test.py` | Your runner, modified in place. Every edit is marked `REFINED PIPELINE:` in a comment. |
| `aop_ext.py` | New stdlib-only module holding all new logic. Separated so it is importable and testable without an endpoint. |
| `test_aop_ext.py` | 67 unit tests. `python3 -m unittest test_aop_ext -v` |
| `smoke_test_wiring.py` | 19 integration tests with stubbed LLM/Fuseki. `PYTHONPATH=stubs python3 -m unittest smoke_test_wiring -v` |
| `stubs/` | Fake `rdflib`/`openai` modules, used only so the smoke tests can import the runner offline. **Do not ship these to your real environment** — they shadow the real packages. |

Place `aop_ext.py` next to the runner. No new third-party dependencies.

---

## 2. Changes by area

### 2.1 Dead code paths restored (correctness bugs, not features)

Three functions returned early whenever `rdf_graph is None`, which is always true on the
Fuseki backend. They were documented as active in the methodology but never executed.

| Function | Was | Now |
|---|---|---|
| `add_cardinality_hints` | Returned the schema unmodified. `cardinality_hints` never existed, yet Generate and Refine both instructed the model to "use cardinality_hints from Schema Details" — an instruction pointing at absent data. | Delegates to new `add_cardinality_hints_fuseki`: one aggregate SPARQL query per (class, property) computing distinct values, coverage, and max/avg subjects per value, then labels `many_per_value` / `unique_per_value`. |
| `get_actual_properties_for_failed_query` | Returned `[]`. The post-scan repair loop therefore always sent the generator the placeholder `"Unknown - ensure you are using exact prefixes and LCASE()"` instead of real evidence. | Runs the lookup over Fuseki. Also returns the `rdf:type` of the subject carrying the literal, which is what the generator needs to fix an entity-anchoring error. |
| `optimize_missing_related_record_count_sparql` | Returned the query unchanged, so the rewrite never fired. | The rdflib subject/object walk is replaced by `related_class_has_direct_key()` — a single cached `ASK`. |

These three alone change behaviour on every query, independently of the new features.

### 2.2 Multi-candidate SPARQL with execution-consensus selection

**Where:** `semantic_generate_sparql` (sampling), `pre_programmed_scan` (selection),
`aop_ext.select_by_consensus` (logic).

`Generate` now samples `k` candidates in parallel (`AOP_SPARQL_CANDIDATES`, default 3).
Candidate 0 is always greedy at temperature 0, so `k=1` reproduces the original pipeline
exactly. `Scan` executes every candidate, groups them by an order-insensitive fingerprint
of the result set, and returns the modal cluster.

Selection order: drop candidates failing deterministic hard-error checks → drop candidates
that error or time out → prefer the largest result cluster → prefer non-empty over empty at
equal size → within the winner, prefer the cleanest structural check, then the shortest query.

Two economies: the selected candidate's result is already in hand, so `Scan` does not
re-execute; and a repair attempt (`logic_feedback` present) uses a single greedy call,
because sampling alternatives after targeted error feedback dilutes the feedback signal.

Telemetry recorded per query: `Candidate Count`, `Candidate Agreement`,
`Candidate Cluster Count`, `Candidate Telemetry` (per-candidate status, row count,
fingerprint, structural severity).

### 2.3 Deterministic SPARQL structure checking

**Where:** `aop_ext.parse_sparql_structure`, `aop_ext.check_sparql_structure`,
called from `semantic_pre_scan_validate`.

Everything decidable from the query text is now decided in Python, before any LLM call.
The previous design asked the model and then keyword-matched its prose for words like
`"cartesian"`, `"row explosion"`, `"time out"` to decide whether to stop.

The extractor masks string literals and IRIs, peels nested `OPTIONAL` / `MINUS` /
`FILTER NOT EXISTS` / subquery blocks, then builds a union-find over the variables of each
triple-pattern statement in the main graph pattern.

| Code | Severity | Detects |
|---|---|---|
| `E_DISCONNECTED_PATTERN` | hard | More than one connected variable component (a Cartesian product), unless `UNION` is present |
| `E_UNSCOPED_NEGATION` | hard | A `NOT EXISTS`/`MINUS` block sharing no variable with the outer pattern |
| `E_MISSING_GROUP_BY` | hard | Aggregates projected alongside ungrouped plain variables |
| `E_COUNT_SUBSTITUTION` | hard | Spec requires SUM/AVG/MIN/MAX, query only uses COUNT |
| `E_AGGREGATE_IN_BIND` | hard | Aggregate inside `BIND`/`OPTIONAL` |
| `E_UNDECLARED_PREFIX`, `E_UNKNOWN_TERM`, `E_NO_SELECT`, `E_EMPTY` | hard | Executability |
| `E_MISSING_OUTPUT_FIELD`, `E_MISSING_MEASURE`, `E_MISSING_ORDER_BY`, `E_MISSING_LIMIT`, `E_RANK_DIRECTION` | repairable | Spec conformance |
| `W_NO_TIE_BREAK` | acceptable | `ORDER BY` + `LIMIT` with a single sort key |

Two design guarantees:

- **A structural hard error short-circuits without an LLM call.** Cheaper and more reliable.
- **The LLM cannot override the deterministic verdict upward.** If Python finds a repairable
  warning and the model says the query is fine, the outcome stays a repairable warning
  (`source: "structural_override"` in the trace).

Low-confidence parses never produce hard errors — an unsegmentable query degrades to a
warning rather than a false rejection.

### 2.4 Decomposed multi-scan execution

**Where:** `semantic_build_query_spec`, `cleanup_query_spec`, `semantic_generate_sparql`,
`pre_programmed_scan`, `aop_ext.combine_sub_results`.

`Query_Spec` may now emit `execution_strategy: "decomposed_sparql"` with `sub_queries` and
a `combine` block. `Generate` returns named SPARQL queries; `Scan` executes each and
combines the results using your existing `Set_Intersect` / `Set_Union` / `Set_Difference` /
`Math_Compute` implementations, wired through the new `SCAN_COMBINE_OPERATORS` registry.

This is what makes those four operators reachable. Previously the plan validator required
exactly one `Scan` node, so a third of the operator library was unexecutable.

Two guards had to be removed and replaced with validation rather than prohibition:

- `semantic_build_query_spec` used to downgrade `decomposed_metric_scan` and
  `post_scan_pandas_merge` unconditionally. It now validates the decomposition (≥2 named
  sub-queries, a `combine.op`, inputs referencing real sub-query names, a join key for set
  operations) and downgrades only if malformed.
- **`cleanup_query_spec` had a second, independent downgrade** at its first branch
  (`if execution_strategy not in {"single_sparql", "preaggregate_sparql"}`) that would have
  silently undone the above. Fixed. This one is easy to miss.

Failure is contained: a malformed spec downgrades to `preaggregate_sparql`, and unparsable
decomposed generation falls back to single-query mode.

### 2.5 Grounded literal-value linking

**Where:** `aop_ext.ValueIndex`, built in `main()`, injected into `Query_Spec` and `Generate`.

For each categorical property, one SPARQL query collects the distinct literal values.
Properties exceeding `AOP_VALUE_INDEX_MAX_VALUES` (default 200) are skipped as free-text or
identifier-like. The index is cached to `output/value_index.json` and reused.

At query time, token and n-gram phrases from the question are matched exactly, then fuzzily
via `difflib`. Matches are rendered into both prompts with instructions to use equality on
exact matches instead of `CONTAINS(LCASE(...))`. Linked values are recorded per query.

### 2.6 Cross-query exemplar memory

**Where:** `aop_ext.ExemplarStore`, injected into `Query_Spec` and `Generate`, written at
the end of `_execute_dag_inner`.

Only clean successes are stored: no failure stage, no short-circuit, validation passed,
SPARQL present. Retrieval is token-cosine over stored questions, with self-exclusion so a
question cannot retrieve itself on a resumed run.

> **This makes your run transductive.** Later questions benefit from earlier ones on the same
> evaluation split. The runner prints a warning at startup and every entry records
> `source_split`. For a clean model comparison, either pre-populate from a disjoint dev split
> and set `AOP_EXEMPLAR_FROZEN=1`, or set `AOP_ENABLE_EXEMPLARS=0`. Whichever you pick must be
> stated in the paper — a reviewer will look for this.

### 2.7 Global per-query budget

**Where:** `aop_ext.QueryBudget`, charged in `APILogger.log_call`, bound in `run_single_test`,
caught in `AOPExecutor.execute_dag`.

Every semantic operator already called `api_logger.log_call` before its request, so that is
the one place all of them can be metered — no operator or retry loop can bypass it.

The three repair loops (pre-scan × scan-refine × post-scan, each re-entering the others)
previously made worst-case cost per question a product rather than a sum. `BudgetExhausted`
now propagates out and is converted into an ordinary short-circuit with
`failure_stage = "Budget"`, so a capped question still yields a well-formed result row.
Defaults: 60 LLM calls, 900 seconds. The budget is released in a `finally` block, because
worker threads are reused across questions.

Recorded per query: `LLM Calls`, `LLM Calls By Operator`, `Budget Exhausted`.

### 2.8 Reward clamp made opt-in

**Where:** `AdvancedAOPPlanner._evaluate_dag_reward`.

`adjusted_score = max(0.5, raw_score)` collapsed the judge to two effective values, since
the prompt only ever asks for 0.0/0.5/1.0 and 0.0 was lifted to 0.5. Combined with the
`>= 0.9` selection threshold, the reward model could not discriminate. The clamp is now
controlled by `AOP_REWARD_CLAMP`, **default off**, so the judge's contribution is
measurable. Set it to 1 to reproduce your existing runs.

### 2.9 Ablation switches

All in `aop_ext.PipelineConfig`, all env-driven, all folded into a config fingerprint that
is printed at startup and stamped on every result row.

| Variable | Default | Ablation |
|---|---|---|
| `AOP_ENABLE_PLANNER` | 1 | 0 → fixed canonical chain via `build_canonical_chain_dag`, bypassing plan search entirely |
| `AOP_ENABLE_QUERY_SPEC` | 1 | reserved |
| `AOP_ENABLE_PRE_SCAN_VALIDATE` | 1 | 0 → deterministic checks only, no LLM validator |
| `AOP_ENABLE_SELF_HEAL` | 1 | 0 → every repair loop runs once (`EFFECTIVE_*_RETRIES` = 1) |
| `AOP_REWARD_CLAMP` | 0 | 1 → original clamp |
| `AOP_SPARQL_CANDIDATES` | 3 | 1 → original single greedy generation |
| `AOP_ENABLE_STRUCTURAL_CHECK` | 1 | 0 → LLM-only validation |
| `AOP_ENABLE_VALUE_LINKING` | 1 | 0 |
| `AOP_ENABLE_EXEMPLARS` | 1 | 0 |
| `AOP_ENABLE_DECOMPOSED_EXECUTION` | 1 | 0 → single-Scan only |

The no-planner ablation is the important one. Because `_validate_planned_dag` already pins
the operator order, the planner's only remaining freedom is which optional operators to
include. If the fixed chain matches the full planner, the plan search is not earning its cost.

### 2.10 Evaluation hardening

- **Execution accuracy.** If the dataset carries a gold SPARQL column
  (`AOP_GOLD_SPARQL_COLUMN`, default `gold_sparql`), the gold query is executed and the
  result sets compared under the same normalisation used for consensus clustering. Recorded
  as `Exec Match`. This is far more objective than judging the verbalised answer string.
- **Seeds.** `AOP_RUN_SEED` is recorded per row so repeated runs stay distinguishable.
- **Config fingerprint** on every row, including crash rows.
- **19 new report columns** covering structural verdicts, candidate telemetry, generation
  mode, execution strategy, combine op, sub-query row counts, linked values, exemplars used,
  and budget consumption.

### 2.11 State propagation fix

`sparql_candidates` and `sub_sparql` were added to the global data bus back-fill in the
executor. Without this, an intermediate routing node drops them and `Scan` silently falls
back to single-candidate mode — a failure that would have been invisible in the results.

---

## 3. Reproducing your current baseline

```bash
AOP_SPARQL_CANDIDATES=1 \
AOP_REWARD_CLAMP=1 \
AOP_ENABLE_STRUCTURAL_CHECK=0 \
AOP_ENABLE_VALUE_LINKING=0 \
AOP_ENABLE_EXEMPLARS=0 \
AOP_ENABLE_DECOMPOSED_EXECUTION=0 \
python run_pipeline_deepseek_v3_2_all_test.py
```

This restores original behaviour on every axis **except** the three dead code paths in §2.1,
which are bug fixes rather than features and are not switchable. If you need a
strictly-identical baseline for the paper, run the original file.

---

## 4. Suggested ablation table

| Run | Configuration |
|---|---|
| Full | defaults |
| − plan search | `AOP_ENABLE_PLANNER=0` |
| − multi-candidate | `AOP_SPARQL_CANDIDATES=1` |
| − structural checks | `AOP_ENABLE_STRUCTURAL_CHECK=0` |
| − LLM pre-scan validator | `AOP_ENABLE_PRE_SCAN_VALIDATE=0` |
| − self-healing | `AOP_ENABLE_SELF_HEAL=0` |
| − value linking | `AOP_ENABLE_VALUE_LINKING=0` |
| − exemplars | `AOP_ENABLE_EXEMPLARS=0` |
| − decomposition | `AOP_ENABLE_DECOMPOSED_EXECUTION=0` |
| reward clamp restored | `AOP_REWARD_CLAMP=1` |

Report accuracy, execution match, mean LLM calls, and mean latency for each — the budget
telemetry now makes the cost columns free.

---

## 5. Known limitations

1. **Never executed end to end.** The pure logic is well tested; the wiring is tested only
   against stubs. Prompt f-strings, real model outputs, and the decomposed path in
   production are unverified.
2. **The SPARQL structure extractor is regex-based**, not a full grammar. It is deliberately
   conservative — low-confidence parses yield warnings, never hard errors — but an exotic
   query shape could be misread. `Structural Issue Codes` is logged per query specifically so
   you can audit for false rejections after your first run.
3. **`empty_answer_can_be_valid` is unchanged.** It is still a keyword heuristic that decides
   whether an empty result counts as correct. With `Exec Match` available, prefer checking
   against gold; I left the heuristic alone rather than silently changing what counts as a
   correct answer in your existing numbers.
4. **`AOP_ENABLE_QUERY_SPEC` is defined but not yet wired.** Removing `Query_Spec` requires
   relaxing `_validate_planned_dag`, which affects plan validity for every query; it needs a
   design decision from you rather than a mechanical edit.
5. **The value index and cardinality hints add startup cost** — roughly one SPARQL query per
   categorical property, plus one per (class, property) for hints. The value index is cached
   after the first run; cardinality hints are not. Consider caching them too if startup drags.
