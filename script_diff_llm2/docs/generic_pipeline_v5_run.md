# Generic pipeline v5

V5 corrects observed plan-interface regressions while retaining v4's schema profiling, RDF datatype checks and bounded SQL repair. Runtime prompts contain generic computation rules and independently obtained source metadata. The optional business-rules catalog is disabled by the launcher. No grader changes or reference-answer access were added to the runtime.

The paired audit is in `analysis/generic_no_rules_v5/REPORT.md`. Saved-plan revalidation recovers 155 of v4's 269 contract-blocked questions and 76 of v2's 167. No previously contract-clear saved plan becomes blocked. These are contract acceptance counts, not measured v5 matches. V5 has not been evaluated with a fresh paid benchmark. An 80% MATCH score is a target, not a guarantee.

## Changes

- Schema-grounded normalization records each structural repair in `query_spec.structural_repairs`: path, old value, new value and evidence. Reserved operand labels, logical source labels, physical versus alias formulas, distinct entity-key counts and nested aggregate-predicate syntax are normalized only when supported by the plan and schema.
- Missing aggregate stages are inferred only when exactly one aggregation level exists. Conflicting aliases, ambiguous sources, unknown operands and genuine unresolved definitions still block execution. Filter values, operators, scopes, requested populations and ranking limits are preserved.
- Identical plain projections duplicated between group_by and measures are consolidated, with requirement paths and subsequent measure indices updated. Conflicting expressions or aggregate computations sharing an alias are still rejected.
- QuerySpec's model-facing template no longer asks for redundant operand_kind. The runtime derives it from the resolved operands. Prompts distinguish stored fields from requested aggregations and spell out entity totals versus row averages, and explicit magnitude versus stored sign.
- Contract repair revalidates the corrected candidate without inheriting stale validator diagnostics. Stored-field questions can correct an erroneous analytic classification rather than invent an aggregate.
- Consumer output contracts reach each upstream subquery's QuerySpec. Missing required output aliases trigger contract repair before execution. Source identity values and supported mappings remain required; identifiers are never manufactured from URI suffixes.
- RDF validation receives parsed evidence for direct projections from mandatory typed carriers. OPTIONAL, UNION and negative patterns do not establish mandatory carrier evidence. A projected literal does not need rdf:type. Evidence does not override unrelated semantic validation failures.

## Run

If Fuseki is not already serving the configured dataset, start it in a separate terminal:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
./tools/apache-jena-fuseki-6.1.0/fuseki-server \
  --localhost --port=3030 \
  --file="$PWD/data/kg/wealth_management_diverse_kg.ttl" /wealth
```

Then run the full raw pipeline followed by the unchanged grader:

```bash
cd /home/kritik/Desktop/neosapiens/finance/script_diff_llm2
bash runners/run_generic_v5.sh all
```

This uses existing configured credentials and makes paid model calls for unfinished work. Reports are written to `outputs/openai_gpt_oss_120b/all/test1000/generic_no_rules_v5`, with version `generic-contract-recovery-v5`. The launcher sets the report paths, disables the catalog, and clears source/input overrides so the original experiment configuration applies after a NeoWealth run. It selects all 1,000 questions with offset zero regardless of previous subset settings.

For an explicitly full run despite earlier subset settings:

```bash
TEST_QUERY_LIMIT=1000 TEST_QUERY_OFFSET=0 bash runners/run_generic_v5.sh all
```

Run/resume only one stage with:

```bash
bash runners/run_generic_v5.sh raw
bash runners/run_generic_v5.sh grade
```

Reusing the same folder/version resumes saved rows. Saved raw CRASH/QUOTA_EXHAUSTED rows are retried; other saved failures count as completed. Unsaved in-flight work may repeat. Use a fresh V5_OUTPUT_DIR after changing pipeline code; do not mix different implementations in one report.

Offline checks:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -q
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/regression -q
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/integration -q
PYTHONPATH=src /usr/bin/python3 analysis/generic_no_rules_v5/revalidate.py
```

Revalidation needs the source database and running Fuseki. It performs read-only metadata queries, compares saved reports and writes only analysis artifacts. It makes no model calls and does not execute or grade new answers.
