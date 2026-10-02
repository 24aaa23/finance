# Baseline changes — 2026-10-02

This snapshot contains five 1,000-question baselines: Base SPARQL, Base SQL,
GraphRAG Local, Parallel SPARQL, and Parallel SQL. GraphRAG hybrid code and
results are excluded.

## Pipeline changes

### Domain-neutral generation prompts

- Base SQL and Parallel SQL now provide the active database DDL, the question,
  and the instruction to return only SQL. Row counts, sample values,
  wealth-management wording, database-specific table/join assumptions, and
  hand-written SQL rules were removed.
- Base SPARQL and Parallel SPARQL now provide the active RDF schema, the
  question, and the instruction to return only SPARQL. Wealth-management
  wording, fixed ontology prefixes, and database-specific query rules were
  removed.
- GraphRAG Local now provides only the retrieved RDF facts, the question, and
  the required JSON response contract. Its domain-specific answer rules and
  system message were removed.
- SQL and SPARQL prompts retain the basic output constraint requested for the
  benchmark: return only the query, without reasoning, explanations, Markdown,
  comments, or prose.

### Base SPARQL namespace handling

- Namespace declarations and qualified names are derived from the active Turtle
  schema instead of hard-coded wealth-management namespaces.
- Fuseki metadata discovery is restricted to classes found in the active
  schema and records full property IRIs before rendering schema-qualified terms.
- Generated SPARQL prefix repair now uses the active schema namespace map.
- In the rerun, operational results improved from 601 successful scans, 399
  scan errors, and 126 non-empty scans to 967 successful scans, 33 scan errors,
  and 879 non-empty scans. All 1,000 generated queries used the real namespace;
  none used the former `example.org` placeholder namespace.

### Parallel SPARQL validation

- Local RDFLib `parseQuery` validation is protected by a lock because the
  shared parser grammar is not thread-safe under concurrent calls.
- Model generation and Fuseki execution remain parallel; only local parser
  validation is serialized.
- The fixed rerun produced 779 consensus outputs and 221 no-consensus outputs.
  Across 3,000 branches, 2,926 completed and 74 had scan errors.

### Grading

- The grader prompt was not changed.
- The current reports were graded with `gpt-5-mini`.
- The five graded CSVs each contain 1,000 unique sample IDs.

## Current GPT-5 Mini results

| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1,000 | 495 | 182 | 311 | 12 |
| Base SQL | 1,000 | 662 | 105 | 228 | 5 |
| GraphRAG Local | 1,000 | 68 | 876 | 54 | 2 |
| Parallel SPARQL | 1,000 | 454 | 326 | 220 | 0 |
| Parallel SQL | 1,000 | 632 | 168 | 198 | 2 |

## Previous committed snapshot

The table below is included for provenance, not as a controlled grader-model
comparison. Both the pipelines and the grader model changed between snapshots.
The previous reports used the older pipeline prompts and GPT-5.6 TERA.

| Pipeline | Total | MATCH | MISMATCH | PARTIAL | OTHER / ERROR |
|---|---:|---:|---:|---:|---:|
| Base SPARQL | 1,000 | 618 | 257 | 125 | 0 |
| Base SQL | 1,000 | 815 | 75 | 110 | 0 |
| GraphRAG Local | 1,000 | 60 | 904 | 36 | 0 |
| Parallel SPARQL | 1,000 | 382 | 513 | 105 | 0 |
| Parallel SQL | 1,000 | 806 | 141 | 53 | 0 |

## Reports added in this snapshot

- `query_type_grading_results_gpt_5_mini.md`: MATCH, MISMATCH, PARTIAL, and
  remaining-status counts for every query type in each pipeline.
- `category_grading_results_125_each_gpt_5_mini.md`: the same counts for all
  eight source categories, with exactly 125 questions per category per
  pipeline.
- `generate_grading_markdown.py`: reproducibly rebuilds both reports and checks
  row counts, unique sample IDs, grader model, source categories, and category
  size.
- `baseline_metrics_gpt_5_mini.md`: accuracy, token latency, inference cost,
  average cost per question, and execution efficiency for every baseline.
- `generate_baseline_metrics.py`: reproducibly rebuilds the aggregate metrics
  report from the five graded CSVs.
