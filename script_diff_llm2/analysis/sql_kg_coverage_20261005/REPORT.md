# SQL → KG coverage and identity audit

This audit concerns source representation fidelity, not benchmark accuracy. It reads the configured SQLite database and local RDF export, uses no reference answers, makes no model calls, and does not change either source or the answering pipeline.

## Finding

The current KG preserves all records and physical field values from the current eight-table SQL database. The sources are two representations of shared enterprise records. They are not independent factual databases.

The RDF graph also contains metadata, category resources, asset resources, and materialized relationships. These additional structures are not additional independently verified business observations merely because they are graph nodes. Their provenance and semantics should be distinguished from the SQL-backed record layer.

## Inputs and reproducibility

The audit reads these files under `script_diff_llm2`:

- `historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db`
- `data/kg/wealth_management_diverse_schema.ttl`
- `data/kg/wealth_management_diverse_kg.ttl`
- `data/kg/wealth_management_diverse_kg_summary.json`
- `data/kg/rdf_id_alias_map.json`

`coverage.json` records absolute paths and SHA-256 hashes. The export summary records an original Windows SQL source path, `wealthmanagement_tables-main\raw_data_sample\wealth_management_diverse.db`. That path is historical provenance; current equality is established by comparing the configured local database's records, not by assuming its file path matches the historical path.

The audit also writes [field_mapping.csv](field_mapping.csv), covering all 70 table-column bindings, and [identity_mapping.csv](identity_mapping.csv), covering all eight record classes, key literals, namespaces, and investor relationships. These are review artifacts, not automatically activated pipeline configuration.

The original SQL→RDF converter was not located in the searched workspace Python files or identifiable converter paths on `main`. The audit therefore reconstructs mappings from the export summary, actual RDF provenance, and actual values. It does not claim to have inspected the original converter implementation. The available alias-map builder is an identifier convenience utility, not the SQL→RDF converter.

Re-run from the finance repository root:

```bash
/usr/bin/python3 -u script_diff_llm2/analysis/sql_kg_coverage_20261005/audit.py
```

Paths and endpoint can be overridden with `--database`, `--kg`, `--schema`, `--export-summary`, `--alias-map`, and `--fuseki-endpoint`. The audit uses a read-only SQL connection and one read-only Fuseki class-count query. All artifacts remain in this analysis directory.

## Record coverage

| SQL table | RDF class | SQL rows | RDF source records | Source record key |
|---|---|---:|---:|---|
| ATOM_ENTITY_INVESTOR_PROFILE_001 | Investor | 1,550 | 1,550 | investor_id |
| ATOM_ENTITY_PORTFOLIO_HEALTH_001 | PortfolioHealth | 1,550 | 1,550 | portfolio_health_id |
| ATOM_ENTITY_PORTFOLIO_HOLDING_001 | PortfolioHolding | 15,102 | 15,102 | holding_id |
| ATOM_ENTITY_SECTOR_ALLOCATION_001 | SectorAllocation | 3,038 | 3,038 | sector_id |
| ATOM_ENTITY_INVESTMENT_GOAL_001 | InvestmentGoal | 4,865 | 4,865 | goal_id |
| ATOM_EVENT_CASH_FLOW_001 | CashFlow | 7,828 | 7,828 | cash_flow_id |
| ATOM_EVENT_REBALANCING_ACTION_001 | RebalancingAction | 6,192 | 6,192 | rebalance_id |
| ATOM_EVENT_SCENARIO_REBALANCING_001 | ScenarioRebalancing | 1,549 | 1,549 | scenario_rebalance_id |
| **Total** | | **41,674** | **41,674** | |

All SQL record keys are non-null and unique within their tables. Each has exactly one corresponding RDF subject carrying its key literal and expected class. No SQL keys are missing from RDF, and no extra SQL-backed RDF keys were found. The audit checks every row, not a sample.

Important qualification: SQLite declares **no primary-key or foreign-key constraints** on these tables. The export's `pk` entries describe converter-selected keys; uniqueness is verified empirically against this snapshot. Generic runtime schema discovery cannot discover these as declared constraints because they do not exist in SQLite DDL.

## Field coverage and transformations

Across the eight tables there are 70 table-column mappings and 419,600 source cells:

- **402,154 non-null cells** match exactly under text comparison or decimal comparison of the SQL/RDF numeric representations.
- **17,446 SQL NULL cells** have no value for the corresponding RDF property.
- There are **zero missing non-null values, unequal values, unexpected values for null cells, or multi-valued physical cells**.

The comparison associates records through the exported key and compares each physical SQL column with its annotated RDF property. `wm:sourceColumn` annotations are present in the merged RDF export; relying only on the standalone schema file would miss these bindings. The audit explicitly checks that every row and column mapping was examined (`audit_complete: true`).

The verified mapping is therefore value-preserving at the SQL record/property layer, with these representation changes:

| SQL representation | RDF representation | Consequence for queries |
|---|---|---|
| Physical table | Named RDF class plus `wm:sourceTable` provenance on records | SQL table names and RDF class names differ. |
| snake_case physical column | RDF predicate, generally camelCase, annotated with `wm:sourceColumn` | Field correspondence must come from metadata, not spelling guesses. |
| Record identifier | Original identifier literal plus namespaced resource IRI | Projected literals can equal SQL keys; full IRIs cannot be used as SQL IDs unchanged. |
| NULL cell | Absent property triple | Mandatory triple patterns can accidentally remove nullable rows; optional patterns and presence tests must follow the question. |
| Date stored as SQL TEXT | Literal typed as `xsd:date` | SPARQL date comparisons need datatype-aware literals; the source lexical dates remain unchanged. |
| SQL numeric value | `xsd:decimal`, `xsd:integer`, or occasional `xsd:double` | Numeric value is preserved; RDF datatype and serialization are not the SQLite storage representation. |
| Shared `investor_id` value | Preserved literal plus explicit investor relationship | Traversal expresses relationships originally implicit in SQL identifier equality. |

Observed datatypes for the mapped non-null cells are 224,156 plain literals, 151,531 decimals, 4,672 integers, 11 doubles, and 21,784 typed dates. These figures describe source serialization; they do not establish identical rounding behavior for every SQL and SPARQL aggregate.

## Identity and relationship coverage

For all 41,674 SQL-backed records, the decoded URI suffix equals the original record key. Verified namespaces are:

| RDF class | Namespace | Preserved key predicate |
|---|---|---|
| Investor | `https://wealth.example.org/kg/investor/` | investorId |
| PortfolioHealth | `https://wealth.example.org/kg/portfolio-health/` | portfolioHealthId |
| PortfolioHolding | `https://wealth.example.org/kg/holding/` | holdingId |
| SectorAllocation | `https://wealth.example.org/kg/sector-allocation/` | sectorAllocationId |
| InvestmentGoal | `https://wealth.example.org/kg/investment-goal/` | goalId |
| CashFlow | `https://wealth.example.org/kg/cash-flow/` | cashFlowId |
| RebalancingAction | `https://wealth.example.org/kg/rebalancing-action/` | rebalanceId |
| ScenarioRebalancing | `https://wealth.example.org/kg/scenario-rebalancing/` | scenarioRebalanceId |

All 40,124 non-profile records have investor relationship targets agreeing with their SQL `investor_id` values. The checked child-to-investor predicates are `belongsToInvestor`, `healthOfInvestor`, `heldByInvestor`, `allocationOfInvestor`, `cashFlowOfInvestor`, `rebalancingActionOfInvestor`, and `scenarioRebalancingOfInvestor`. The machine-readable audit additionally verifies the corresponding investor-to-child edges recorded in the export summary.

This establishes two usable identity strategies:

1. **Project the preserved literal key.** A KG result containing `wm:investorId`, for example, can supply the same identifier string expected by SQL. This does not need IRI suffix conversion.
2. **Convert a resource IRI through a declared, source-verified namespace mapping.** The suffix correspondence is verified here, but the runtime does not activate it automatically. An explicitly configured catalog binding is needed when actual IRI conversion is requested.

Current ablation launchers set `SEMANTIC_CATALOG_FILE` empty. Consequently they do not automatically convert these IRIs through a catalog. An identity-compatible graph exists, but a producer that returns the wrong representation can still create a failed binding. Physical identity coverage and model projection correctness are separate properties.

The compact RDF alias map contains 1,658 normalized lookup keys resolving to exactly 1,550 distinct identifiers, with no entries marked ambiguous. It covers all 1,550 investor keys and none of the primary record keys in the other seven tables. It is therefore an investor-spelling convenience map, not a complete record identity catalog: many SQL records use UUID identifiers. Its per-table coverage is recorded in `coverage.json`. It should not be used to infer equivalence between unrelated classes or to justify arbitrary IRI stripping.

## Extra graph structures

The merged graph has **742,996 triples**. Beyond the eight source-record classes it includes 5,752 `Asset` resources, category and context nodes, metadata primitives and attributes, documented derived attributes, and other structural classes. These are graph enrichment and metadata layers.

The audited SQL columns are all preserved, so there is no evidence of a missing physical field that inherently forces cross-backend record composition for this snapshot. Many graph relationship questions can potentially be expressed as SQL joins over the underlying records. However, not every graph enrichment or documented context fact is necessarily stored as a SQL table/column. This audit does not prove full semantic equivalence for every enriched graph traversal or metadata-based query.

## Running Fuseki verification

The live endpoint `http://127.0.0.1:3030/wealth/query` returned the same distinct-subject count for **every RDF type** as the local merged export. This supports that the running dataset has the expected class population.

It is deliberately a lightweight verification while raw ablations run. Equal class counts do **not** prove equality of all live literals or relationship triples. The complete value and relationship audit applies to the local configured TTL export. A full live-data comparison would be a separate stronger check.

## Implications and next steps

No pipeline change is needed to repair missing SQL records or physical values in the local KG export: none were found. Preserve the running ablations.

After those runs finish, focus any changes on use of the representations:

- Have dependent KG nodes expose preserved source identifier literals when SQL expects those keys. If full IRIs must cross the interface, supply the verified mapping as source configuration rather than hard-coded financial prompt rules.
- Expose verified source key and relationship metadata independently of benchmark answers. The SQLite file's lack of declared constraints is a real grounding gap even though the data has valid relationships.
- Audit nullable-property handling and typed dates in failed queries. Mandatory RDF patterns and incorrect literal types can cause SQL/KG answers to diverge despite identical source values.
- Use table/column/property correspondence to inspect routing errors. Shared-source provenance supports simpler one-backend plans when that representation contains all required information; it does not prove that a model selected a correct plan.
- Retain the original export manifest and converter, when available, for future database regeneration. Record/property equality at this snapshot does not guarantee that a later database update leaves Fuseki synchronized.

The methodology document has been corrected to describe a relational database and its derived RDF representation, including the distinction between record fidelity and graph enrichment. No inference code, grader, source data, or running job was modified.
